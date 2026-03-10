"""WSL2 management: detect, install, configure."""

import subprocess
import re
from deployer.logger import DeployerLogger


def _decode_wsl(raw: bytes) -> str:
    """Decode bytes from wsl.exe which may be UTF-8 or UTF-16-LE.

    wsl.exe host commands (--list, --status, --install, errors) output
    UTF-16-LE.  Commands that run *inside* a distro (bash -lc ...) output
    UTF-8.  Detect by checking for null bytes which are pervasive in
    UTF-16-LE but rare in UTF-8.
    """
    if not raw:
        return ""
    # Heuristic: if ≥10% of bytes are 0x00, it's almost certainly UTF-16-LE.
    null_ratio = raw.count(b"\x00") / max(len(raw), 1)
    if null_ratio >= 0.1:
        try:
            text = raw.decode("utf-16-le")
            # Strip stray nulls / BOM
            return text.replace("\x00", "").strip()
        except UnicodeDecodeError:
            pass
    # Otherwise treat as UTF-8
    return raw.decode("utf-8", errors="replace")


def _run_wsl_cmd(args, timeout=60, **kwargs) -> subprocess.CompletedProcess:
    """Run a wsl command and return a CompletedProcess with decoded strings."""
    r = subprocess.run(args, capture_output=True, timeout=timeout, **kwargs)
    # Manually decode
    r.stdout_text = _decode_wsl(r.stdout) if isinstance(r.stdout, bytes) else r.stdout
    r.stderr_text = _decode_wsl(r.stderr) if isinstance(r.stderr, bytes) else r.stderr
    return r


class WSLManager:
    """Handles WSL2 detection, distro install, and systemd configuration."""

    def __init__(self, config, logger: DeployerLogger):
        self.cfg = config
        self.log = logger
        self._configured_distro = config.get("wsl.distro", "Ubuntu-24.04")
        self.distro = self._configured_distro  # will be resolved to real name

    # ────────────────────── queries ──────────────────────

    def is_wsl_installed(self) -> bool:
        """Check if WSL feature is enabled."""
        try:
            r = _run_wsl_cmd(["wsl", "--status"], timeout=15)
            return r.returncode == 0
        except FileNotFoundError:
            return False
        except subprocess.TimeoutExpired:
            return False

    def list_distros(self) -> list[str]:
        """Return installed WSL distro names."""
        try:
            r = _run_wsl_cmd(["wsl", "--list", "--quiet"], timeout=15)
            return [line.strip() for line in r.stdout_text.splitlines() if line.strip()]
        except Exception:
            return []

    def _resolve_distro(self) -> str | None:
        """Find the actual installed distro name that matches the configured one.

        e.g. configured 'Ubuntu-24.04' will match installed 'Ubuntu'.
        Returns the real WSL distro name or None.
        """
        distros = self.list_distros()
        target = self._configured_distro.lower()

        # 1. Exact match
        for d in distros:
            if d.lower() == target:
                return d

        # 2. Prefix match: "Ubuntu" matches "Ubuntu-24.04" config
        #    or "Ubuntu-24.04" matches "Ubuntu" installed
        target_base = target.split("-")[0]   # "ubuntu"
        for d in distros:
            d_lower = d.lower()
            d_base = d_lower.split("-")[0]
            if d_base == target_base or d_lower.startswith(target_base):
                return d

        return None

    def is_distro_installed(self) -> bool:
        real = self._resolve_distro()
        if real:
            if real != self.distro:
                self.log.info(f"Resolved distro: configured '{self._configured_distro}' → found '{real}'")
                self.distro = real  # use the real name from now on
            return True
        return False

    def is_systemd_enabled(self) -> bool:
        """Check if systemd is configured inside WSL."""
        try:
            r = _run_wsl_cmd(
                ["wsl", "-d", self.distro, "--", "cat", "/etc/wsl.conf"],
                timeout=15,
            )
            return "systemd=true" in r.stdout_text.lower()
        except Exception:
            return False

    def get_wsl_version(self) -> str:
        """Return WSL kernel version string."""
        try:
            r = _run_wsl_cmd(["wsl", "--version"], timeout=15)
            for line in r.stdout_text.splitlines():
                if re.search(r"\d+\.\d+", line):
                    return line.strip()
            return r.stdout_text.strip()[:100]
        except Exception:
            return "unknown"

    # ────────────────────── actions ──────────────────────

    def install_wsl(self) -> bool:
        """Enable WSL feature (may require reboot)."""
        self.log.step("Installing WSL2 feature…")
        try:
            r = _run_wsl_cmd(
                ["wsl", "--install", "--no-distribution"], timeout=300,
            )
            self.log.info(f"wsl --install output: {r.stdout_text.strip()}")
            if r.returncode != 0:
                self.log.error(f"WSL install stderr: {r.stderr_text.strip()}")
                return False
            self.log.success("WSL2 feature installed")
            return True
        except Exception as e:
            self.log.error(f"Failed to install WSL: {e}")
            return False

    def install_distro(self) -> bool:
        """Install the configured Ubuntu distro."""
        self.log.step(f"Installing distro {self.distro}…")
        try:
            r = _run_wsl_cmd(
                ["wsl", "--install", "-d", self.distro], timeout=600,
            )
            self.log.info(f"Distro install output: {r.stdout_text.strip()}")
            if r.returncode != 0 and "already installed" not in r.stdout_text.lower():
                self.log.error(f"Distro install error: {r.stderr_text.strip()}")
                return False
            self.log.success(f"{self.distro} installed")
            return True
        except Exception as e:
            self.log.error(f"Failed to install distro: {e}")
            return False

    def enable_systemd(self) -> bool:
        """Write /etc/wsl.conf with systemd=true and security hardening."""
        self.log.step("Enabling systemd + security hardening in WSL…")
        # Hardened wsl.conf: systemd + restrict Windows interop
        conf_lines = [
            "[boot]",
            "systemd=true",
            "",
            "[automount]",
            "enabled=true",
            'options="metadata,umask=077"',
            "",
            "[interop]",
            "appendWindowsPath=false",
        ]
        conf_content = "\\n".join(conf_lines)
        try:
            # Check if already configured
            if self.is_systemd_enabled():
                self.log.info("systemd already enabled")
                return True

            r = _run_wsl_cmd(
                [
                    "wsl", "-d", self.distro, "--",
                    "bash", "-c",
                    f"echo -e '{conf_content}' | sudo tee /etc/wsl.conf > /dev/null"
                ],
                timeout=30,
            )
            if r.returncode != 0:
                self.log.error(f"Enable systemd error: {r.stderr_text.strip()}")
                return False
            self.log.success("systemd enabled + WSL security hardening applied")
            return True
        except Exception as e:
            self.log.error(f"Failed to enable systemd: {e}")
            return False

    def shutdown_wsl(self) -> bool:
        """Shutdown WSL to apply config (e.g. after systemd change)."""
        self.log.step("Restarting WSL (wsl --shutdown)…")
        try:
            subprocess.run(["wsl", "--shutdown"], capture_output=True, timeout=30)
            self.log.success("WSL shutdown complete")
            return True
        except Exception as e:
            self.log.error(f"WSL shutdown failed: {e}")
            return False

    def run_in_wsl(self, command: str, timeout: int = 600) -> tuple[bool, str]:
        """Run a bash command inside WSL and return (success, output)."""
        try:
            r = _run_wsl_cmd(
                ["wsl", "-d", self.distro, "--", "bash", "-lc", command],
                timeout=timeout,
            )
            output = r.stdout_text + r.stderr_text
            return r.returncode == 0, output.strip()
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, str(e)

    def setup_auto_start(self) -> bool:
        """Enable linger + create scheduled task for WSL boot."""
        self.log.step("Setting up auto-start…")
        try:
            # Enable linger inside WSL
            ok, out = self.run_in_wsl('sudo loginctl enable-linger "$(whoami)"')
            if not ok:
                self.log.warn(f"loginctl enable-linger: {out}")

            # Create Windows scheduled task (native Windows cmd, uses system encoding)
            task_cmd = (
                f'schtasks /create /tn "WSL Boot - OpenClaw" '
                f'/tr "wsl.exe -d {self.distro} --exec /bin/true" '
                f'/sc onstart /ru SYSTEM /f'
            )
            r = subprocess.run(
                task_cmd, shell=True,
                capture_output=True, timeout=30,
            )
            stderr = _decode_wsl(r.stderr)
            if r.returncode != 0:
                self.log.warn(f"Scheduled task creation: {stderr.strip()} (may need admin)")
                return False
            self.log.success("WSL auto-start scheduled task created")
            return True
        except Exception as e:
            self.log.error(f"Auto-start setup failed: {e}")
            return False
