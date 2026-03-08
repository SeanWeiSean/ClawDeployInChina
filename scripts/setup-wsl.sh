#!/usr/bin/env bash
# ───────────────────────────────────────────────────────────
#  OpenClaw WSL2 Bootstrap Script
#  Run inside WSL — installs Node 22, pnpm, OpenClaw
# ───────────────────────────────────────────────────────────
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()   { echo -e "${GREEN}[OK]${NC}   $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail()  { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }

NODE_VERSION="${NODE_VERSION:-22}"
INSTALL_METHOD="${INSTALL_METHOD:-nvm}"
OPENCLAW_CHANNEL="${OPENCLAW_CHANNEL:-latest}"

# ── 1. System deps ──
echo "▸ Updating apt cache…"
sudo apt-get update -qq
sudo apt-get install -y -qq curl git build-essential ca-certificates >/dev/null 2>&1
log "System dependencies installed"

# ── 2. Node.js ──
if command -v node &>/dev/null; then
    CURRENT=$(node --version | sed 's/v//' | cut -d. -f1)
    if [ "$CURRENT" -ge "$NODE_VERSION" ]; then
        log "Node.js $(node --version) already satisfies ≥${NODE_VERSION}"
    else
        warn "Node.js $(node --version) is too old, upgrading…"
        INSTALL_METHOD="force"
    fi
else
    INSTALL_METHOD="force"
fi

if [ "$INSTALL_METHOD" = "force" ] || [ "$INSTALL_METHOD" = "nvm" ]; then
    echo "▸ Installing Node.js ${NODE_VERSION} via nvm…"
    export NVM_DIR="${HOME}/.nvm"
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
    # shellcheck source=/dev/null
    [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
    nvm install "$NODE_VERSION"
    nvm alias default "$NODE_VERSION"
    log "Node.js $(node --version) installed"
elif [ "$INSTALL_METHOD" = "nodesource" ]; then
    echo "▸ Installing Node.js ${NODE_VERSION} via NodeSource…"
    curl -fsSL "https://deb.nodesource.com/setup_${NODE_VERSION}.x" | sudo -E bash -
    sudo apt-get install -y nodejs
    log "Node.js $(node --version) installed"
fi

# ── 3. pnpm ──
if ! command -v pnpm &>/dev/null; then
    echo "▸ Installing pnpm…"
    corepack enable 2>/dev/null && corepack prepare pnpm@latest --activate 2>/dev/null \
        || npm install -g pnpm
    log "pnpm $(pnpm --version) installed"
else
    log "pnpm $(pnpm --version) already installed"
fi

# ── 4. OpenClaw ──
if ! command -v openclaw &>/dev/null; then
    echo "▸ Installing OpenClaw (npm, tag=${OPENCLAW_CHANNEL})…"
    npm install -g "openclaw@${OPENCLAW_CHANNEL}"
    log "OpenClaw $(openclaw --version) installed"
else
    log "OpenClaw $(openclaw --version) already installed"
fi

echo ""
log "Bootstrap complete! Run 'openclaw onboard --install-daemon' to finish setup."
