#!/bin/bash
set -eu

cd "$(dirname "$0")/.."

# Source env (token + chat ID)
if [ -f ".envrc" ]; then
  set -a
  # shellcheck disable=SC1091
  source .envrc
fi

export TELEGRAM_BOT_TOKEN
export TELEGRAM_CHAT_ID

exec /opt/homebrew/bin/uv run claude-telegram-bridge
