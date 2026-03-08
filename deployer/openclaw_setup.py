"""OpenClaw installation & configuration inside WSL."""

import json
import textwrap
from deployer.logger import DeployerLogger
from deployer.wsl_manager import WSLManager

# Prefix that ensures nvm is available in non-interactive shells.
_NVM = 'export NVM_DIR="$HOME/.nvm" && [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"'


class OpenClawSetup:
    """Installs Node, pnpm, OpenClaw and writes config inside WSL."""

    def __init__(self, config, wsl: WSLManager, logger: DeployerLogger):
        self.cfg = config
        self.wsl = wsl
        self.log = logger

    def _run(self, cmd: str, timeout: int = 300) -> tuple[bool, str]:
        """Run a command inside WSL, auto-sourcing nvm if installed."""
        full = f'{_NVM} 2>/dev/null; {cmd}'
        return self.wsl.run_in_wsl(full, timeout=timeout)

    # ────────────────────── Node.js ──────────────────────

    def check_node(self) -> bool:
        ok, out = self._run("node --version 2>/dev/null")
        if ok:
            for line in out.strip().splitlines():
                line = line.strip()
                if line.startswith("v"):
                    parts = line.lstrip("v").split(".")
                    major = int(parts[0])
                    minor = int(parts[1]) if len(parts) > 1 else 0
                    self.log.info(f"Node.js found: {line}")
                    return (major > 22) or (major == 22 and minor >= 12)
        return False

    def install_node(self) -> bool:
        method = self.cfg.get("node.install_method", "nvm")
        version = self.cfg.get("node.version", "22")

        if method == "nvm":
            return self._install_node_nvm(version)
        return self._install_node_nodesource(version)

    def _install_node_nvm(self, version: str) -> bool:
        self.log.step(f"Installing Node.js {version} via nvm…")

        # Step 1: Install nvm itself
        ok, out = self.wsl.run_in_wsl(
            'curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash',
            timeout=120,
        )
        self.log.debug(out[:400])
        # nvm install script may return non-zero even on success, check if it exists
        ok_check, _ = self.wsl.run_in_wsl('[ -s "$HOME/.nvm/nvm.sh" ]')
        if not ok_check:
            self.log.error(f"nvm installation failed: {out[:500]}")
            return False
        self.log.info("nvm installed")

        # Step 2: Install node (source nvm explicitly)
        ok, out = self._run(
            f'nvm install {version} && nvm alias default {version}',
            timeout=300,
        )
        self.log.debug(out[:400])

        # Step 3: Create symlinks so node/npm/npx are in PATH for non-interactive shells
        self._run(
            f'NVM_NODE=$(nvm which {version}) && '
            'NVM_DIR_BIN=$(dirname "$NVM_NODE") && '
            'sudo ln -sf "$NVM_DIR_BIN/node" /usr/local/bin/node && '
            'sudo ln -sf "$NVM_DIR_BIN/npm" /usr/local/bin/npm && '
            'sudo ln -sf "$NVM_DIR_BIN/npx" /usr/local/bin/npx && '
            'sudo ln -sf "$NVM_DIR_BIN/corepack" /usr/local/bin/corepack',
            timeout=30,
        )

        # Verify
        ok, out = self._run("node --version")
        out = out.strip().splitlines()[-1] if out.strip() else ""
        if out.startswith("v"):
            parts = out.lstrip("v").split(".")
            major = int(parts[0])
            minor = int(parts[1]) if len(parts) > 1 else 0
            if (major > 22) or (major == 22 and minor >= 12):
                self.log.success(f"Node.js installed: {out}")
                return True
            self.log.error(f"Node.js {out} installed but need >= 22.12")
            return False
        self.log.error(f"Node verification failed: {out}")
        return False

    def _install_node_nodesource(self, version: str) -> bool:
        self.log.step(f"Installing Node.js {version} via NodeSource…")
        cmd = (
            f'curl -fsSL https://deb.nodesource.com/setup_{version}.x | sudo -E bash - '
            f'&& sudo apt-get install -y nodejs'
        )
        ok, out = self.wsl.run_in_wsl(cmd, timeout=300)
        if not ok:
            self.log.error(f"NodeSource install failed: {out[:500]}")
            return False
        self.log.success("Node.js installed via NodeSource")
        return True

    # ────────────────────── pnpm ──────────────────────

    def check_pnpm(self) -> bool:
        ok, out = self._run("pnpm --version 2>/dev/null")
        if ok and out.strip():
            self.log.info(f"pnpm found: {out.strip().splitlines()[-1]}")
            return True
        return False

    def install_pnpm(self) -> bool:
        self.log.step("Installing pnpm…")
        ok, out = self._run(
            'corepack enable && corepack prepare pnpm@latest --activate 2>/dev/null || npm install -g pnpm',
            timeout=120,
        )
        if not ok:
            self.log.warn(f"pnpm install corepack path: {out[:300]}, trying npm fallback…")
            ok, out = self._run("npm install -g pnpm", timeout=120)
        if ok:
            self.log.success("pnpm installed")
        else:
            self.log.error(f"pnpm install failed: {out[:300]}")
        return ok

    # ────────────────────── OpenClaw ──────────────────────

    def check_openclaw(self) -> bool:
        ok, out = self._run("openclaw --version 2>/dev/null")
        if ok and out.strip():
            self.log.info(f"OpenClaw found: {out.strip().splitlines()[-1]}")
            return True
        return False

    def install_openclaw(self) -> bool:
        method = self.cfg.get("openclaw.install_method", "npm")
        channel = self.cfg.get("openclaw.channel", "stable")

        if method == "npm":
            return self._install_openclaw_npm(channel)
        return self._install_openclaw_source()

    def _install_openclaw_npm(self, channel: str) -> bool:
        tag = "latest" if channel == "stable" else channel
        self.log.step(f"Installing OpenClaw via npm (tag={tag})…")
        ok, out = self._run(f"npm install -g openclaw@{tag}", timeout=300)
        if ok:
            self.log.success("OpenClaw installed via npm")
        else:
            self.log.error(f"npm install openclaw failed: {out[:500]}")
        return ok

    def _install_openclaw_source(self) -> bool:
        self.log.step("Installing OpenClaw from source…")
        commands = [
            "git clone https://github.com/openclaw/openclaw.git ~/openclaw-src",
            "cd ~/openclaw-src && pnpm install",
            "cd ~/openclaw-src && pnpm ui:build",
            "cd ~/openclaw-src && pnpm build",
        ]
        for cmd in commands:
            self.log.debug(f"Running: {cmd}")
            ok, out = self._run(cmd, timeout=600)
            if not ok:
                self.log.error(f"Source build failed at: {cmd}\n{out[:500]}")
                return False
        self.log.success("OpenClaw built from source")
        return True

    # ────────────────────── Configuration ──────────────────────

    def write_openclaw_config(self) -> bool:
        """Write ~/.openclaw/openclaw.json with model + gateway settings.

        Reads existing config first, migrates legacy keys, then writes.
        """
        self.log.step("Writing OpenClaw configuration…")

        base_url = self.cfg.get("model.base_url", "")
        api_key = self.cfg.get("model.api_key", "")
        model_name = self.cfg.get("model.model_name", "claude-opus-4-6")
        port = self.cfg.get("gateway.port", 18789)
        bind = self.cfg.get("gateway.bind", "loopback")

        # Read existing config, migrate legacy keys, write clean config
        migrate_and_write = textwrap.dedent(f"""\
            mkdir -p ~/.openclaw
            CONF=~/.openclaw/openclaw.json
            # Remove legacy 'agent' key from existing config if present
            if [ -f "$CONF" ] && command -v python3 >/dev/null 2>&1; then
                python3 -c "
import json, sys
try:
    c = json.load(open('$CONF'))
    changed = False
    if 'agent' in c:
        del c['agent']
        changed = True
    if changed:
        json.dump(c, open('$CONF','w'), indent=2)
        print('Migrated legacy config keys')
except: pass
" 2>/dev/null
            fi
            cat > "$CONF" << 'OCEOF'
            {json.dumps({"agents": {"defaults": {"model": {"primary": model_name}}}, "gateway": {"port": port, "bind": bind}}, indent=2)}
            OCEOF
        """)
        ok, out = self.wsl.run_in_wsl(migrate_and_write)
        if not ok:
            self.log.error(f"Config write failed: {out}")
            return False
        if "Migrated" in out:
            self.log.info("  Config migration: removed legacy 'agent' key")

        # Write environment variables for the LiteLLM proxy
        env_script = textwrap.dedent(f"""\
            mkdir -p ~/.openclaw
            cat >> ~/.bashrc << 'ENVEOF'

            # OpenClaw LiteLLM Proxy Configuration
            export ANTHROPIC_BASE_URL="{base_url}"
            export ANTHROPIC_API_KEY="{api_key}"
            export ANTHROPIC_AUTH_TOKEN="{api_key}"
            ENVEOF
        """)
        ok, out = self.wsl.run_in_wsl(env_script)
        if not ok:
            self.log.error(f"Env var write failed: {out}")
            return False

        self.log.success("OpenClaw config + environment written")
        return True

    # ────────────────────── Onboard / Daemon ──────────────────────

    def run_onboard(self) -> bool:
        """Run openclaw onboard (non-interactive parts)."""
        self.log.step("Running OpenClaw onboard…")
        install_daemon = self.cfg.get("openclaw.install_daemon", True)
        flag = " --install-daemon" if install_daemon else ""
        ok, out = self.wsl.run_in_wsl(f"openclaw onboard{flag} --non-interactive 2>&1 || true", timeout=120)
        self.log.info(f"Onboard output: {out[:500]}")
        return True  # onboard may partially succeed; config is already written

    def start_gateway(self) -> bool:
        """Start the openclaw gateway."""
        self.log.step("Starting OpenClaw gateway…")
        ok, out = self.wsl.run_in_wsl(
            "openclaw gateway start --port {} --verbose &".format(
                self.cfg.get("gateway.port", 18789)
            ),
            timeout=30,
        )
        if ok:
            self.log.success("Gateway started")
        else:
            self.log.warn(f"Gateway start: {out[:300]}")
        return ok

    def verify_installation(self) -> bool:
        """Quick health check."""
        self.log.step("Verifying installation…")
        ok, out = self.wsl.run_in_wsl("openclaw --version 2>&1")
        if ok:
            self.log.success(f"OpenClaw version: {out}")
        else:
            self.log.error(f"Verification failed: {out}")
        return ok
