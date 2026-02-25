"""
Claude Code <-> Telegram bridge MCP server.

Provides tools for Claude Code to communicate with the user via Telegram
when they are away from the terminal. Activated/deactivated explicitly
so notifications only fire when the user has opted in.

Environment variables required:
  TELEGRAM_BOT_TOKEN  - Bot token from @BotFather
  TELEGRAM_CHAT_ID    - Chat ID for the conversation with the user
"""

import json
import os
import time
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

STATE_FILE = Path.home() / ".claude" / "telegram-bridge-state.json"

mcp = FastMCP("claude-telegram-bridge")


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def _get_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN environment variable is not set. "
            "Add it to the MCP server config in ~/.claude/settings.json"
        )
    return token


def _get_chat_id() -> str:
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not chat_id:
        raise ValueError(
            "TELEGRAM_CHAT_ID environment variable is not set. "
            "Run the setup_check tool to discover your chat ID."
        )
    return chat_id


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"away": False, "project": None, "last_update_id": 0}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ---------------------------------------------------------------------------
# Telegram Bot API helpers
# ---------------------------------------------------------------------------

async def _send_message(text: str) -> dict:
    token = _get_token()
    chat_id = _get_chat_id()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
            },
        )
        return resp.json()


async def _poll_updates(state: dict, timeout: int = 10) -> list:
    """Long-poll Telegram for new updates.

    Advances ``state["last_update_id"]`` past *all* fetched updates
    (including those from other chats) to avoid re-reading them,
    but returns only messages from the configured chat.
    """
    token = _get_token()
    chat_id_str = str(_get_chat_id())

    async with httpx.AsyncClient(timeout=timeout + 10) as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{token}/getUpdates",
            json={
                "offset": state.get("last_update_id", 0),
                "timeout": timeout,
                "allowed_updates": ["message"],
            },
        )
        data = resp.json()

    all_updates = data.get("result", [])

    # Advance offset past everything so we never re-process
    if all_updates:
        state["last_update_id"] = all_updates[-1]["update_id"] + 1

    # Return only messages that belong to our chat
    return [
        u
        for u in all_updates
        if str(u.get("message", {}).get("chat", {}).get("id", "")) == chat_id_str
    ]


def _is_command(text: str) -> bool:
    return text.startswith("/")


async def _handle_commands(updates: list, state: dict) -> list:
    """Process /away, /back, /status commands from Telegram.

    Returns the remaining non-command updates.
    """
    non_command: list = []
    for update in updates:
        text = update.get("message", {}).get("text", "")
        if text.strip() == "/away":
            state["away"] = True
            _save_state(state)
            await _send_message("Away mode activated from Telegram.")
        elif text.strip() == "/back":
            state["away"] = False
            _save_state(state)
            await _send_message("Away mode deactivated. Welcome back!")
        elif text.strip() == "/status":
            status = "Active" if state.get("away") else "Inactive"
            project = state.get("project") or "none"
            await _send_message(f"Status: {status}\nProject: {project}")
        elif not _is_command(text):
            non_command.append(update)
    return non_command


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def setup_check() -> str:
    """Verify the Telegram bot is configured correctly.

    Shows bot info and recent chat IDs so the user can find the right
    TELEGRAM_CHAT_ID to put in their config.  Run this during first-time
    setup.
    """
    token = _get_token()

    async with httpx.AsyncClient() as client:
        # Bot identity
        me_resp = await client.get(f"https://api.telegram.org/bot{token}/getMe")
        me_data = me_resp.json()

        # Recent updates (to discover chat IDs)
        updates_resp = await client.post(
            f"https://api.telegram.org/bot{token}/getUpdates",
            json={"limit": 10, "timeout": 1},
        )
        updates_data = updates_resp.json()

    lines = ["Bot configuration check:\n"]

    if me_data.get("ok"):
        bot = me_data["result"]
        lines.append(f"  Bot name : {bot.get('first_name', '?')}")
        lines.append(f"  Username : @{bot.get('username', '?')}")
        lines.append(f"  Bot ID   : {bot.get('id', '?')}")
    else:
        lines.append(f"  ERROR: {me_data}")
        return "\n".join(lines)

    chats_seen: dict[str, str] = {}
    for u in updates_data.get("result", []):
        chat = u.get("message", {}).get("chat", {})
        cid = str(chat.get("id", ""))
        if cid:
            title = (
                chat.get("title")
                or chat.get("first_name", "")
                + (" " + chat.get("last_name", "") if chat.get("last_name") else "")
            )
            chats_seen[cid] = title.strip()

    if chats_seen:
        lines.append("\nRecent chats (use one of these as TELEGRAM_CHAT_ID):\n")
        for cid, title in chats_seen.items():
            lines.append(f"  {cid}  ->  {title}")
    else:
        lines.append(
            "\nNo recent chats found. Send a message to the bot on Telegram "
            "first, then run this tool again."
        )

    return "\n".join(lines)


@mcp.tool()
async def set_away_mode(active: bool, project: str = "") -> str:
    """Activate or deactivate away mode.

    Call with active=true when the user says they are stepping away,
    leaving, going AFK, etc.  Call with active=false when they return.

    While active, send_question / send_summary / check_messages route
    through Telegram.  While inactive they return immediately, so Claude
    should use the normal terminal interaction instead.
    """
    state = _load_state()
    state["away"] = active
    if project:
        state["project"] = project

    if active:
        # Flush stale updates so old messages don't confuse polling
        try:
            await _poll_updates(state, timeout=1)
        except Exception:
            pass

        project_name = state.get("project") or "general"
        await _send_message(
            f"Away mode activated\n"
            f"Project: {project_name}\n\n"
            f"I will send questions and updates here.\n"
            f"Commands: /back  /status"
        )
        _save_state(state)
        return (
            f"Away mode activated. Project: {project_name}. "
            "Telegram notifications enabled."
        )
    else:
        await _send_message("Away mode deactivated\nBack at the terminal.")
        _save_state(state)
        return "Away mode deactivated. Telegram notifications disabled."


@mcp.tool()
async def send_question(question: str, timeout: int = 300) -> str:
    """Send a question via Telegram and wait for the user's reply.

    Only works when away mode is active.  Use this *instead of* asking
    in the terminal when the user is away.  The tool blocks (polls) until
    a reply arrives or the timeout expires.
    """
    state = _load_state()
    if not state.get("away"):
        return (
            "Away mode is not active. "
            "Ask the user directly in the terminal instead."
        )

    project_tag = f"[{state['project']}] " if state.get("project") else ""
    await _send_message(f"{project_tag}Question\n\n{question}")

    start = time.monotonic()
    while time.monotonic() - start < timeout:
        remaining = timeout - (time.monotonic() - start)
        wait = min(10, int(remaining))
        if wait <= 0:
            break

        try:
            updates = await _poll_updates(state, timeout=wait)
        except Exception:
            continue

        non_command = await _handle_commands(updates, state)
        _save_state(state)

        if non_command:
            reply = non_command[0].get("message", {}).get("text", "")
            return f"User responded: {reply}"

    _save_state(state)
    return (
        f"No response received within {timeout} seconds. "
        "Consider moving to the next task or trying again later."
    )


@mcp.tool()
async def send_summary(summary: str) -> str:
    """Send a task-completion summary via Telegram.

    Only works when away mode is active.  Use after finishing a task or
    reaching a milestone so the user knows progress was made.
    """
    state = _load_state()
    if not state.get("away"):
        return (
            "Away mode is not active. "
            "Communicate with the user directly in the terminal."
        )

    project_tag = f"[{state['project']}] " if state.get("project") else ""
    await _send_message(f"{project_tag}Task complete\n\n{summary}")
    return "Summary sent via Telegram."


@mcp.tool()
async def check_messages(timeout: int = 10) -> str:
    """Check for new messages / instructions from the user on Telegram.

    Only works when away mode is active.  Use after sending a summary to
    see if the user replied with follow-up instructions, or periodically
    during long autonomous work.
    """
    state = _load_state()
    if not state.get("away"):
        return "Away mode is not active. Ask the user directly in the terminal."

    try:
        updates = await _poll_updates(state, timeout=timeout)
    except Exception as exc:
        return f"Error checking messages: {exc}"

    non_command = await _handle_commands(updates, state)
    _save_state(state)

    if non_command:
        messages = [
            u.get("message", {}).get("text", "") for u in non_command
        ]
        return "New messages:\n" + "\n".join(f"- {m}" for m in messages)

    return "No new messages."


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    mcp.run()


if __name__ == "__main__":
    main()
