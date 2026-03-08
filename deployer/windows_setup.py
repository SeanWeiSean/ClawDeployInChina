"""Windows-native Node.js + OpenClaw installation.

Downloads Node.js from npmmirror (Chinese mirror), installs it,
configures npm to use the taobao registry, and installs openclaw.
"""

import os
import platform
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from deployer.logger import DeployerLogger

# ── Mirror URLs ──
NODE_MIRROR = "https://registry.npmmirror.com/binary.html?path=node/"
NODE_DOWNLOAD_BASE = "https://registry.npmmirror.com/-/binary/node"
NPM_REGISTRY = "https://registry.npmmirror.com"

# Default install location
DEFAULT_NODE_DIR = Path(os.environ.get(
    "OPENCLAW_NODE_DIR",
    str(Path.home() / ".openclaw-node"),
))


class WindowsSetup:
    """Handles Node.js + OpenClaw installation on Windows natively."""

    def __init__(self, config, logger: DeployerLogger):
        self.cfg = config
        self.log = logger
        self.node_version = config.get("node.version", "22")
        self.node_dir = DEFAULT_NODE_DIR
        self._node_bin: Path | None = None

    # ────────────────────── Node.js ──────────────────────

    def _get_arch(self) -> str:
        """Return 'x64' or 'arm64' based on platform."""
        machine = platform.machine().lower()
        if machine in ("amd64", "x86_64", "x64"):
            return "x64"
        if machine in ("arm64", "aarch64"):
            return "arm64"
        return "x64"

    def _get_node_download_url(self, version: str) -> str:
        """Build the download URL for Node.js Windows zip from npmmirror."""
        arch = self._get_arch()
        # npmmirror hosts Node binaries at:
        # https://registry.npmmirror.com/-/binary/node/v22.x.x/node-v22.x.x-win-x64.zip
        return f"{NODE_DOWNLOAD_BASE}/v{version}/node-v{version}-win-{arch}.zip"

    def _resolve_latest_version(self, major: str) -> str:
        """Resolve '22' to the latest specific version like '22.14.0'."""
        self.log.debug(f"Resolving latest Node.js {major}.x version…")
        import re
        import json

        # Method 1: Use nodejs.org version index (most reliable)
        try:
            url = "https://nodejs.org/dist/index.json"
            req = urllib.request.Request(url, headers={"User-Agent": "OpenClawDeployer/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
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
            url = f"{NODE_DOWNLOAD_BASE}/latest-v{major}.x/"
            req = urllib.request.Request(url, headers={"User-Agent": "OpenClawDeployer/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            arch = self._get_arch()
            pattern = rf'node-v({major}\.\d+\.\d+)-win-{arch}\.zip'
            m = re.search(pattern, html)
            if m:
                self.log.debug(f"Resolved from npmmirror: {m.group(1)}")
                return m.group(1)
        except Exception as e:
            self.log.debug(f"npmmirror resolve failed: {e}")

        # Fallback
        fallback = f"{major}.14.0"
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
        self.log.step("Installing Node.js on Windows (npmmirror)…")

        version = self._resolve_latest_version(self.node_version)
        self.log.info(f"Resolved version: v{version}")

        url = self._get_node_download_url(version)
        self.log.info(f"Downloading: {url}")

        try:
            # Download to temp
            tmp_dir = Path(tempfile.mkdtemp(prefix="openclaw_node_"))
            zip_path = tmp_dir / "node.zip"

            self._download_with_progress(url, zip_path)

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

    # ────────────────────── npm config ──────────────────────

    def setup_npm_mirror(self) -> bool:
        """Set npm registry to taobao mirror."""
        self.log.step("Configuring npm registry (taobao mirror)…")
        npm = self._get_npm_path()
        if not npm:
            self.log.error("npm not found")
            return False
        try:
            r = subprocess.run(
                [npm, "config", "set", "registry", NPM_REGISTRY],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=30,
            )
            if r.returncode == 0:
                self.log.success(f"npm registry set to {NPM_REGISTRY}")
                return True
            self.log.error(f"npm config set failed: {r.stderr.strip()}")
            return False
        except Exception as e:
            self.log.error(f"npm config failed: {e}")
            return False

    # ────────────────────── OpenClaw ──────────────────────

    def check_openclaw_windows(self) -> bool:
        """Check if openclaw is installed on Windows."""
        npm = self._get_npm_path()
        if not npm:
            return False
        try:
            env = self._get_env()
            r = subprocess.run(
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

    def install_openclaw_windows(self) -> bool:
        """Install openclaw via npm on Windows."""
        channel = self.cfg.get("openclaw.channel", "stable")
        tag = "latest" if channel == "stable" else channel
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

            r = subprocess.run(
                [npm, "install", "-g", f"openclaw@{tag}",
                 "--verbose", "--prefer-offline"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=600, env=env,
            )
            if r.returncode == 0:
                self.log.success("OpenClaw installed on Windows")
                return True
            # npm warnings (EBADENGINE etc.) may still succeed
            if "added" in r.stderr.lower() or "openclaw" in r.stdout.lower():
                self.log.warn(f"npm warnings: {r.stderr.strip()[:300]}")
                self.log.success("OpenClaw installed on Windows (with warnings)")
                return True
            self.log.error(f"npm install failed: {r.stderr.strip()[:500]}")
            return False
        except Exception as e:
            self.log.error(f"OpenClaw install failed: {e}")
            return False

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

        # ── Model: use custom provider via models.providers ──
        existing["agents"] = {
            "defaults": {
                "model": {
                    "primary": provider_model,
                },
            },
        }

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

        # ── Custom LiteLLM provider (openai-completions API) ──
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

        try:
            config_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
            self.log.success(f"Config written to {config_path}")
            self.log.info(f"  Model: {provider_model}")
            self.log.info(f"  Provider: litellm → {api_url}")
            self.log.info(f"  API type: openai-completions")
        except Exception as e:
            self.log.error(f"Config write failed: {e}")
            return False

        # ── .env file (secrets) ──
        env_path = openclaw_dir / ".env"
        try:
            env_path.write_text(
                f"LITELLM_API_KEY={api_key}\n",
                encoding="utf-8",
            )
            self.log.success(f"Environment written to {env_path}")
        except Exception as e:
            self.log.warn(f"Env file write: {e}")

        return True

    def run_onboard(self) -> bool:
        """Install gateway daemon service (entire process runs as admin)."""
        self.log.step("Installing gateway service…")
        cmd = self._find_openclaw_cmd()
        if not cmd:
            self.log.error("openclaw not found")
            return False

        env = self._get_env()
        api_key = self.cfg.get("model.api_key", "")
        if api_key:
            env["LITELLM_API_KEY"] = api_key

        try:
            # Install the gateway as a system service
            r = subprocess.run(
                cmd + ["gateway", "install"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=30, env=env,
            )
            output = r.stdout.strip()
            if output:
                self.log.info(f"Gateway install: {output[:300]}")
            stderr = r.stderr.strip()
            if stderr:
                self.log.debug(f"Gateway install stderr: {stderr[:200]}")

            if "access is denied" in (stderr + output).lower():
                self.log.error("Access denied — deployer needs to run as Administrator")
                return False

            # Run doctor --fix to auto-repair any config issues
            r2 = subprocess.run(
                cmd + ["doctor", "--fix"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=30, env=env,
            )
            if r2.stdout.strip():
                self.log.debug(f"Doctor: {r2.stdout.strip()[:200]}")

            self.log.success("Gateway service installed")
            return True
        except subprocess.TimeoutExpired:
            self.log.warn("Onboard timed out (may need interactive setup)")
            return True  # Config is already written
        except Exception as e:
            self.log.error(f"Onboard failed: {e}")
            return False

    def start_gateway(self) -> bool:
        """Start the OpenClaw gateway and open dashboard in browser."""
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

        # Read token from config BEFORE starting gateway
        import json
        config_path = Path.home() / ".openclaw" / "openclaw.json"
        self._gateway_token = ""
        try:
            cfg_data = json.loads(config_path.read_text(encoding="utf-8"))
            self._gateway_token = cfg_data.get("gateway", {}).get("auth", {}).get("token", "")
        except Exception:
            pass

        try:
            # Start gateway in background
            subprocess.Popen(
                cmd + ["gateway", "--port", str(port), "--verbose"],
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0x08000000,
            )
            self.log.success(f"Gateway starting on port {port}…")

            if self._gateway_token:
                dashboard_url = f"http://127.0.0.1:{port}/?token={self._gateway_token}"
            else:
                dashboard_url = f"http://127.0.0.1:{port}/"
            self._dashboard_url = dashboard_url

            self.log.info("")
            self.log.info(f"  ★ Dashboard: {dashboard_url}")
            self.log.info("")

            # Auto-open dashboard in browser
            import webbrowser
            webbrowser.open(dashboard_url)

            return True
        except Exception as e:
            self.log.error(f"Gateway start failed: {e}")
            return False

    def _find_openclaw_cmd(self) -> list[str] | None:
        """Find openclaw executable on Windows."""
        # Managed node dir
        if self._node_bin:
            for name in ("openclaw.cmd", "openclaw"):
                p = self._node_bin / name
                if p.exists():
                    return [str(p)]
        # npm global
        npm_prefix = Path.home() / "AppData" / "Roaming" / "npm"
        for name in ("openclaw.cmd", "openclaw"):
            p = npm_prefix / name
            if p.exists():
                return [str(p)]
        # System PATH
        found = shutil.which("openclaw")
        if found:
            return [found]
        return None

    # ────────────────────── helpers ──────────────────────

    def _get_env(self) -> dict:
        """Return env dict with our managed node in PATH."""
        env = os.environ.copy()
        if self._node_bin:
            env["PATH"] = str(self._node_bin) + os.pathsep + env.get("PATH", "")
        return env

    def _get_npm_path(self) -> str | None:
        """Find npm executable."""
        if self._node_bin:
            npm = self._node_bin / "npm.cmd"
            if npm.exists():
                return str(npm)
            npm = self._node_bin / "npm"
            if npm.exists():
                return str(npm)
        return shutil.which("npm")

    def _get_node_version(self, node_path: str) -> str | None:
        try:
            r = subprocess.run(
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

            new_path = current_path.rstrip(";") + ";" + ";".join(added)
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
            return True

        except Exception as e:
            self.log.error(f"Failed to update PATH: {e}")
            return False
