# Claude Telegram Bridge

MCP server that bridges Claude Code to Telegram for async communication. When the user is away from the terminal, Claude can send questions and summaries via Telegram and receive responses.

## Project Structure

```
claude-telegram-bridge/
├── pyproject.toml                          # uv project config
├── uv.lock                                 # Locked dependencies
├── setup_check.py                          # Standalone setup helper (no MCP needed)
├── CLAUDE.md                               # This file
└── src/claude_telegram_bridge/
    ├── __init__.py
    └── server.py                           # MCP server — all tools and logic
```

## Tech Stack

- **Python 3.11+** with `uv` as package manager
- **MCP SDK** (`mcp` package with `FastMCP`) for Claude Code integration
- **httpx** for async Telegram Bot API calls
- **Telegram Bot API** (long polling via `getUpdates`)

## MCP Tools (5 total)

| Tool | Purpose | Away mode required |
|---|---|---|
| `setup_check` | Verify bot config, discover chat IDs | No |
| `set_away_mode` | Toggle away mode on/off | No (it sets the mode) |
| `send_question` | Send question, poll for reply (blocking) | Yes |
| `send_summary` | Send task completion notification | Yes |
| `check_messages` | Read new instructions from Telegram | Yes |

## Telegram Commands (from phone)

- `/away` — activate away mode remotely
- `/back` — deactivate away mode
- `/status` — check current state

## State Management

State persisted at `~/.claude/telegram-bridge-state.json`:
```json
{"away": false, "project": null, "last_update_id": 0}
```

## MCP Server Config

Registered in `~/.claude.json` under `mcpServers.telegram-bridge`:
```
command: uv run --directory /path/to/this/project claude-telegram-bridge
env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
```

## Development

```bash
# Install deps
uv sync

# Test imports and tool registration
uv run python -c "from claude_telegram_bridge.server import mcp; print([t.name for t in mcp._tool_manager._tools.values()])"

# Run standalone setup check (needs TELEGRAM_BOT_TOKEN env var)
TELEGRAM_BOT_TOKEN=xxx uv run python setup_check.py
```

## Key Design Decisions

- **Explicit activation**: Away mode must be toggled — no surprise notifications when user is at the terminal
- **Single chat**: All projects share one Telegram chat, tagged with `[project-name]` prefix. Can be extended to per-project chats later.
- **Long polling**: Uses Telegram's `getUpdates` with server-side timeout (efficient, no webhook infrastructure needed)
- **State file**: Simple JSON file, not a database. Only one consumer reads updates (the MCP server), so no concurrency issues.
- **No Markdown in Telegram messages**: Using plain text to avoid Markdown parsing issues with special characters in project names or summaries.
