"""MCP task payloads are slim; HTTP / dashboard task payloads stay full."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

try:
    import asyncpg  # noqa: F401
except ImportError:
    sys.modules["asyncpg"] = MagicMock()
    sys.modules["pgvector"] = MagicMock()
    sys.modules["pgvector.asyncpg"] = MagicMock()

try:
    import fastmcp  # noqa: F401
except ImportError:
    sys.modules["fastmcp"] = MagicMock()

import pytest
from bot_memory_server.tools.tasks import _mcp_task, _row_to_task


def _fake_task_row(**kwargs):
    now = datetime.now(UTC)
    return {
        "id": kwargs.get("id", 1),
        "external_key": kwargs.get("external_key", "RHCLOUD-1"),
        "source_type": "jira",
        "source_url": "https://issues.example/browse/RHCLOUD-1",
        "artifacts": json.dumps([{"name": "PR #1", "url": "https://github.com/o/r/pull/1", "type": "pull_request"}]),
        "status": "pr_open",
        "repo": "token-cost-bench",
        "branch": "bot/RHCLOUD-1",
        "title": "CSV",
        "summary": "Implemented --format flag",
        "created_at": now,
        "last_addressed": now,
        "paused_reason": None,
        "instance_id": "local-aobrien",
        "metadata": json.dumps(
            {
                "last_step": "pr_opened",
                "next_step": "wait_review",
                "files_changed": ["a.py", "b.py"],
                "commits": ["abc123"],
                "notes": "long note",
                "repos": ["token-cost-bench"],
                "prs": [
                    {
                        "repo": "token-cost-bench",
                        "number": 1,
                        "url": "https://github.com/o/r/pull/1",
                        "host": "github",
                    }
                ],
            }
        ),
    }


def test_mcp_task_keeps_resume_fields_drops_fat():
    full = _row_to_task(_fake_task_row())
    slim = _mcp_task(full)
    assert slim["external_key"] == "RHCLOUD-1"
    assert slim["last_step"] == "pr_opened"
    assert slim["prs"] == [{"repo": "token-cost-bench", "number": 1, "host": "github"}]
    assert "artifacts" not in slim
    assert "source_url" not in slim
    assert "files_changed" not in slim
    assert "metadata" not in slim
    assert "instance_id" not in slim


def test_http_full_dump_still_includes_artifacts():
    """_row_to_task remains the full serializer; HTTP api._task is unchanged and also includes artifacts."""
    full = _row_to_task(_fake_task_row())
    assert full["artifacts"]
    assert full["source_url"]
    assert "files_changed" in full["metadata"]


async def _get_tool_fn(mcp_instance, tool_name):
    tools = await mcp_instance.list_tools()
    for t in tools:
        if t.name == tool_name:
            return t.fn
    raise KeyError(f"Tool {tool_name} not found")


@pytest.mark.asyncio
async def test_mcp_task_list_returns_slim_items():
    pytest.importorskip("pytest_asyncio")
    fm = pytest.importorskip("fastmcp")
    if isinstance(fm, MagicMock):
        pytest.skip("fastmcp not installed")
    from bot_memory_server.tools.tasks import register_task_tools
    from fastmcp import FastMCP

    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=[_fake_task_row(id=1), _fake_task_row(id=2, external_key="RHCLOUD-2")])
    mcp = FastMCP(name="test")
    register_task_tools(mcp)
    with patch("bot_memory_server.tools.tasks.get_pool", return_value=pool):
        list_fn = await _get_tool_fn(mcp, "task_list")
        items = await list_fn(instance_id="local-aobrien")

    assert len(items) == 2
    assert items[0]["external_key"] == "RHCLOUD-1"
    assert items[0]["last_step"] == "pr_opened"
    assert items[0]["prs"][0]["host"] == "github"
    assert "url" not in items[0]["prs"][0]
    assert "artifacts" not in items[0]
    assert "source_url" not in items[0]


def test_http_api_task_serializer_keeps_artifacts():
    pytest.importorskip("starlette")
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        sys.modules["sentence_transformers"] = MagicMock()
    from bot_memory_server.api import _task

    http = _task(_fake_task_row())
    assert http["artifacts"]
    assert http["source_url"]
    assert "files_changed" in http["metadata"]
