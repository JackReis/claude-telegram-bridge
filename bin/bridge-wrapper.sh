#!/bin/bash
set -eu

cd "$(dirname "$0")/.."

# Source env (token + chat ID)
if [ -f ".envrc" ]; then
  set -a
  # shellcheck disable=SC1091
  source .envrc
fi

# Claude Code must not share Zoe/OpenClaw's Telegram bot token.  Use a
# Claude-specific token name so a copied TELEGRAM_BOT_TOKEN fails closed.
if [ -z "${CLAUDE_TELEGRAM_BOT_TOKEN:-}" ]; then
  echo "claude-telegram-bridge: CLAUDE_TELEGRAM_BOT_TOKEN is required." >&2
  echo "Refusing to use TELEGRAM_BOT_TOKEN because that may belong to Zoe/OpenClaw." >&2
  exit 78
fi

TELEGRAM_BOT_TOKEN="$CLAUDE_TELEGRAM_BOT_TOKEN"

export TELEGRAM_BOT_TOKEN
export TELEGRAM_CHAT_ID

exec /opt/homebrew/bin/uv run claude-telegram-bridge
