"""Turn-budget PostToolUse hook thresholds."""

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
    from bot.agent import _make_turn_budget_hook

    return _make_turn_budget_hook(100)


def _fire(hook, n):
    result = {}
    for _ in range(n):
        result = asyncio.run(hook({}, "id", None))
    return result


def test_no_warning_before_fifty_percent():
    hook = _hook()
    assert _fire(hook, 49) == {}


def test_warning_at_fifty_percent():
    hook = _hook()
    result = _fire(hook, 50)
    msg = result["systemMessage"]
    assert "WARNING" in msg
    assert "memory_search" in msg
    assert "jira_get_issue" in msg


def test_no_repeat_warning_between_thresholds():
    hook = _hook()
    _fire(hook, 50)
    assert _fire(hook, 1) == {}


def test_critical_at_seventy_percent():
    hook = _hook()
    result = _fire(hook, 70)
    assert "CRITICAL" in result["systemMessage"]
    assert "task_update" in result["systemMessage"]
