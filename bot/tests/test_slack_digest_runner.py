"""Tests for try_slack_digest — runner-triggered digest."""

from unittest.mock import patch

from bot.slack_digest import try_slack_digest


@patch("bot.slack_digest.cmd_digest")
def test_calls_cmd_digest_when_webhook_set(mock_cmd, monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

    try_slack_digest()

    mock_cmd.assert_called_once()


@patch("bot.slack_digest.cmd_digest")
def test_skips_when_webhook_not_set(mock_cmd, monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)

    try_slack_digest()

    mock_cmd.assert_not_called()


@patch("bot.slack_digest.cmd_digest", side_effect=Exception("MCP error"))
def test_handles_error_gracefully(mock_cmd, monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

    try_slack_digest()  # should not raise
