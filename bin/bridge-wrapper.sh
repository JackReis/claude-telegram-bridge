#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

# Load bridge token from SOPS vault (defensive: fail closed if missing/invalid)
SOPS_CFG="$HOME/.secrets/.sops.yaml"
SOPS_AGE_KEY_FILE="$HOME/.config/sops/age/keys.txt"
# Overridable for tests; defaults to the shared fleet runtime secrets file.
SECRETS_FILE="${CLAUDE_TELEGRAM_BRIDGE_SECRETS_FILE:-$HOME/.secrets/openclaw-runtime.env}"

# Emit the decrypted (or plaintext, in test mode) contents of the secrets file.
# sops stderr is intentionally NOT suppressed here so a genuine decrypt failure
# (bad/missing age key, sops version mismatch) is visible in the MCP host log
# instead of masquerading as a missing token.
_bridge_read_secrets() {
  if [ "${CLAUDE_TELEGRAM_BRIDGE_PLAINTEXT_SECRETS:-0}" = "1" ]; then
    cat "$SECRETS_FILE"
  else
    SOPS_AGE_KEY_FILE="$SOPS_AGE_KEY_FILE" sops --config "$SOPS_CFG" -d "$SECRETS_FILE"
  fi
}

# Extract the value of KEY from already-decrypted secrets text (arg 2), matching
# `KEY=val` or `export KEY=val` and stripping optional surrounding quotes.
# SOPS-decrypted lines carry an `export ` prefix, so the match must tolerate it
# (this was the live bug). A missing key yields an empty string (handled
# downstream), so grep's no-match exit must not trip `set -e`/`pipefail`.
_bridge_extract() {
  local key="$1" content="$2"
  { printf '%s\n' "$content" \
    | grep -E "^(export[[:space:]]+)?${key}=" \
    | head -n1 \
    | sed -E "s/^(export[[:space:]]+)?${key}=//; s/^[\"']//; s/[\"']$//" \
    | tr -d '\n'; } || true
}

# In plaintext test mode the age key need not exist; otherwise it must.
_bridge_secrets_available() {
  [ -f "$SECRETS_FILE" ] || return 1
  [ "${CLAUDE_TELEGRAM_BRIDGE_PLAINTEXT_SECRETS:-0}" = "1" ] && return 0
  [ -f "$SOPS_AGE_KEY_FILE" ]
}

if [ "${CLAUDE_TELEGRAM_BRIDGE_DISABLE_SOPS:-0}" != "1" ] && _bridge_secrets_available; then
  # Decrypt once; extract both keys from the in-memory copy.
  SECRETS_CONTENT=$(_bridge_read_secrets || true)
  if [ -z "${CLAUDE_TELEGRAM_BOT_TOKEN:-}" ]; then
    CLAUDE_TELEGRAM_BOT_TOKEN=$(_bridge_extract CLAUDE_CODE_BRIDGE_TELEGRAM_BOT_TOKEN "$SECRETS_CONTENT")
  fi
  if [ -z "${TELEGRAM_CHAT_ID:-}" ]; then
    TELEGRAM_CHAT_ID=$(_bridge_extract CLAUDE_CODE_BRIDGE_TELEGRAM_CHAT_ID "$SECRETS_CONTENT")
  fi
  unset SECRETS_CONTENT
fi

if [ -z "${CLAUDE_TELEGRAM_BOT_TOKEN:-}" ]; then
  echo "claude-telegram-bridge: CLAUDE_TELEGRAM_BOT_TOKEN is required." >&2
  echo "Refusing to use TELEGRAM_BOT_TOKEN because that may belong to Zoe/OpenClaw." >&2
  exit 78
fi

if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ "$TELEGRAM_BOT_TOKEN" = "$CLAUDE_TELEGRAM_BOT_TOKEN" ]; then
  echo "claude-telegram-bridge: CLAUDE_TELEGRAM_BOT_TOKEN must not equal TELEGRAM_BOT_TOKEN." >&2
  echo "Refusing to share Zoe/OpenClaw's Telegram token." >&2
  exit 78
fi

TELEGRAM_BOT_TOKEN="$CLAUDE_TELEGRAM_BOT_TOKEN"
export TELEGRAM_BOT_TOKEN

if [ -z "${TELEGRAM_CHAT_ID:-}" ]; then
  TELEGRAM_CHAT_ID="7618822262"
fi
export TELEGRAM_CHAT_ID

# Launch seam — TEST-ONLY escape hatch, and a security surface: whoever can set
# CLAUDE_TELEGRAM_BRIDGE_EXEC in this process's environment gets arbitrary code
# execution with the decrypted token in scope. Safe for a single-user local MCP
# server (local compromise already exposes the age key); do NOT expose it on a
# shared host. Lets tests observe the resolved env without starting the server.
if [ -n "${CLAUDE_TELEGRAM_BRIDGE_EXEC:-}" ]; then
  exec /bin/bash -c "$CLAUDE_TELEGRAM_BRIDGE_EXEC"
fi

exec /opt/homebrew/bin/uv run claude-telegram-bridge
