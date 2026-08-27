"""PostToolUse reminder after /post-pr and /claim-ticket Bash scripts."""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _mock_sdk():
    sdk = MagicMock()
    sentinel = object()
    prev = sys.modules.get("claude_agent_sdk", sentinel)
    sys.modules["claude_agent_sdk"] = sdk
    for mod_name in list(sys.modules):
        if mod_name.startswith("bot.agent"):
            sys.modules.pop(mod_name, None)
    yield
    if prev is sentinel:
        sys.modules.pop("claude_agent_sdk", None)
    else:
        sys.modules["claude_agent_sdk"] = prev
    for mod_name in list(sys.modules):
        if mod_name.startswith("bot.agent"):
            sys.modules.pop(mod_name, None)


def _hook():
    from bot.agent import _make_bookkeeping_done_hook

    return _make_bookkeeping_done_hook()


def _fire(command: str, tool_name: str = "Bash"):
    hook = _hook()
    return asyncio.run(
        hook(
            {"tool_name": tool_name, "tool_input": {"command": command}},
            "toolu_1",
            None,
        )
    )


def test_post_pr_injects_stop_message():
    result = _fire("cd /home/botuser/app && python3 .claude/skills/post-pr/post_pr.py RHCLOUD-50735 2>&1")
    msg = result["systemMessage"]
    assert "STOP bookkeeping" in msg
    assert "jira_transition_issue" in msg
    assert "jira_add_comment" in msg
    assert "jira_get_transitions" in msg


def test_claim_ticket_injects_stop_message():
    result = _fire("python3 .claude/skills/claim-ticket/scripts/claim_ticket_operations.py RHCLOUD-50735 2>&1")
    msg = result["systemMessage"]
    assert "claim-ticket finished" in msg
    assert "jira_transition_issue" in msg


def test_dry_run_is_silent():
    assert _fire("python3 .claude/skills/post-pr/post_pr.py RHCLOUD-1 --dry-run") == {}


def test_unrelated_bash_is_silent():
    assert _fire("git push origin bot/RHCLOUD-1") == {}


def test_non_bash_is_silent():
    assert _fire("python3 post_pr.py KEY", tool_name="mcp__mcp-atlassian__jira_add_comment") == {}
