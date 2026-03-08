#!/usr/bin/env bash
# ───────────────────────────────────────────────────────────
#  Write OpenClaw config + env vars
#  Called by the deployer with env vars:
#    ANTHROPIC_BASE_URL, ANTHROPIC_API_KEY, MODEL_NAME,
#    GATEWAY_PORT, GATEWAY_BIND
# ───────────────────────────────────────────────────────────
set -euo pipefail

MODEL_NAME="${MODEL_NAME:-claude-opus-4-6}"
GATEWAY_PORT="${GATEWAY_PORT:-18789}"
GATEWAY_BIND="${GATEWAY_BIND:-loopback}"

mkdir -p ~/.openclaw

# ── openclaw.json ──
cat > ~/.openclaw/openclaw.json <<EOF
{
  "agent": {
    "model": "${MODEL_NAME}"
  },
  "gateway": {
    "port": ${GATEWAY_PORT},
    "bind": "${GATEWAY_BIND}"
  }
}
EOF
echo "[OK] wrote ~/.openclaw/openclaw.json"

# ── env vars (idempotent) ──
MARKER="# >>> OpenClaw LiteLLM Proxy <<<"
if ! grep -q "$MARKER" ~/.bashrc 2>/dev/null; then
    cat >> ~/.bashrc <<ENVEOF

${MARKER}
export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-}"
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"
export ANTHROPIC_AUTH_TOKEN="${ANTHROPIC_API_KEY:-}"
# <<< OpenClaw LiteLLM Proxy >>>
ENVEOF
    echo "[OK] appended env vars to ~/.bashrc"
else
    echo "[OK] env vars already in ~/.bashrc"
fi
