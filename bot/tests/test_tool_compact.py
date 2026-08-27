"""Tests for MCP tool-result compactors (conversation history, not MCP servers)."""

from __future__ import annotations

import asyncio
import json

from bot.tool_compact import (
    compact_payload,
    compact_tool_response,
    hook_output,
    make_compact_hook,
)

_AVATAR = "https://example.com/avatar.png?size=48"


def _adf_paragraph(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def _fat_jira_issue() -> dict:
    comments = [
        {
            "self": f"https://jira.example/rest/api/3/comment/{i}",
            "id": str(10000 + i),
            "author": {
                "accountId": f"acct-{i}",
                "displayName": f"User {i}",
                "avatarUrls": {"48x48": _AVATAR},
                "self": f"https://jira.example/rest/api/3/user?accountId=acct-{i}",
            },
            "created": f"2026-08-01T{i:02d}:00:00.000+0000",
            "body": {
                "type": "doc",
                "version": 1,
                "content": [_adf_paragraph("word " * 80)],
            },
        }
        for i in range(20)
    ]
    return {
        "expand": "renderedFields,names,schema,operations,editmeta,changelog,versionedRepresentations",
        "id": "6950439",
        "self": "https://jira.example/rest/api/3/issue/6950439",
        "key": "RHCLOUD-50690",
        "fields": {
            "summary": "Batch CSV Mode 1",
            "status": {"self": "https://jira.example/status/1", "name": "In Progress", "id": "3"},
            "labels": ["kessel-ai-local", "repo:token-cost-bench"],
            "issuetype": {"name": "Story", "id": "10001", "self": "https://jira.example/issuetype/1"},
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    _adf_paragraph("Users sometimes have token usage for many requests."),
                    _adf_paragraph("Add a CLI mode that accepts a CSV."),
                ],
            },
            "issuelinks": [
                {
                    "id": "1",
                    "self": "https://jira.example/link/1",
                    "type": {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
                    "outwardIssue": {
                        "key": "RHCLOUD-1",
                        "fields": {"status": {"name": "Done"}},
                    },
                }
            ],
            "comment": {"comments": comments, "maxResults": 100, "total": 20},
            "watches": {"isWatching": False, "watchCount": 3},
            "votes": {"votes": 0, "hasVoted": False},
            "worklog": {"worklogs": []},
        },
        "renderedFields": {"description": "<p>huge html blob " + ("x" * 2000) + "</p>"},
        "schema": {"summary": {"type": "string"}},
        "operations": {"linkGroups": []},
        "editmeta": {"fields": {}},
        "changelog": {"histories": []},
        "versionedRepresentations": {},
    }


def test_fat_jira_issue_drops_metadata_and_caps_comments():
    original = json.dumps(_fat_jira_issue())
    compact = compact_tool_response("mcp__mcp-atlassian__jira_get_issue", _fat_jira_issue())
    assert compact is not None
    assert "accountId" not in compact
    assert '"self"' not in compact
    assert "expand" not in json.loads(compact)
    data = json.loads(compact)
    assert data["key"] == "RHCLOUD-50690"
    assert data["summary"] == "Batch CSV Mode 1"
    assert data["status"] == "In Progress"
    assert "CSV" in data["description"]
    assert len(data["comments"]) <= 5
    assert data["links"][0].startswith("Blocks RHCLOUD-1")
    assert len(compact) < 0.25 * len(original)


def test_jira_search_compacts_each_issue():
    payload = {"issues": [_fat_jira_issue(), _fat_jira_issue()]}
    compact = compact_tool_response("mcp__mcp-atlassian__jira_search", payload)
    data = json.loads(compact)
    assert len(data["issues"]) == 2
    assert data["issues"][0]["key"] == "RHCLOUD-50690"
    assert "renderedFields" not in data["issues"][0]


def test_transitions_keep_id_and_name_only():
    payload = [
        {
            "id": 91,
            "name": "Code Review",
            "to": {"name": "Code Review", "id": "10154"},
            "hasScreen": False,
        }
    ]
    compact = compact_tool_response("mcp__mcp-atlassian__jira_get_transitions", payload)
    data = json.loads(compact)
    assert data == [{"id": "91", "name": "Code Review"}]


def test_memory_search_drops_empty_metadata():
    payload = [
        {
            "id": 1,
            "category": "learning",
            "repo": "token-cost-bench",
            "title": "CSV flag",
            "content": "Reuse EstimateCost",
            "tags": ["testing"],
            "similarity": 0.91,
            "metadata": {},
            "external_key": "RHCLOUD-1",
        }
    ]
    compact = compact_tool_response("mcp__bot-memory__memory_search", payload)
    data = json.loads(compact)
    assert data[0]["title"] == "CSV flag"
    assert "metadata" not in data[0]
    assert "external_key" not in data[0]
    assert data[0]["similarity"] == 0.91


def test_memory_list_compacts_items():
    payload = {
        "items": [
            {
                "id": 2,
                "category": "learning",
                "repo": None,
                "title": "t",
                "content": "c",
                "tags": [],
                "metadata": {"noise": 1},
            }
        ],
        "total": 1,
        "limit": 20,
        "offset": 0,
    }
    compact = compact_tool_response("mcp__bot-memory__memory_list", payload)
    data = json.loads(compact)
    assert data["total"] == 1
    assert data["items"][0]["id"] == 2
    assert "metadata" not in data["items"][0]


def test_unknown_mcp_tool_unchanged_when_large():
    blob = {"raw": "y" * 5000}
    compact = compact_tool_response("mcp__other__mystery", blob)
    assert compact is None


def test_tiny_payload_returns_none():
    compact = compact_tool_response(
        "mcp__mcp-atlassian__jira_get_issue",
        {"key": "X-1", "fields": {"summary": "tiny", "status": {"name": "New"}}},
    )
    assert compact is None


def test_content_blocks_are_unwrapped():
    inner = _fat_jira_issue()
    wrapped = [{"type": "text", "text": json.dumps(inner)}]
    compact = compact_payload("mcp__mcp-atlassian__jira_get_issue", wrapped)
    assert compact is not None
    assert json.loads(compact)["key"] == "RHCLOUD-50690"


def test_hook_returns_empty_when_not_smaller():
    hook = make_compact_hook()
    result = asyncio.run(
        hook(
            {
                "tool_name": "mcp__mcp-atlassian__jira_get_issue",
                "tool_response": {"key": "X-1", "fields": {"summary": "tiny"}},
            },
            "toolu_1",
            None,
        )
    )
    assert result == {}


def test_hook_observes_fat_jira_without_rewrite(caplog):
    hook = make_compact_hook()
    with caplog.at_level("INFO", logger="bot.tool_compact"):
        result = asyncio.run(
            hook(
                {
                    "tool_name": "mcp__mcp-atlassian__jira_get_issue",
                    "tool_response": _fat_jira_issue(),
                },
                "toolu_1",
                None,
            )
        )
    assert result == {}
    compact_logs = [r.message for r in caplog.records if r.message.startswith("tool_compact ")]
    assert compact_logs
    assert "tool=mcp__mcp-atlassian__jira_get_issue" in compact_logs[0]
    assert " in=" in compact_logs[0]
    assert " out=" in compact_logs[0]
    assert " ratio=" in compact_logs[0]
    assert "rewrote=0" in compact_logs[0]
    # hook_output still produces a valid rewrite payload (escape hatch / SDK shape lock).
    compact = compact_tool_response("mcp__mcp-atlassian__jira_get_issue", _fat_jira_issue())
    assert compact is not None
    specific = hook_output(compact)["hookSpecificOutput"]
    assert specific["hookEventName"] == "PostToolUse"


def _fat_task(i: int) -> dict:
    return {
        "id": i,
        "external_key": f"RHCLOUD-{50000 + i}",
        "source_type": "jira",
        "source_url": f"https://issues.redhat.com/browse/RHCLOUD-{50000 + i}",
        "artifacts": [
            {
                "name": f"PR #{i}",
                "url": f"https://github.com/Adam0Brien/token-cost-bench/pull/{i}",
                "type": "pull_request",
            }
        ],
        "status": "pr_open",
        "repo": "token-cost-bench",
        "branch": f"bot/RHCLOUD-{50000 + i}",
        "title": f"Batch CSV Mode {i}",
        "summary": "Implemented --format flag (table/csv) for tokencost CLI. " + ("x" * 80),
        "created_at": "2026-08-20T10:00:00+00:00",
        "last_addressed": "2026-08-26T16:20:00+00:00",
        "paused_reason": None,
        "instance_id": "local-aobrien",
        "metadata": {
            "last_step": "pr_opened",
            "next_step": "wait_review",
            "files_changed": [f"src/file_{n}.py" for n in range(20)],
            "commits": [f"abc{n:03d} conventional commit message {n}" for n in range(8)],
            "notes": "long note " * 40,
            "repos": ["token-cost-bench"],
            "prs": [
                {
                    "repo": "token-cost-bench",
                    "number": i,
                    "url": f"https://github.com/Adam0Brien/token-cost-bench/pull/{i}",
                    "host": "github",
                }
            ],
        },
    }


def test_fat_task_list_drops_artifacts_and_urls():
    payload = [_fat_task(i) for i in range(1, 9)]
    original = json.dumps(payload)
    compact = compact_tool_response("mcp__bot-memory__task_list", payload)
    assert compact is not None
    data = json.loads(compact)
    assert len(data) == 8
    first = data[0]
    assert first["external_key"] == "RHCLOUD-50001"
    assert first["last_step"] == "pr_opened"
    assert first["prs"][0]["number"] == 1
    assert "url" not in first["prs"][0]
    assert "artifacts" not in first
    assert "source_url" not in first
    assert "files_changed" not in first
    assert "metadata" not in first
    assert len(compact) < 0.3 * len(original)


def test_tiny_task_get_unchanged_when_not_smaller():
    compact = compact_tool_response(
        "mcp__bot-memory__task_get",
        {"id": 1, "external_key": "X-1", "status": "in_progress", "repo": "r"},
    )
    assert compact is None


def test_progress_store_ack_shape():
    payload = {
        "id": 40,
        "task_id": 12,
        "cycle_type": "task_work",
        "instance_id": "local-aobrien",
        "started_at": "2026-08-27T11:16:46+00:00",
        "finished_at": "2026-08-27T11:19:56+00:00",
        "tool_calls": 20,
        "tokens_used": 6850,
        "progress": {"last_step": "pr_opened", "notes": "n" * 200},
        "created_at": "2026-08-27T11:19:56+00:00",
    }
    compact = compact_tool_response("mcp__bot-memory__progress_store", payload)
    assert json.loads(compact) == {"id": 40, "task_id": 12, "cycle_type": "task_work"}


def test_progress_load_keeps_progress_drops_created_at():
    payload = [
        {
            "id": 1,
            "task_id": 12,
            "cycle_type": "task_work",
            "progress": {"last_step": "implemented"},
            "started_at": "2026-08-27T11:00:00+00:00",
            "created_at": "2026-08-27T11:00:01+00:00",
            "instance_id": "local-aobrien",
        }
    ]
    compact = compact_tool_response("mcp__bot-memory__progress_load", payload)
    data = json.loads(compact)
    assert data[0]["progress"]["last_step"] == "implemented"
    assert "created_at" not in data[0]
    assert "instance_id" not in data[0]
