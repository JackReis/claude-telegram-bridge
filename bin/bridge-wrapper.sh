#!/bin/bash
set -eu

cd "$(dirname "$0")/.."

# Load bridge token from SOPS vault (defensive: fail closed if missing/invalid)
SOPS_CFG="$HOME/.secrets/.sops.yaml"
SOPS_AGE_KEY_FILE="$HOME/.config/sops/age/keys.txt"

if [ -f "$SOPS_AGE_KEY_FILE" ] && [ -f ~/.secrets/openclaw-runtime.env ]; then
  TOKEN=$(SOPS_AGE_KEY_FILE="$SOPS_AGE_KEY_FILE" sops --config "$SOPS_CFG" \
    -d ~/.secrets/openclaw-runtime.env 2>/dev/null | \
    grep '^CLAUDE_CODE_BRIDGE_TELEGRAM_BOT_TOKEN=' | cut -d= -f2- | tr -d '\n')
  if [ -n "$TOKEN" ] && [ "${#TOKEN}" -gt 20 ]; then
    export TELEGRAM_BOT_TOKEN="$TOKEN"
  else
    echo "ERROR: CLAUDE_CODE_BRIDGE_TELEGRAM_BOT_TOKEN missing or invalid in SOPS" >&2
    echo "  Fix: Get a real BotFather token and add it to ~/.secrets/openclaw-runtime.env" >&2
    exit 1
  fi
else
  echo "ERROR: SOPS key or secrets file missing" >&2
  exit 1
fi

export TELEGRAM_CHAT_ID="7618822262"

exec /opt/homebrew/bin/uv run claude-telegram-bridge
