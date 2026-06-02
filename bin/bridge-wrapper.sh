#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

# Load bridge token from SOPS vault (defensive: fail closed if missing/invalid)
SOPS_CFG="$HOME/.secrets/.sops.yaml"
SOPS_AGE_KEY_FILE="$HOME/.config/sops/age/keys.txt"

if [ -z "${CLAUDE_TELEGRAM_BOT_TOKEN:-}" ] && [ "${CLAUDE_TELEGRAM_BRIDGE_DISABLE_SOPS:-0}" != "1" ]; then
  if [ -f "$SOPS_AGE_KEY_FILE" ] && [ -f ~/.secrets/openclaw-runtime.env ]; then
    CLAUDE_TELEGRAM_BOT_TOKEN=$(SOPS_AGE_KEY_FILE="$SOPS_AGE_KEY_FILE" sops --config "$SOPS_CFG" \
      -d ~/.secrets/openclaw-runtime.env 2>/dev/null | \
      grep '^CLAUDE_CODE_BRIDGE_TELEGRAM_BOT_TOKEN=' | cut -d= -f2- | tr -d '\n')
  fi
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

export TELEGRAM_CHAT_ID="7618822262"

exec /opt/homebrew/bin/uv run claude-telegram-bridge
