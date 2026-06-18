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


def _run_wrapper_with_secrets(tmp_path, secrets_body):
    """Run the wrapper against a plaintext secrets fixture, capturing the
    token/chat-id it resolves (via the EXEC seam instead of launching uv)."""
    secrets = tmp_path / "secrets.env"
    secrets.write_text(secrets_body)

    env = os.environ.copy()
    for k in ("CLAUDE_TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        env.pop(k, None)
    env["CLAUDE_TELEGRAM_BRIDGE_SKIP_ENVRC"] = "1"
    env["CLAUDE_TELEGRAM_BRIDGE_PLAINTEXT_SECRETS"] = "1"
    env["CLAUDE_TELEGRAM_BRIDGE_SECRETS_FILE"] = str(secrets)
    env["CLAUDE_TELEGRAM_BRIDGE_EXEC"] = (
        'printf "TOKEN=%s\\nCHAT=%s\\n" "$TELEGRAM_BOT_TOKEN" "$TELEGRAM_CHAT_ID"'
    )

    return subprocess.run(
        [str(WRAPPER)], cwd=ROOT, env=env, capture_output=True, text=True
    )


def test_wrapper_extracts_export_prefixed_token_from_secrets(tmp_path):
    # SOPS-decrypted lines carry an `export ` prefix — the wrapper must still
    # extract the dedicated bridge token (regression: anchored grep missed it).
    result = _run_wrapper_with_secrets(
        tmp_path,
        "export CLAUDE_CODE_BRIDGE_TELEGRAM_BOT_TOKEN=111111:FAKE-bridge-token\n"
        "export CLAUDE_CODE_BRIDGE_TELEGRAM_CHAT_ID=7618822262\n"
        "export BLUE_TELEGRAM_BOT_TOKEN=222222:FAKE-other-bot\n",
    )

    assert result.returncode == 0, result.stderr
    assert "TOKEN=111111:FAKE-bridge-token" in result.stdout
    assert "CHAT=7618822262" in result.stdout
    # must NOT pick up a different bot's token
    assert "FAKE-other-bot" not in result.stdout


def test_wrapper_extracts_unprefixed_and_quoted_token(tmp_path):
    # Tolerate both no-export and quoted values.
    result = _run_wrapper_with_secrets(
        tmp_path,
        'CLAUDE_CODE_BRIDGE_TELEGRAM_BOT_TOKEN="333333:FAKE-quoted"\n',
    )

    assert result.returncode == 0, result.stderr
    assert "TOKEN=333333:FAKE-quoted" in result.stdout
