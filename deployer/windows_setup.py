"""Windows-native Node.js + OpenClaw installation.

Downloads Node.js from npmmirror (Chinese mirror), installs it,
configures npm to use the taobao registry, and installs openclaw.
"""

import hashlib
import os
import platform
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from deployer.logger import DeployerLogger
from deployer.skill_catalog import export_catalog_json

# ── Mirror URLs ──
MIRRORS = {
    "npmmirror": {
        "node_download_base": "https://registry.npmmirror.com/-/binary/node",
        "git_mirror_base": "https://registry.npmmirror.com/-/binary/git-for-windows",
        "npm_registry": "https://registry.npmmirror.com",
    },
    "tencent": {
        "node_download_base": "https://mirrors.cloud.tencent.com/nodejs-release",
        "git_mirror_base": "https://registry.npmmirror.com/-/binary/git-for-windows",  # tencent has no Git mirror
        "npm_registry": "http://mirrors.cloud.tencent.com/npm/",
    },
}
DEFAULT_MIRROR = "npmmirror"

# Legacy constants (kept for reference, use self._mirror_* instead)
NODE_DOWNLOAD_BASE = MIRRORS["npmmirror"]["node_download_base"]
NPM_REGISTRY = MIRRORS["npmmirror"]["npm_registry"]
GIT_MIRROR_BASE = MIRRORS["npmmirror"]["git_mirror_base"]

# Default install location
DEFAULT_NODE_DIR = Path(os.environ.get(
    "OPENCLAW_NODE_DIR",
    str(Path.home() / ".openclaw-node"),
))

DEFAULT_DESKTOP_DIR = Path(os.environ.get(
    "MICROCLAW_DIR",
    str(Path.home() / ".microclaw"),
))

# Strict pattern for version strings interpolated into URLs/commands
_VERSION_RE = re.compile(r'^\d+(\.\d+){0,2}$')

# Hide console windows spawned by subprocess on Windows
_CREATE_NO_WINDOW = 0x08000000


class WindowsSetup:
    """Handles Node.js + OpenClaw installation on Windows natively."""

    def __init__(self, config, logger: DeployerLogger):
        self.cfg = config
        self.log = logger
        self.node_version = config.get("node.version", "22")
        self.node_dir = DEFAULT_NODE_DIR
        self._node_bin: Path | None = None
        self._git_bin: str | None = None  # path to git bin directory
        self._rollback_actions: list[tuple[str, Callable]] = []

        # Select mirror based on npm.registry config
        registry = config.get("npm.registry", "")
        if "tencent" in registry.lower():
            mirror = MIRRORS["tencent"]
        else:
            mirror = MIRRORS["npmmirror"]
        self._node_download_base = mirror["node_download_base"]
        self._git_mirror_base = mirror["git_mirror_base"]
        mirror_name = "tencent" if "tencent" in registry.lower() else "npmmirror"
        self._mirror_name = mirror_name

    # ────────────────────── Subprocess helper ──────────────────────

    @staticmethod
    def _run(cmd, **kwargs):
        """Wrapper around subprocess.run that hides console windows on Windows."""
        kwargs.setdefault("creationflags", _CREATE_NO_WINDOW)
        return subprocess.run(cmd, **kwargs)

    # ────────────────────── Rollback ──────────────────────

    def _register_rollback(self, label: str, fn):
        """Push a cleanup action onto the rollback stack."""
        self._rollback_actions.append((label, fn))

    def rollback(self):
        """Execute all registered rollback actions in reverse order."""
        if not self._rollback_actions:
            return
        self.log.step("正在清理已安装的组件…")
        for label, fn in reversed(self._rollback_actions):
            try:
                self.log.info(f"  回滚: {label}")
                fn()
            except Exception as e:
                self.log.warn(f"  回滚 '{label}' 失败: {e}")
        self._rollback_actions.clear()
        self.log.info("清理完成")

    # ────────────────────── Git ──────────────────────

    def ensure_git(self) -> bool:
        """Install Git if not already available."""
        git_path = shutil.which("git")
        if git_path:
            self._git_bin = str(Path(git_path).parent)
            self.log.info("git already in PATH")
            return True

        self.log.step(f"Installing Git for Windows ({self._mirror_name})…")
        arch = self._get_arch()
        # Resolve latest Git version from npmmirror
        git_version = self._resolve_git_version()
        if not git_version:
            self.log.error("Could not resolve Git version")
            return False

        # Git for Windows release naming (verified against actual releases):
        #   x64:   PortableGit-{ver}-64-bit.7z.exe   (self-extracting)
        #   arm64: PortableGit-{ver}-arm64.7z.exe     (self-extracting)
        #   x86:   MinGit-{ver}-32-bit.zip            (zip — no 32-bit PortableGit since ~v2.50)
        use_mingit_zip = (arch == "x86")
        if arch == "arm64":
            filename = f"PortableGit-{git_version}-arm64.7z.exe"
        elif arch == "x86":
            filename = f"MinGit-{git_version}-32-bit.zip"
        else:
            filename = f"PortableGit-{git_version}-64-bit.7z.exe"
        url = f"{self._git_mirror_base}/v{git_version}.windows.1/{filename}"

        git_dir = Path.home() / ".openclaw-git"
        try:
            tmp_dir = Path(tempfile.mkdtemp(prefix="openclaw_git_"))
            dl_path = tmp_dir / filename

            self.log.info(f"Downloading: {url}")
            self._download_with_progress(url, dl_path)

            self.log.step("Extracting Git…")
            git_dir.mkdir(parents=True, exist_ok=True)

            if use_mingit_zip:
                # MinGit is a plain zip — extract directly
                with zipfile.ZipFile(dl_path, "r") as zf:
                    zf.extractall(git_dir)
            else:
                # PortableGit self-extracts with -o flag
                self._run(
                    [str(dl_path), "-o" + str(git_dir), "-y"],
                    capture_output=True, text=True, timeout=120,
                )

            shutil.rmtree(tmp_dir, ignore_errors=True)

            git_exe = git_dir / "bin" / "git.exe"
            if not git_exe.exists():
                # Some versions use cmd/git.exe
                git_exe = git_dir / "cmd" / "git.exe"

            if git_exe.exists():
                # Add to current process PATH
                git_bin = str(git_exe.parent)
                self._git_bin = git_bin
                os.environ["PATH"] = git_bin + os.pathsep + os.environ.get("PATH", "")
                # Add to system PATH permanently
                self._add_to_system_path(git_bin)
                self.log.success(f"Git installed to {git_dir}")
                # Register rollback
                def _rollback_git(d=str(git_dir), b=git_bin):
                    shutil.rmtree(d, ignore_errors=True)
                    self._remove_from_system_path(b)
                self._register_rollback("删除 Git", _rollback_git)
                return True

            self.log.error("Git extraction failed — git.exe not found")
            return False
        except Exception as e:
            self.log.error(f"Git install failed: {e}")
            return False

    def _resolve_git_version(self) -> str | None:
        """Resolve latest Git for Windows version from npmmirror."""
        import json
        try:
            url = "https://api.github.com/repos/git-for-windows/git/releases/latest"
            req = urllib.request.Request(url, headers={"User-Agent": "OpenClawDeployer/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            tag = data.get("tag_name", "")  # e.g. "v2.47.1.windows.1"
            ver = tag.lstrip("v").split(".windows")[0]  # "2.47.1"
            return ver
        except Exception:
            pass
        # Fallback: hardcoded recent version
        return "2.53.0"

    def _add_to_system_path(self, directory: str):
        """Add a directory to system PATH via registry (persistent)."""
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
                0, winreg.KEY_ALL_ACCESS,
            )
            current, _ = winreg.QueryValueEx(key, "Path")
            if directory.lower() not in current.lower():
                new_path = current.rstrip(";") + ";" + directory
                winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
                self.log.info(f"  Added to system PATH: {directory}")
            winreg.CloseKey(key)
        except Exception as e:
            self.log.warn(f"  Could not update system PATH: {e}")

    def _remove_from_system_path(self, directory: str):
        """Remove a directory from system PATH via registry."""
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
                0, winreg.KEY_ALL_ACCESS,
            )
            current, _ = winreg.QueryValueEx(key, "Path")
            parts = [p for p in current.split(";") if p.strip().lower() != directory.lower()]
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, ";".join(parts))
            winreg.CloseKey(key)
        except Exception:
            pass

    # ────────────────────── Node.js ──────────────────────

    def _get_arch(self) -> str:
        """Return 'x64', 'x86', or 'arm64' based on platform."""
        machine = platform.machine().lower()
        if machine in ("amd64", "x86_64", "x64"):
            return "x64"
        if machine in ("arm64", "aarch64"):
            return "arm64"
        if machine in ("x86", "i386", "i686"):
            return "x86"
        return "x64"

    def _get_node_download_url(self, version: str) -> str:
        """Build the download URL for Node.js Windows zip from npmmirror."""
        arch = self._get_arch()
        # npmmirror hosts Node binaries at:
        # https://registry.npmmirror.com/-/binary/node/v22.x.x/node-v22.x.x-win-x64.zip
        return f"{self._node_download_base}/v{version}/node-v{version}-win-{arch}.zip"

    def _resolve_latest_version(self, major: str) -> str:
        """Resolve '22' to the latest specific version like '22.14.0'."""
        self.log.debug(f"Resolving latest Node.js {major}.x version…")
        import re
        import json
        import ssl

        # Method 1: Use nodejs.org version index (most reliable)
        try:
            url = "https://nodejs.org/dist/index.json"
            req = urllib.request.Request(url, headers={"User-Agent": "OpenClawDeployer/1.0"})
            # Try normal SSL first, fall back to unverified if cert fails
            # (common in China due to corporate proxies / missing CA certs)
            try:
                resp = urllib.request.urlopen(req, timeout=15)
            except urllib.error.URLError:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                resp = urllib.request.urlopen(req, timeout=15, context=ctx)
            with resp:
                data = json.loads(resp.read())
            for entry in data:
                ver = entry.get("version", "").lstrip("v")
                if ver.startswith(f"{major}."):
                    self.log.debug(f"Resolved from nodejs.org: {ver}")
                    return ver
        except Exception as e:
            self.log.debug(f"nodejs.org resolve failed: {e}")

        # Method 2: Scrape npmmirror directory listing
        try:
            url = f"{self._node_download_base}/latest-v{major}.x/"
            req = urllib.request.Request(url, headers={"User-Agent": "OpenClawDeployer/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            arch = self._get_arch()
            pattern = rf'node-v({major}\.\d+\.\d+)-win-{arch}\.zip'
            matches = re.findall(pattern, html)
            if matches:
                best = max(matches, key=lambda v: tuple(int(x) for x in v.split(".")))
                self.log.debug(f"Resolved from npmmirror: {best}")
                return best
        except Exception as e:
            self.log.debug(f"npmmirror resolve failed: {e}")

        # Fallback — must satisfy OpenClaw's v22.12+ requirement
        fallback = f"{major}.20.0"
        self.log.warn(f"Could not resolve version, using fallback: {fallback}")
        return fallback

    def check_node_windows(self) -> bool:
        """Check if a suitable Node.js is available on Windows."""
        # Check our managed install first
        managed_node = self.node_dir / "node.exe"
        if managed_node.exists():
            ver = self._get_node_version(str(managed_node))
            if ver and self._version_ok(ver):
                self.log.info(f"Node.js (managed) found: {ver}")
                self._node_bin = managed_node.parent
                return True

        # Check system PATH
        node_path = shutil.which("node")
        if node_path:
            ver = self._get_node_version(node_path)
            if ver and self._version_ok(ver):
                self.log.info(f"Node.js (system) found: {ver} at {node_path}")
                self._node_bin = Path(node_path).parent
                return True
            elif ver:
                self.log.warn(f"Node.js {ver} found but need ≥22")

        return False

    def install_node_windows(self) -> bool:
        """Download and install Node.js on Windows from npmmirror."""
        self.log.step(f"Installing Node.js on Windows ({self._mirror_name})…")

        version = self._resolve_latest_version(self.node_version)
        if not _VERSION_RE.match(version):
            self.log.error(f"Invalid resolved version: {version!r}")
            return False
        self.log.info(f"Resolved version: v{version}")

        url = self._get_node_download_url(version)
        self.log.info(f"Downloading: {url}")

        try:
            # Download to temp
            tmp_dir = Path(tempfile.mkdtemp(prefix="openclaw_node_"))
            zip_path = tmp_dir / "node.zip"

            self._download_with_progress(url, zip_path)

            # Verify SHA256 integrity against official SHASUMS256.txt
            if not self._verify_node_sha256(version, zip_path):
                self.log.error("SHA256 verification FAILED — download may be tampered")
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return False

            # Extract
            self.log.step("Extracting Node.js…")
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp_dir)

            # Find the extracted folder (e.g., node-v22.14.0-win-x64/)
            arch = self._get_arch()
            extracted = tmp_dir / f"node-v{version}-win-{arch}"
            if not extracted.exists():
                # Try to find it
                for d in tmp_dir.iterdir():
                    if d.is_dir() and d.name.startswith("node-v"):
                        extracted = d
                        break

            if not extracted.exists() or not (extracted / "node.exe").exists():
                self.log.error(f"Extraction failed: node.exe not found in {extracted}")
                return False

            # Move to install dir
            self.node_dir.mkdir(parents=True, exist_ok=True)
            for item in extracted.iterdir():
                dest = self.node_dir / item.name
                if dest.exists():
                    if dest.is_dir():
                        shutil.rmtree(dest)
                    else:
                        dest.unlink()
                shutil.move(str(item), str(dest))

            self._node_bin = self.node_dir

            # Cleanup
            shutil.rmtree(tmp_dir, ignore_errors=True)

            # Verify
            ver = self._get_node_version(str(self.node_dir / "node.exe"))
            if ver:
                self.log.success(f"Node.js {ver} installed to {self.node_dir}")
                # Register rollback
                def _rollback_node(d=str(self.node_dir)):
                    shutil.rmtree(d, ignore_errors=True)
                self._register_rollback("删除 Node.js", _rollback_node)
                return True

            self.log.error("Node.js installed but verification failed")
            return False

        except Exception as e:
            self.log.error(f"Node.js install failed: {e}")
            return False

    def _download_with_progress(self, url: str, dest: Path):
        """Download a URL with progress logging."""
        req = urllib.request.Request(url, headers={"User-Agent": "OpenClawDeployer/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            total_mb = total / (1024 * 1024) if total else 0
            downloaded = 0
            last_pct = -1

            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(256 * 1024)  # 256KB chunks
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = int(downloaded * 100 / total)
                        if pct >= last_pct + 10:
                            self.log.info(
                                f"  Downloading… {downloaded // (1024*1024):.0f}"
                                f" / {total_mb:.0f} MB ({pct}%)")
                            last_pct = pct

        self.log.info(f"  Download complete: {downloaded // (1024*1024):.0f} MB")

    def _verify_node_sha256(self, version: str, zip_path: Path) -> bool:
        """Verify downloaded Node.js zip against official SHASUMS256.txt."""
        import json
        arch = self._get_arch()
        filename = f"node-v{version}-win-{arch}.zip"

        # Compute local hash
        sha = hashlib.sha256()
        with open(zip_path, "rb") as f:
            for chunk in iter(lambda: f.read(256 * 1024), b""):
                sha.update(chunk)
        local_hash = sha.hexdigest()

        # Fetch official SHASUMS256.txt (try nodejs.org first, then npmmirror)
        shasums_urls = [
            f"https://nodejs.org/dist/v{version}/SHASUMS256.txt",
            f"{self._node_download_base}/v{version}/SHASUMS256.txt",
        ]
        for url in shasums_urls:
            try:
                import ssl
                req = urllib.request.Request(url, headers={"User-Agent": "OpenClawDeployer/1.0"})
                try:
                    resp = urllib.request.urlopen(req, timeout=15)
                except urllib.error.URLError:
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    resp = urllib.request.urlopen(req, timeout=15, context=ctx)
                with resp:
                    shasums = resp.read().decode("utf-8")
                for line in shasums.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 2 and parts[1].strip() == filename:
                        expected = parts[0].strip()
                        if local_hash == expected:
                            self.log.success(f"SHA256 verified: {local_hash[:16]}…")
                            return True
                        else:
                            self.log.error(
                                f"SHA256 mismatch!\n"
                                f"  Expected: {expected}\n"
                                f"  Got:      {local_hash}")
                            return False
                self.log.warn(f"Filename {filename} not found in SHASUMS256 from {url}")
            except Exception as e:
                self.log.debug(f"SHASUMS256 fetch from {url} failed: {e}")
                continue

        self.log.warn("Could not fetch SHASUMS256.txt — skipping integrity check")
        return True  # Fail-open: don't block install if verification servers are down

    # ────────────────────── npm config ──────────────────────

    def setup_npm_mirror(self) -> bool:
        """Set npm registry and global prefix.

        Redirects npm's global config path via npm_config_globalconfig env var
        so that npm never touches the system npmrc (which may be under
        C:\\Program Files and need admin privileges).
        """
        registry = self.cfg.get("npm.registry", NPM_REGISTRY)
        self.log.step(f"Configuring npm registry ({registry})…")
        npm = self._get_npm_path()
        if not npm:
            self.log.error("npm not found")
            return False
        try:
            env = self._get_env()

            # Set prefix so `npm install -g` puts openclaw.cmd in our dir
            try:
                self._run(
                    [npm, "config", "set", "prefix", str(self.node_dir)],
                    capture_output=True, timeout=30, env=env,
                )
            except Exception:
                pass

            r = self._run(
                [npm, "config", "set", "registry", registry],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=30, env=env,
            )
            if r.returncode != 0:
                self.log.error(f"npm config set failed: {r.stderr.strip()}")
                return False

            # Verify
            r2 = self._run(
                [npm, "config", "get", "registry"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=10, env=env,
            )
            actual = r2.stdout.strip().rstrip("/")
            expected = registry.rstrip("/")
            if actual == expected:
                self.log.success(f"npm registry → {actual}  ✓")
            else:
                self.log.warn(f"npm registry set to {actual} (expected {expected})")

            # Register rollback
            def _rollback_npm_mirror(npm_path=npm, env_copy=env.copy()):
                try:
                    WindowsSetup._run(
                        [npm_path, "config", "set", "registry", "https://registry.npmjs.org/"],
                        capture_output=True, timeout=30, env=env_copy,
                    )
                except Exception:
                    pass
            self._register_rollback("重置 npm 镜像源", _rollback_npm_mirror)
            return True
        except Exception as e:
            self.log.error(f"npm config failed: {e}")
            self.log.info(f"  node_dir: {self.node_dir}")
            self.log.info(f"  node_dir exists: {self.node_dir.exists()}")
            self.log.info(f"  npm_config_globalconfig: {env.get('npm_config_globalconfig', 'NOT SET')}")
            return False

    # ────────────────────── OpenClaw ──────────────────────

    def check_openclaw_windows(self) -> bool:
        """Check if openclaw is installed on Windows and the binary exists."""
        # Must have the actual cmd/exe file, not just npm metadata
        if not self._find_openclaw_cmd():
            return False
        npm = self._get_npm_path()
        if not npm:
            return False
        try:
            env = self._get_env()
            r = self._run(
                [npm, "list", "-g", "openclaw", "--depth=0"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=30, env=env,
            )
            if "openclaw@" in r.stdout:
                version = r.stdout.strip().split("openclaw@")[-1].split()[0]
                self.log.info(f"OpenClaw found on Windows: {version}")
                return True
        except Exception:
            pass
        return False

    def ensure_execution_policy(self) -> bool:
        """Set PowerShell ExecutionPolicy to RemoteSigned for current user.

        Without this, npm.ps1 / npx.ps1 scripts cannot execute on fresh
        Windows installs where the default policy is Restricted.
        """
        self.log.step("Checking PowerShell execution policy…")
        try:
            r = self._run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-ExecutionPolicy -Scope CurrentUser"],
                capture_output=True, text=True, timeout=10,
            )
            policy = r.stdout.strip()
            if policy in ("RemoteSigned", "Unrestricted", "Bypass"):
                self.log.info(f"ExecutionPolicy already OK: {policy}")
                return True
        except Exception:
            pass

        try:
            self._run(
                ["powershell", "-NoProfile", "-Command",
                 "Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force"],
                capture_output=True, text=True, timeout=10,
            )
            self.log.success("ExecutionPolicy set to RemoteSigned")
            return True
        except Exception as e:
            self.log.warn(f"Could not set ExecutionPolicy: {e}")
            return False

    def _configure_git_https(self):
        """Rewrite git SSH URLs to HTTPS to avoid SSH key issues.

        Many npm packages reference git dependencies via ssh://git@github.com/
        which fails on machines without GitHub SSH keys (common in China).
        """
        git = shutil.which("git")
        if not git:
            return
        for pattern in [
            "ssh://git@github.com/",
            "git@github.com:",
        ]:
            try:
                self._run(
                    [git, "config", "--global",
                     f"url.https://github.com/.insteadOf", pattern],
                    capture_output=True, text=True, timeout=10,
                )
            except Exception:
                pass
        self.log.info("Configured git to use HTTPS instead of SSH for GitHub")

    def install_openclaw_windows(self) -> bool:
        """Install openclaw via npm on Windows."""
        channel = self.cfg.get("openclaw.channel", "stable")
        tag = "latest" if channel == "stable" else channel
        # Validate tag before passing to subprocess
        if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9._-]{0,60}$', tag):
            self.log.error(f"Invalid npm tag: {tag!r}")
            return False
        self.log.step(f"Installing OpenClaw on Windows (npm, tag={tag})…")

        npm = self._get_npm_path()
        if not npm:
            self.log.error("npm not found — install Node.js first")
            return False

        try:
            env = self._get_env()
            # Skip llama.cpp binary download (avoids build failures on Windows)
            env["NODE_LLAMA_CPP_SKIP_DOWNLOAD"] = "true"
            self.log.info("Set NODE_LLAMA_CPP_SKIP_DOWNLOAD=true")

            r = self._run(
                [npm, "install", "-g", f"openclaw@{tag}",
                 "--loglevel", "warn"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=900, env=env,
            )
            if r.returncode == 0:
                self.log.success("OpenClaw installed on Windows")
                self._register_rollback_openclaw(npm, env)
                return True
            # npm warnings (EBADENGINE etc.) may still succeed
            if "added" in r.stderr.lower() or "openclaw" in r.stdout.lower():
                self.log.warn(f"npm warnings: {r.stderr.strip()[-300:]}")
                self.log.success("OpenClaw installed on Windows (with warnings)")
                self._register_rollback_openclaw(npm, env)
                return True
            # Log the TAIL of stderr (actual error is at the end, not the beginning)
            err_out = r.stderr.strip()
            self.log.error(f"npm install failed (exit {r.returncode}):\n{err_out[-1000:]}")
            return False
        except Exception as e:
            self.log.error(f"OpenClaw install failed: {e}")
            return False

    def _register_rollback_openclaw(self, npm: str, env: dict):
        """Register rollback action for OpenClaw npm uninstall."""
        def _rollback_openclaw():
            try:
                WindowsSetup._run(
                    [npm, "uninstall", "-g", "openclaw"],
                    capture_output=True, timeout=120, env=env,
                )
            except Exception:
                pass
        self._register_rollback("卸载 OpenClaw", _rollback_openclaw)

    # ────────────────────── Configure + Gateway ──────────────────────

    def write_config(self) -> bool:
        """Write ~/.openclaw/openclaw.json with LiteLLM proxy as custom provider.

        Uses models.providers with openai-completions API type so OpenClaw
        routes through the LiteLLM proxy instead of direct Anthropic API.
        Also migrates any legacy config keys.
        """
        self.log.step("Writing OpenClaw configuration…")
        import json

        base_url = self.cfg.get("model.base_url", "")
        api_key = self.cfg.get("model.api_key", "")
        model_name = self.cfg.get("model.model_name", "claude-opus-4-6")
        port = self.cfg.get("gateway.port", 18789)
        bind = self.cfg.get("gateway.bind", "loopback")

        # Extract bare model id (strip provider prefix if present)
        bare_model = model_name.split("/")[-1] if "/" in model_name else model_name
        provider_model = f"litellm/{bare_model}"

        openclaw_dir = Path.home() / ".openclaw"
        openclaw_dir.mkdir(parents=True, exist_ok=True)
        config_path = openclaw_dir / "openclaw.json"

        # Load existing config if present (preserve user's other settings)
        existing = {}
        if config_path.exists():
            try:
                existing = json.loads(config_path.read_text(encoding="utf-8"))
            except Exception:
                existing = {}

        # ── Migrate legacy keys ──
        migrated = []
        if "agent" in existing:
            existing.pop("agent")
            migrated.append("removed legacy 'agent' key")
        # Remove old providers key from previous attempts
        if "providers" in existing:
            existing.pop("providers")
            migrated.append("removed invalid 'providers' key")

        if migrated:
            for m in migrated:
                self.log.info(f"  Config migration: {m}")

        # ── Gateway ──
        gw = existing.get("gateway", {})
        gw["port"] = port
        gw["bind"] = bind
        gw["mode"] = "local"
        # Ensure auth token exists (generate if missing)
        import secrets
        auth = gw.get("auth", {})
        if not auth.get("token"):
            auth["mode"] = "token"
            auth["token"] = secrets.token_hex(24)
            self.log.info(f"  Generated gateway auth token")
        gw["auth"] = auth
        existing["gateway"] = gw

        # ── Model + provider: only write when api_key is configured ──
        if api_key and base_url:
            existing["agents"] = {
                "defaults": {
                    "model": {
                        "primary": provider_model,
                    },
                },
            }

            # apiKey uses ${ENV_VAR} syntax so secrets stay in .env
            api_url = base_url.rstrip("/")
            if not api_url.endswith("/v1"):
                api_url += "/v1"

            existing["models"] = {
                "mode": "merge",
                "providers": {
                    "litellm": {
                        "baseUrl": api_url,
                        "apiKey": "${LITELLM_API_KEY}",
                        "api": "openai-completions",
                        "models": [
                            {
                                "id": bare_model,
                                "name": bare_model,
                                "reasoning": True,
                                "input": ["text", "image"],
                                "contextWindow": 200000,
                                "maxTokens": 16384,
                            }
                        ],
                    }
                },
            }
        else:
            self.log.info("  No API key/base URL configured — skipping model provider")
            # Remove any existing invalid model provider entries to prevent
            # startup errors like "Invalid option" for api field
            VALID_API_TYPES = {
                "openai-completions", "openai-responses", "openai-codex-responses",
                "anthropic-messages", "google-generative-ai", "github-copilot",
                "bedrock-converse-stream", "ollama",
            }
            providers = existing.get("models", {}).get("providers", {})
            invalid = [
                name for name, cfg in providers.items()
                if isinstance(cfg, dict) and cfg.get("api") not in VALID_API_TYPES
            ]
            for name in invalid:
                self.log.warn(f"  Removing invalid model provider '{name}' "
                              f"(api: {providers[name].get('api', '<missing>')})")
                del providers[name]
            if invalid and not providers:
                existing.pop("models", None)

        # ── Skill whitelist ──
        # Only applied when skills.enable is true in deployer config.
        if self.cfg.get("skills.enable", False):
            allow_bundled = self.cfg.get("skills.allowBundled", [])
            allow_managed = self.cfg.get("skills.allowManaged", [])

            skills_cfg = existing.get("skills", {})

            # Bundled skill restriction: allowBundled=[...] limits which built-in skills load.
            if allow_bundled:
                skills_cfg["allowBundled"] = allow_bundled
            else:
                self.log.warn("  Skill whitelist: allowBundled is empty — all bundled skills will load")

            # Managed/workspace skill restriction: OpenClaw has no native allowlist for these,
            # so we enumerate any currently known managed skills and disable the ones not
            # on the whitelist via entries.<name>.enabled=false in openclaw.json.
            # An empty allowManaged list with enable=true disables ALL managed/workspace skills.
            if allow_managed is not None:
                entries = skills_cfg.get("entries", {})
                # Skills in the whitelist: ensure enabled=true.
                for name in allow_managed:
                    entry = entries.get(name, {})
                    entry["enabled"] = True
                    entries[name] = entry
                # Skills already tracked in entries that are NOT in the whitelist: disable.
                for name in list(entries.keys()):
                    if name not in allow_managed:
                        entries[name]["enabled"] = False
                skills_cfg["entries"] = entries

            existing["skills"] = skills_cfg
            self.log.info(
                f"  Skill whitelist: bundled={allow_bundled or 'all'}, "
                f"managed={allow_managed if allow_managed else 'none allowed'}"
            )
        else:
            self.log.info("  Skill whitelist: disabled (skills.enable=false in deployer config)")

        try:
            config_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
            self.log.success(f"Config written to {config_path}")
            if api_key and base_url:
                self.log.info(f"  Model: {provider_model}")
                self.log.info(f"  Provider: litellm → {api_url}")
                self.log.info(f"  API type: openai-completions")
            else:
                self.log.info("  Model provider not configured — configure later in desktop app")
        except Exception as e:
            self.log.error(f"Config write failed: {e}")
            return False

        # ── Skill catalog (certification metadata for desktop app) ──
        catalog_path = openclaw_dir / "skill_catalog.json"
        try:
            catalog_path.write_text(
                json.dumps(export_catalog_json(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self.log.success(f"Skill catalog written to {catalog_path}")
        except Exception as e:
            self.log.warn(f"Skill catalog write failed (non-fatal): {e}")

        # ── .env file (secrets) — only write if api_key is set ──
        env_path = openclaw_dir / ".env"
        if api_key:
            try:
                env_path.write_text(
                    f"LITELLM_API_KEY={api_key}\n",
                    encoding="utf-8",
                )
                self.log.success(f"Environment written to {env_path}")
            except Exception as e:
                self.log.warn(f"Env file write: {e}")

        # Register rollback
        def _rollback_config(cp=str(config_path), ep=str(env_path)):
            for p in (cp, ep):
                try:
                    Path(p).unlink(missing_ok=True)
                except Exception:
                    pass
        self._register_rollback("删除配置文件", _rollback_config)

        return True

    def run_onboard(self) -> bool:
        """Install gateway scheduled task via openclaw daemon install (elevated)."""
        self.log.step("Installing gateway service…")
        cmd = self._find_openclaw_cmd()
        if not cmd:
            self.log.error("openclaw not found")
            return False

        env = self._get_env()
        api_key = self.cfg.get("model.api_key", "")
        if api_key:
            env["LITELLM_API_KEY"] = api_key

        # Always elevate — schtasks create requires admin
        # Remove + install are combined into one elevated script to avoid double UAC prompt
        try:
            openclaw_path = cmd[0]
            tmp_script = Path(tempfile.mktemp(suffix=".ps1", prefix="openclaw_gw_"))
            lines = [
                "# Remove existing scheduled task to avoid conflicts",
                "try {",
                "    $existing = Get-ScheduledTask -TaskName 'OpenClaw Gateway' -ErrorAction SilentlyContinue",
                "    if ($existing) {",
                "        Unregister-ScheduledTask -TaskName 'OpenClaw Gateway' -Confirm:$false",
                "    }",
                "} catch {}",
                "",
            ]
            if api_key:
                lines.append(f'$env:LITELLM_API_KEY = "{api_key}"')
            lines += [
                f'& "{openclaw_path}" daemon install',
                '',
                '# Set scheduled task to run in background (no cmd window)',
                "try {",
                "    $task = Get-ScheduledTask -TaskName 'OpenClaw Gateway' -ErrorAction Stop",
                "    $task.Principal.LogonType = 'S4U'",
                "    $task.Settings.Hidden = $true",
                "    Set-ScheduledTask -InputObject $task | Out-Null",
                "} catch {}",
                'exit 0',
            ]
            tmp_script.write_text("\n".join(lines), encoding="utf-8")

            self.log.info('  请在 UAC 弹窗中点击「是」以授权安装…')
            self._run(
                ["powershell", "-Command",
                 f'Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden '
                 f'-ArgumentList \'-ExecutionPolicy\', \'Bypass\', \'-File\', \'"{tmp_script}"\''],
                capture_output=True, timeout=90,
            )
            tmp_script.unlink(missing_ok=True)
            self.log.success("Gateway service installed")
            # Register rollback
            def _rollback_gateway_task():
                try:
                    WindowsSetup._run(
                        ["powershell", "-Command",
                         "Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden "
                         "-ArgumentList '-Command', 'Unregister-ScheduledTask -TaskName ''OpenClaw Gateway'' -Confirm:$false'"],
                        capture_output=True, timeout=30,
                    )
                except Exception:
                    pass
            self._register_rollback("删除网关计划任务", _rollback_gateway_task)
            return True
        except Exception as e:
            self.log.error(f"Gateway install failed: {e}")
            return False

    def _remove_existing_gateway_task(self):
        """Delete existing 'OpenClaw Gateway' scheduled task if present."""
        try:
            r = self._run(
                ["powershell", "-Command",
                 "Get-ScheduledTask -TaskName 'OpenClaw Gateway' -ErrorAction SilentlyContinue"],
                capture_output=True, text=True, timeout=15,
            )
            if not r.stdout.strip():
                return  # task does not exist
        except Exception:
            return

        self.log.info("  Removing existing 'OpenClaw Gateway' scheduled task…")
        try:
            self._run(
                ["powershell", "-Command",
                 "Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden "
                 "-ArgumentList '-Command', 'Unregister-ScheduledTask -TaskName ''OpenClaw Gateway'' -Confirm:$false'"],
                capture_output=True, timeout=30,
            )
        except Exception:
            pass

    def _fix_gateway_task_background(self):
        """Set the OpenClaw Gateway scheduled task to run in background."""
        try:
            self._run(
                ["powershell", "-Command",
                 "$task = Get-ScheduledTask -TaskName 'OpenClaw Gateway' -ErrorAction Stop; "
                 "$task.Principal.LogonType = 'S4U'; "
                 "$task.Settings.Hidden = $true; "
                 "Set-ScheduledTask -InputObject $task | Out-Null"],
                capture_output=True, timeout=15,
            )
            self.log.info("  Scheduled task set to background mode")
        except Exception:
            pass

    def start_gateway(self) -> bool:
        """Start gateway via daemon stop + daemon start and open dashboard."""
        self.log.step("Starting OpenClaw gateway…")
        cmd = self._find_openclaw_cmd()
        if not cmd:
            self.log.error("openclaw not found")
            return False

        env = self._get_env()
        api_key = self.cfg.get("model.api_key", "")
        if api_key:
            env["LITELLM_API_KEY"] = api_key

        port = self.cfg.get("gateway.port", 18789)

        # Read token from config
        import json
        config_path = Path.home() / ".openclaw" / "openclaw.json"
        self._gateway_token = ""
        try:
            cfg_data = json.loads(config_path.read_text(encoding="utf-8"))
            self._gateway_token = cfg_data.get("gateway", {}).get("auth", {}).get("token", "")
        except Exception:
            pass

        try:
            # Stop any running gateway first
            try:
                self._run(
                    cmd + ["daemon", "stop"],
                    capture_output=True, timeout=10, env=env,
                )
            except Exception:
                pass

            time.sleep(1)

            # Try daemon start first (works if scheduled task exists)
            # Fall back to direct gateway process if no task installed
            started = False
            r = self._run(
                cmd + ["daemon", "start"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=30, env=env,
            )
            if r.returncode == 0:
                self.log.info("  Gateway started via daemon")
                started = True
            else:
                self.log.info("  daemon start failed, starting gateway directly…")

            # Check if gateway is reachable after daemon start
            if started:
                time.sleep(3)
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=2):
                        pass  # reachable
                except (ConnectionRefusedError, OSError):
                    started = False
                    self.log.info("  daemon started but gateway not reachable, trying direct start…")

            # Direct start as background process (no scheduled task needed)
            if not started:
                import subprocess as _sp
                gw_proc = _sp.Popen(
                    cmd + ["gateway"],
                    env=env,
                    stdout=_sp.DEVNULL, stderr=_sp.DEVNULL,
                    creationflags=_sp.CREATE_NO_WINDOW | _sp.DETACHED_PROCESS,
                )
                self.log.info(f"  Gateway started directly (pid={gw_proc.pid})")

            dashboard_url = f"http://127.0.0.1:{port}/"
            self._dashboard_url = dashboard_url
            open_url = dashboard_url
            if self._gateway_token:
                open_url = f"{dashboard_url}#token={self._gateway_token}"

            # Wait for gateway to be reachable
            self.log.info("  Waiting for gateway to be ready…")
            ready = False
            for i in range(15):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=1):
                        ready = True
                        break
                except (ConnectionRefusedError, OSError):
                    time.sleep(1)

            if ready:
                self.log.success("Gateway is ready!")
                self.log.info(f"  ★ Dashboard: {open_url}")
                import webbrowser
                webbrowser.open(open_url)
            else:
                self.log.warn("Gateway did not become reachable in 15s")
                self.log.info(f"  Try manually: {open_url}")

            # Register rollback
            def _rollback_gateway_stop(c=cmd, e=env):
                try:
                    WindowsSetup._run(c + ["daemon", "stop"], capture_output=True, timeout=10, env=e)
                except Exception:
                    pass
            self._register_rollback("停止网关", _rollback_gateway_stop)

            return ready
        except Exception as e:
            self.log.error(f"Gateway start failed: {e}")
            return False

    # ────────────────────── Desktop Client ──────────────────────

    def _find_local_desktop_zip(self) -> Path | None:
        """Look for a bundled desktop zip in _MEIPASS, next to exe, or CWD."""
        import sys
        candidates = []
        # Bundled inside PyInstaller exe (_MEIPASS)
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            candidates.append(Path(sys._MEIPASS) / "microclaw-portable.zip")
        # Next to the exe (distribution scenario)
        if getattr(sys, 'frozen', False):
            candidates.append(Path(sys.executable).parent / "microclaw-portable.zip")
        # CWD (development scenario)
        candidates.append(Path.cwd() / "microclaw-portable.zip")
        candidates.append(Path.cwd() / "dist" / "microclaw-portable.zip")
        for p in candidates:
            if p.exists():
                return p
        return None

    def install_desktop_client(self) -> bool:
        """Install MicroClawDesktop (Electron portable).

        Priority: local zip next to exe > network download.
        """
        install_dir = DEFAULT_DESKTOP_DIR

        # If already installed, overwrite with bundled version
        exe_path = install_dir / "MicroClawDesktop.exe"
        if exe_path.exists():
            self.log.info("检测到已有桌面客户端，将覆盖更新…")
            # Kill running MicroClawDesktop.exe to release file locks
            try:
                self._run(
                    ["taskkill", "/F", "/IM", "MicroClawDesktop.exe"],
                    capture_output=True, timeout=10,
                )
                time.sleep(1)
            except Exception:
                pass
            shutil.rmtree(install_dir, ignore_errors=True)

        # 1. Try local bundled zip
        local_zip = self._find_local_desktop_zip()
        if local_zip:
            self.log.step(f"从本地安装桌面客户端 ({local_zip.name})…")
            return self._extract_desktop_zip(local_zip, install_dir)

        # 2. Try network download
        download_url = self.cfg.get("desktop.download_url", "")
        if not download_url:
            self.log.warn("未找到本地桌面客户端包，也未配置下载地址，跳过客户端安装")
            return True  # Non-fatal

        if not download_url.startswith(("https://", "http://")):
            self.log.error(f"Invalid desktop download URL: {download_url!r}")
            return False

        self.log.step("下载 MicroClawDesktop 桌面客户端…")
        try:
            tmp_dir = Path(tempfile.mkdtemp(prefix="microclaw_"))
            zip_path = tmp_dir / "microclaw.zip"
            self._download_with_progress(download_url, zip_path)
            result = self._extract_desktop_zip(zip_path, install_dir)
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return result
        except Exception as e:
            self.log.error(f"桌面客户端下载失败: {e}")
            return False

    def _extract_desktop_zip(self, zip_path: Path, install_dir: Path) -> bool:
        """Extract a desktop client zip to install_dir."""
        if not zipfile.is_zipfile(zip_path):
            self.log.error("文件不是有效的 zip 包")
            return False

        self.log.step("解压桌面客户端…")
        install_dir.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(install_dir)
        except Exception as e:
            self.log.error(f"解压失败: {e}")
            return False

        exe_path = install_dir / "MicroClawDesktop.exe"

        # electron-builder portable may nest inside a subfolder
        # e.g. "win-unpacked/" — detect and flatten if needed
        subdirs = [d for d in install_dir.iterdir() if d.is_dir()]
        if not exe_path.exists() and len(subdirs) == 1:
            nested_exe = subdirs[0] / "MicroClawDesktop.exe"
            if nested_exe.exists():
                for item in subdirs[0].iterdir():
                    dest = install_dir / item.name
                    if dest.exists():
                        if dest.is_dir():
                            shutil.rmtree(dest)
                        else:
                            dest.unlink()
                    shutil.move(str(item), str(dest))
                subdirs[0].rmdir()

        if exe_path.exists():
            self.log.success(f"桌面客户端安装到 {install_dir}")
            def _rollback_desktop(d=str(install_dir)):
                shutil.rmtree(d, ignore_errors=True)
            self._register_rollback("删除桌面客户端", _rollback_desktop)
            return True

        # Try to find exe with different name
        exes = list(install_dir.glob("*.exe"))
        if exes:
            self.log.success(f"桌面客户端安装到 {install_dir} (exe: {exes[0].name})")
            def _rollback_desktop(d=str(install_dir)):
                shutil.rmtree(d, ignore_errors=True)
            self._register_rollback("删除桌面客户端", _rollback_desktop)
            return True

        self.log.error("解压后未找到可执行文件")
        shutil.rmtree(install_dir, ignore_errors=True)
        return False

    def _find_desktop_exe(self) -> Path | None:
        """Find the desktop client exe."""
        install_dir = DEFAULT_DESKTOP_DIR
        # Primary name
        exe = install_dir / "MicroClawDesktop.exe"
        if exe.exists():
            return exe
        # Fallback: any exe in the directory
        exes = list(install_dir.glob("*.exe"))
        return exes[0] if exes else None

    def create_desktop_shortcut(self) -> bool:
        """Create a desktop shortcut for the MicroClawDesktop client.

        If the Electron client is installed, create a .lnk pointing to it.
        Otherwise, fall back to a .url shortcut opening the gateway dashboard.
        """
        self.log.step("Creating desktop shortcut…")

        desktop = self._get_desktop_path()
        desktop_exe = self._find_desktop_exe()

        if desktop_exe:
            return self._create_lnk_shortcut(desktop, desktop_exe)
        else:
            self.log.info("桌面客户端未安装，创建浏览器快捷方式作为备选")
            return self._create_url_shortcut(desktop)

    def _get_desktop_path(self) -> Path:
        """Resolve the user's Desktop folder path."""
        desktop = Path.home() / "Desktop"
        if not desktop.exists():
            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
                )
                desktop_val, _ = winreg.QueryValueEx(key, "Desktop")
                winreg.CloseKey(key)
                desktop = Path(os.path.expandvars(desktop_val))
            except Exception:
                pass
        return desktop

    def _create_lnk_shortcut(self, desktop: Path, target_exe: Path) -> bool:
        """Create a proper .lnk shortcut to the Electron app via PowerShell."""
        shortcut_path = desktop / "MicroClawDesktop.lnk"
        # Remove stale .url shortcut if exists
        stale_url = desktop / "OpenClaw.url"
        stale_url.unlink(missing_ok=True)
        stale_lnk = desktop / "OpenClaw.lnk"
        stale_lnk.unlink(missing_ok=True)

        try:
            # Find icon
            ico_path = self._resolve_icon()
            ico_arg = ""
            if ico_path:
                ico_arg = f'$s.IconLocation = "{ico_path},0";'

            ps_script = (
                f'$ws = New-Object -ComObject WScript.Shell;'
                f'$s = $ws.CreateShortcut("{shortcut_path}");'
                f'$s.TargetPath = "{target_exe}";'
                f'$s.WorkingDirectory = "{target_exe.parent}";'
                f'$s.Description = "MicroClawDesktop";'
                f'{ico_arg}'
                f'$s.Save()'
            )
            self._run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True, timeout=15,
            )

            if shortcut_path.exists():
                self.log.success(f"Desktop shortcut created: {shortcut_path}")
                def _rollback_shortcut(p=str(shortcut_path)):
                    try:
                        Path(p).unlink(missing_ok=True)
                    except Exception:
                        pass
                self._register_rollback("删除桌面快捷方式", _rollback_shortcut)
                return True

            self.log.warn("PowerShell shortcut creation returned but .lnk not found")
            return self._create_url_shortcut(desktop)

        except Exception as e:
            self.log.warn(f"LNK shortcut failed ({e}), falling back to URL shortcut")
            return self._create_url_shortcut(desktop)

    def _create_url_shortcut(self, desktop: Path) -> bool:
        """Fallback: create a .url shortcut to the gateway dashboard."""
        port = self.cfg.get("gateway.port", 18789)

        import json
        config_path = Path.home() / ".openclaw" / "openclaw.json"
        token = ""
        try:
            cfg_data = json.loads(config_path.read_text(encoding="utf-8"))
            token = cfg_data.get("gateway", {}).get("auth", {}).get("token", "")
        except Exception:
            pass

        url = f"http://127.0.0.1:{port}/"
        if token:
            url += f"#token={token}"

        shortcut_path = desktop / "MicroClawDesktop.url"
        try:
            content = f"[InternetShortcut]\nURL={url}\nIconIndex=0\n"
            ico_path = self._resolve_icon()
            if ico_path:
                content = f"[InternetShortcut]\nURL={url}\nIconFile={ico_path}\nIconIndex=0\n"
            shortcut_path.write_text(content, encoding="utf-8")
            self.log.success(f"Desktop shortcut created: {shortcut_path}")
            def _rollback_shortcut(p=str(shortcut_path)):
                try:
                    Path(p).unlink(missing_ok=True)
                except Exception:
                    pass
            self._register_rollback("删除桌面快捷方式", _rollback_shortcut)
            return True
        except Exception as e:
            self.log.warn(f"Could not create desktop shortcut: {e}")
            return True  # Non-fatal

    # ────────────────────── Uninstall ──────────────────────

    def uninstall(self) -> bool:
        """Full uninstall: stop services, run openclaw uninstall, clean up."""
        env = self._get_env()
        cmd = self._find_openclaw_cmd()

        # 1. Stop daemon
        if cmd:
            self.log.step("停止守护进程…")
            try:
                self._run(cmd + ["daemon", "stop"],
                          capture_output=True, timeout=15, env=env)
            except Exception:
                pass

        # 2. Stop gateway
        if cmd:
            self.log.step("停止网关服务…")
            try:
                self._run(cmd + ["gateway", "stop"],
                          capture_output=True, timeout=15, env=env)
            except Exception:
                pass

        # 3. Kill desktop clients (both MicroClaw and official OpenClaw)
        self.log.step("关闭桌面客户端…")
        for exe in ("MicroClawDesktop.exe", "OpenClaw.exe"):
            try:
                self._run(["taskkill", "/F", "/IM", exe],
                          capture_output=True, timeout=10)
            except Exception:
                pass
        time.sleep(1)

        # 4. openclaw uninstall --all --yes --non-interactive
        uninstalled = False
        if cmd:
            self.log.step("执行 openclaw uninstall…")
            try:
                r = self._run(
                    cmd + ["uninstall", "--all", "--yes", "--non-interactive"],
                    capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=120, env=env,
                )
                if r.returncode == 0:
                    uninstalled = True
                    self.log.success("openclaw uninstall 完成")
            except Exception as e:
                self.log.warn(f"openclaw uninstall 失败: {e}")

        # 5. Fallback: npx
        if not uninstalled:
            self.log.step("使用 npx 执行卸载…")
            npx = self._find_npx()
            if npx:
                try:
                    self._run(
                        npx + ["-y", "openclaw", "uninstall", "--all", "--yes", "--non-interactive"],
                        capture_output=True, text=True, encoding="utf-8",
                        errors="replace", timeout=120, env=env,
                    )
                    self.log.success("npx openclaw uninstall 完成")
                except Exception as e:
                    self.log.warn(f"npx 卸载失败: {e}")

        # 6. npm uninstall -g openclaw
        self.log.step("卸载 openclaw 命令…")
        npm = self._get_npm_path()
        if npm:
            try:
                self._run(
                    [npm, "uninstall", "-g", "openclaw"],
                    capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=120, env=env,
                )
                self.log.success("npm uninstall -g openclaw 完成")
            except Exception as e:
                self.log.warn(f"npm uninstall openclaw 失败: {e}")

        # 7. Remove .openclaw-node and clean PATH
        self.log.step("清理 Node 环境…")
        node_dir = self.node_dir
        if node_dir.exists():
            self._remove_from_system_path(str(node_dir))
            shutil.rmtree(node_dir, ignore_errors=True)
            self.log.info(f"  已删除 {node_dir}")

        # 8. Remove official OpenClaw desktop app if present
        official_dir = Path.home() / "AppData" / "Local" / "Programs" / "OpenClaw"
        if official_dir.exists():
            self.log.step("清理官方 OpenClaw 客户端…")
            # Run its uninstaller silently if available
            uninstaller = official_dir / "Uninstall OpenClaw.exe"
            if uninstaller.exists():
                try:
                    self._run(
                        [str(uninstaller), "/S"],
                        capture_output=True, timeout=60,
                    )
                    self.log.success("官方 OpenClaw 卸载程序已执行")
                    time.sleep(2)
                except Exception as e:
                    self.log.warn(f"官方卸载程序执行失败: {e}")
            # Clean up remnants
            runtime_bin = official_dir / "resources" / "runtime" / "bin"
            if runtime_bin.exists():
                self._remove_from_system_path(str(runtime_bin))
            if official_dir.exists():
                shutil.rmtree(official_dir, ignore_errors=True)
                self.log.info(f"  已删除 {official_dir}")

        # 10. Remove desktop client
        self.log.step("删除桌面客户端…")
        install_dir = DEFAULT_DESKTOP_DIR
        if install_dir.exists():
            shutil.rmtree(install_dir, ignore_errors=True)
            self.log.info(f"  已删除 {install_dir}")

        # 11. Remove ~/.openclaw config directory
        self.log.step("清理配置目录…")
        openclaw_config = Path.home() / ".openclaw"
        if openclaw_config.exists():
            shutil.rmtree(openclaw_config, ignore_errors=True)
            self.log.info(f"  已删除 {openclaw_config}")

        # 12. Remove desktop shortcuts
        self.log.step("删除快捷方式…")
        desktop = self._get_desktop_path()
        for name in ("MicroClawDesktop.lnk", "MicroClawDesktop.url",
                      "MicroClaw.lnk", "MicroClaw.url",
                      "OpenClaw.lnk", "OpenClaw.url"):
            p = desktop / name
            if p.exists():
                p.unlink(missing_ok=True)
                self.log.info(f"  已删除 {p.name}")

        self.log.success("卸载完成")
        return True

    def _find_npx(self) -> list[str] | None:
        """Find npx executable."""
        for search_dir in filter(None, [self._node_bin, self.node_dir]):
            for name in ("npx.cmd", "npx"):
                p = search_dir / name
                if p.exists():
                    return [str(p)]
        found = shutil.which("npx")
        if found:
            return [found]
        return None

    def _resolve_icon(self) -> Path | None:
        """Find and ensure microclaw.ico is in ~/.openclaw/."""
        import sys
        target_ico = Path.home() / ".openclaw" / "microclaw.ico"
        if target_ico.exists():
            return target_ico
        candidates = [
            Path(__file__).parent.parent / "microclaw.ico",
        ]
        if getattr(sys, 'frozen', False):
            candidates.insert(0, Path(sys._MEIPASS) / "microclaw.ico")
            candidates.insert(1, Path(sys.executable).parent / "microclaw.ico")
        for ico in candidates:
            if ico.exists():
                target_ico.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ico, target_ico)
                return target_ico
        return None

    def _find_openclaw_cmd(self) -> list[str] | None:
        """Find openclaw executable on Windows.

        Prefer .cmd over bare name to avoid .ps1 execution-policy issues.
        """
        # Managed node dir (always check, even if _node_bin not set)
        for search_dir in filter(None, [self._node_bin, self.node_dir]):
            for name in ("openclaw.cmd", "openclaw.exe", "openclaw"):
                p = search_dir / name
                if p.exists():
                    return [str(p)]
        # npm global
        npm_prefix = Path.home() / "AppData" / "Roaming" / "npm"
        for name in ("openclaw.cmd", "openclaw.exe", "openclaw"):
            p = npm_prefix / name
            if p.exists():
                return [str(p)]
        # System PATH — prefer .cmd to avoid .ps1
        for ext in (".cmd", ".exe", ""):
            found = shutil.which(f"openclaw{ext}")
            if found:
                return [found]
        return None

    # ────────────────────── helpers ──────────────────────

    def _get_env(self) -> dict:
        """Return env dict with our managed node + git in PATH.

        Also redirects npm's global config to our managed dir so npm never
        tries to read/write the system npmrc (avoids Access Denied on
        system Node.js installs under C:\\Program Files).
        """
        env = os.environ.copy()
        path_prefix = ""
        # Always put managed node dir first so our node.exe wins over system node
        if self.node_dir.exists():
            path_prefix += str(self.node_dir) + os.pathsep
        if self._node_bin and str(self._node_bin) != str(self.node_dir):
            path_prefix += str(self._node_bin) + os.pathsep
        if self._git_bin:
            path_prefix += self._git_bin + os.pathsep
        if path_prefix:
            env["PATH"] = path_prefix + env.get("PATH", "")

        # Redirect npm global config to our managed dir
        try:
            global_npmrc_dir = self.node_dir / "etc"
            global_npmrc_dir.mkdir(parents=True, exist_ok=True)
            env["npm_config_globalconfig"] = str(global_npmrc_dir / "npmrc")
        except Exception:
            # Fall back: use temp dir if node_dir/etc is not writable
            try:
                import tempfile
                fallback = Path(tempfile.gettempdir()) / "openclaw_npmrc"
                fallback.mkdir(parents=True, exist_ok=True)
                env["npm_config_globalconfig"] = str(fallback / "npmrc")
            except Exception:
                pass

        return env

    def _get_npm_path(self) -> str | None:
        """Find npm executable (prefer .cmd to avoid PS1 execution policy issues)."""
        if self._node_bin:
            npm = self._node_bin / "npm.cmd"
            if npm.exists():
                return str(npm)
            npm = self._node_bin / "npm"
            if npm.exists():
                return str(npm)
        # Prefer .cmd over .ps1 — .ps1 fails when ExecutionPolicy is Restricted
        for ext in (".cmd", ".exe", ""):
            found = shutil.which(f"npm{ext}")
            if found:
                return found
        return shutil.which("npm")

    def _get_node_version(self, node_path: str) -> str | None:
        try:
            r = self._run(
                [node_path, "--version"],
                capture_output=True, text=True, encoding="utf-8",
                timeout=10,
            )
            ver = r.stdout.strip()
            return ver if ver.startswith("v") else None
        except Exception:
            return None

    def _version_ok(self, ver: str) -> bool:
        """Check if version is >= 22.12.0 (OpenClaw minimum)."""
        try:
            parts = ver.lstrip("v").split(".")
            major = int(parts[0])
            minor = int(parts[1]) if len(parts) > 1 else 0
            if major > 22:
                return True
            if major == 22 and minor >= 12:
                return True
            return False
        except Exception:
            return False

    def add_to_path(self) -> bool:
        """Add managed node dir + npm global bin to the user's persistent PATH."""
        self.log.step("Adding Node.js & npm to system PATH…")
        import winreg

        dirs_to_add = []
        # Our managed node install
        if self.node_dir.exists():
            dirs_to_add.append(str(self.node_dir))
        # npm global bin (where openclaw.cmd lives)
        npm_global = Path.home() / "AppData" / "Roaming" / "npm"
        if npm_global.exists():
            dirs_to_add.append(str(npm_global))

        if not dirs_to_add:
            if self._node_bin and shutil.which("node"):
                self.log.info("Node.js already in PATH; no directories to add")
                return True
            self.log.warn("No directories to add to PATH")
            return False

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Environment",
                0, winreg.KEY_READ | winreg.KEY_WRITE,
            )
            current_path, _ = winreg.QueryValueEx(key, "Path")
            current_lower = current_path.lower()

            added = []
            for d in dirs_to_add:
                if d.lower() not in current_lower:
                    added.append(d)

            if not added:
                self.log.info("PATH already contains required directories")
                winreg.CloseKey(key)
                return True

            new_path = ";".join(added) + ";" + current_path.rstrip(";")
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
            winreg.CloseKey(key)

            # Broadcast WM_SETTINGCHANGE so Explorer picks it up
            try:
                import ctypes
                HWND_BROADCAST = 0xFFFF
                WM_SETTINGCHANGE = 0x001A
                ctypes.windll.user32.SendMessageTimeoutW(
                    HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", 0x0002, 5000, None)
            except Exception:
                pass

            for d in added:
                self.log.info(f"  Added to PATH: {d}")
            self.log.success("PATH updated (restart terminal to take effect)")

            # Register rollback
            def _rollback_path(dirs=list(added)):
                try:
                    import winreg
                    key = winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER, r"Environment",
                        0, winreg.KEY_READ | winreg.KEY_WRITE,
                    )
                    current, _ = winreg.QueryValueEx(key, "Path")
                    parts = [p for p in current.split(";")
                             if p.strip().lower() not in {d.lower() for d in dirs}]
                    winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, ";".join(parts))
                    winreg.CloseKey(key)
                except Exception:
                    pass
            self._register_rollback("移除 PATH 条目", _rollback_path)

            return True

        except Exception as e:
            self.log.error(f"Failed to update PATH: {e}")
            return False
