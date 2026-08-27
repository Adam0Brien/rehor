"""Lock PostToolUse rewrite field against claude-agent-sdk 0.1.58 types."""

from __future__ import annotations

import pytest

from bot.tool_compact import MCP_REWRITE_FIELD, hook_output


def test_sdk_post_tool_use_output_declares_rewrite_field():
    pytest.importorskip("claude_agent_sdk")
    from claude_agent_sdk.types import PostToolUseHookSpecificOutput

    hints = PostToolUseHookSpecificOutput.__annotations__
    assert "updatedMCPToolOutput" in hints or "updatedToolOutput" in hints
    assert MCP_REWRITE_FIELD in hints


def test_hook_output_shape_is_content_blocks():
    out = hook_output("compacted")
    specific = out["hookSpecificOutput"]
    assert specific["hookEventName"] == "PostToolUse"
    payload = specific[MCP_REWRITE_FIELD]
    assert payload == [{"type": "text", "text": "compacted"}]
    if "updatedToolOutput" in specific and MCP_REWRITE_FIELD != "updatedToolOutput":
        assert specific["updatedToolOutput"] == payload
