import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "bin" / "bridge-wrapper.sh"


def test_wrapper_refuses_generic_telegram_token_without_claude_token():
    env = os.environ.copy()
    env.pop("CLAUDE_TELEGRAM_BOT_TOKEN", None)
    env["TELEGRAM_BOT_TOKEN"] = "shared-token-must-not-be-used"
    env["TELEGRAM_CHAT_ID"] = "123"
    env["CLAUDE_TELEGRAM_BRIDGE_SKIP_ENVRC"] = "1"
    env["CLAUDE_TELEGRAM_BRIDGE_DISABLE_SOPS"] = "1"

    result = subprocess.run(
        [str(WRAPPER)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 78
    assert "CLAUDE_TELEGRAM_BOT_TOKEN is required" in result.stderr
    assert "Refusing to use TELEGRAM_BOT_TOKEN" in result.stderr


def test_wrapper_refuses_identical_claude_and_generic_tokens():
    env = os.environ.copy()
    env["CLAUDE_TELEGRAM_BOT_TOKEN"] = "same-token"
    env["TELEGRAM_BOT_TOKEN"] = "same-token"
    env["TELEGRAM_CHAT_ID"] = "123"
    env["CLAUDE_TELEGRAM_BRIDGE_SKIP_ENVRC"] = "1"
    env["CLAUDE_TELEGRAM_BRIDGE_DISABLE_SOPS"] = "1"

    result = subprocess.run(
        [str(WRAPPER)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 78
    assert "must not equal TELEGRAM_BOT_TOKEN" in result.stderr
