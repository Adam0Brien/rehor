"""Compact MCP tool results — measuring stick + observe-only PostToolUse hook.

Pure functions — no Agent SDK import. Preflight still receives full JSON.
The hook logs in/out/ratio but never sets updatedMCPToolOutput (rewrites bust
prompt cache: cache_write is 12.5x cache_read).
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# claude-agent-sdk 0.1.58 PostToolUseHookSpecificOutput: updatedMCPToolOutput only.
MCP_REWRITE_FIELD = "updatedMCPToolOutput"

_MAX_COMMENTS = 5
_MAX_LINKS = 5
_MAX_COMMENT_BODY = 150
_UNKNOWN_LOG_CHARS = 4000

_MEMORY_KEYS = ("id", "category", "repo", "title", "content", "tags", "similarity")
_SUMMARY_CAP = 150
_MAX_PRS = 5

_JIRA_ISSUE_TOOLS = frozenset({"jira_get_issue"})
_JIRA_SEARCH_TOOLS = frozenset({"jira_search"})
_JIRA_TRANSITION_TOOLS = frozenset({"jira_get_transitions"})
_MEMORY_SEARCH_TOOLS = frozenset({"memory_search"})
_MEMORY_LIST_TOOLS = frozenset({"memory_list"})
_MEMORY_STORE_TOOLS = frozenset({"memory_store"})
_TASK_LIST_TOOLS = frozenset({"task_list"})
_TASK_ITEM_TOOLS = frozenset({"task_get", "task_add", "task_update", "task_remove"})
_PROGRESS_STORE_TOOLS = frozenset({"progress_store"})
_PROGRESS_LOAD_TOOLS = frozenset({"progress_load"})


def _short_name(tool_name: str) -> str:
    return tool_name.rsplit("__", 1)[-1]


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _unwrap(payload: Any) -> Any:
    if isinstance(payload, list) and payload and isinstance(payload[0], dict) and payload[0].get("type") == "text":
        text = payload[0].get("text", "")
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return payload
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return payload
    return payload


def _flatten_adf(node: Any) -> str:
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "\n".join(part for part in (_flatten_adf(x) for x in node) if part)
    if not isinstance(node, dict):
        return ""
    ntype = node.get("type")
    if ntype == "text":
        return node.get("text") or ""
    if ntype == "hardBreak":
        return "\n"
    inner = _flatten_adf(node.get("content") or [])
    if ntype in ("paragraph", "heading", "blockquote", "listItem"):
        return f"{inner}\n" if inner else ""
    return inner


def _to_plain(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return _flatten_adf(value).strip()
    return str(value).strip()


def _collapse(value: Any, limit: int) -> str:
    collapsed = " ".join(_to_plain(value).split())
    return collapsed[:limit]


def _plain_description(issue: dict) -> str:
    fields = issue.get("fields") or {}
    desc = fields.get("description")
    if desc is None:
        desc = issue.get("description")
    text = _to_plain(desc)
    if text:
        return text
    rendered = (issue.get("renderedFields") or {}).get("description")
    if isinstance(rendered, str) and rendered.strip() and "<" not in rendered:
        return rendered.strip()
    return text


def _compact_links(links: Any) -> list[str]:
    if not isinstance(links, list):
        return []
    out: list[str] = []
    for lk in links[:_MAX_LINKS]:
        if not isinstance(lk, dict):
            continue
        lt = (lk.get("type") or {}).get("name", "?")
        linked = lk.get("inwardIssue") or lk.get("outwardIssue") or {}
        key = linked.get("key", "?")
        status = (linked.get("fields") or {}).get("status") or {}
        status_name = status.get("name", "?") if isinstance(status, dict) else "?"
        out.append(f"{lt} {key} [{status_name}]")
    return out


def _comment_list(issue: dict) -> list:
    fields = issue.get("fields") or {}
    comment = fields.get("comment")
    if isinstance(comment, dict):
        comments = comment.get("comments") or []
        if comments:
            return comments
    top = issue.get("comments")
    return top if isinstance(top, list) else []


def _compact_comments(issue: dict) -> list[dict]:
    comments = [c for c in _comment_list(issue) if isinstance(c, dict)]
    kept = comments[-_MAX_COMMENTS:]
    out = []
    for c in kept:
        author = c.get("author") or {}
        name = author.get("displayName", "?") if isinstance(author, dict) else str(author or "?")
        out.append(
            {
                "created": str(c.get("created", ""))[:16],
                "author": name,
                "body": _collapse(c.get("body"), _MAX_COMMENT_BODY),
            }
        )
    return out


def _compact_jira_issue(issue: dict) -> dict:
    fields = issue.get("fields") or {}
    status = fields.get("status") or issue.get("status") or {}
    status_name = status.get("name", status) if isinstance(status, dict) else str(status or "")
    issuetype = fields.get("issuetype") or issue.get("issuetype") or {}
    type_name = issuetype.get("name", "") if isinstance(issuetype, dict) else str(issuetype or "")
    return {
        "key": issue.get("key", ""),
        "summary": fields.get("summary") or issue.get("summary") or "",
        "status": status_name,
        "labels": fields.get("labels") or issue.get("labels") or [],
        "issuetype": type_name,
        "description": _plain_description(issue),
        "links": _compact_links(fields.get("issuelinks") or issue.get("issuelinks") or []),
        "comments": _compact_comments(issue),
    }


def _compact_search(payload: Any) -> dict | None:
    if isinstance(payload, list):
        issues = payload
    elif isinstance(payload, dict):
        issues = payload.get("issues")
        if issues is None:
            return None
    else:
        return None
    return {"issues": [_compact_jira_issue(i) for i in issues if isinstance(i, dict)]}


def _compact_transitions(payload: Any) -> list[dict] | None:
    items = payload
    if isinstance(payload, dict):
        items = payload.get("transitions")
        if items is None:
            return None
    if not isinstance(items, list):
        return None
    return [{"id": str(t.get("id", "")), "name": t.get("name", "")} for t in items if isinstance(t, dict)]


def _compact_memory_item(item: dict) -> dict:
    return {k: item[k] for k in _MEMORY_KEYS if k in item}


def _compact_memory_search(payload: Any) -> list | None:
    if not isinstance(payload, list):
        return None
    return [_compact_memory_item(i) for i in payload if isinstance(i, dict)]


def _compact_memory_list(payload: Any) -> dict | None:
    if not isinstance(payload, dict):
        return None
    items = payload.get("items") or []
    out = {k: payload[k] for k in ("total", "limit", "offset") if k in payload}
    out["items"] = [_compact_memory_item(i) for i in items if isinstance(i, dict)]
    return out


def _compact_memory_store(payload: Any) -> dict | None:
    if not isinstance(payload, dict):
        return None
    return _compact_memory_item(payload)


def _compact_prs(meta: dict) -> list[dict]:
    out: list[dict] = []
    for pr in (meta.get("prs") or [])[:_MAX_PRS]:
        if not isinstance(pr, dict):
            continue
        slim = {k: pr[k] for k in ("repo", "number", "host") if k in pr and pr[k] is not None}
        if slim:
            out.append(slim)
    return out


def _compact_task(task: dict) -> dict:
    raw_meta = task.get("metadata")
    meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    summary = task.get("summary") or ""
    if isinstance(summary, str) and len(summary) > _SUMMARY_CAP:
        summary = summary[:_SUMMARY_CAP]
    last_addr = task.get("last_addressed")
    last_addr = str(last_addr)[:16] if last_addr else None
    out: dict = {
        "id": task.get("id"),
        "external_key": task.get("external_key"),
        "status": task.get("status"),
        "repo": task.get("repo"),
        "branch": task.get("branch"),
        "title": task.get("title"),
    }
    if summary:
        out["summary"] = summary
    if last_addr:
        out["last_addressed"] = last_addr
    if task.get("paused_reason"):
        out["paused_reason"] = task["paused_reason"]
    if meta.get("last_step"):
        out["last_step"] = meta["last_step"]
    elif task.get("last_step"):
        out["last_step"] = task["last_step"]
    if meta.get("next_step"):
        out["next_step"] = meta["next_step"]
    elif task.get("next_step"):
        out["next_step"] = task["next_step"]
    repos = meta.get("repos") or task.get("repos")
    if repos:
        out["repos"] = repos
    prs = _compact_prs(meta) or _compact_prs(task)
    if prs:
        out["prs"] = prs
    return {k: v for k, v in out.items() if v not in (None, "")}


def _compact_task_list(payload: Any) -> list | None:
    if not isinstance(payload, list):
        return None
    return [_compact_task(t) for t in payload if isinstance(t, dict)]


def _compact_task_item(payload: Any) -> dict | None:
    if not isinstance(payload, dict):
        return None
    return _compact_task(payload)


def _compact_progress_store(payload: Any) -> dict | None:
    if not isinstance(payload, dict):
        return None
    return {
        "id": payload.get("id"),
        "task_id": payload.get("task_id"),
        "cycle_type": payload.get("cycle_type"),
    }


def _compact_progress_load(payload: Any) -> list | None:
    if not isinstance(payload, list):
        return None
    out = []
    for run in payload:
        if not isinstance(run, dict):
            continue
        entry: dict = {
            "id": run.get("id"),
            "task_id": run.get("task_id"),
            "cycle_type": run.get("cycle_type"),
            "progress": run.get("progress") or {},
            "started_at": run.get("started_at"),
        }
        if run.get("finished_at"):
            entry["finished_at"] = run["finished_at"]
        if run.get("tool_calls") is not None:
            entry["tool_calls"] = run["tool_calls"]
        if run.get("tokens_used") is not None:
            entry["tokens_used"] = run["tokens_used"]
        out.append(entry)
    return out


def _dispatch(tool_name: str, data: Any) -> Any:
    short = _short_name(tool_name)
    if short in _JIRA_ISSUE_TOOLS and isinstance(data, dict):
        return _compact_jira_issue(data)
    if short in _JIRA_SEARCH_TOOLS:
        return _compact_search(data)
    if short in _JIRA_TRANSITION_TOOLS:
        return _compact_transitions(data)
    if short in _MEMORY_SEARCH_TOOLS:
        return _compact_memory_search(data)
    if short in _MEMORY_LIST_TOOLS:
        return _compact_memory_list(data)
    if short in _MEMORY_STORE_TOOLS:
        return _compact_memory_store(data)
    if short in _TASK_LIST_TOOLS:
        return _compact_task_list(data)
    if short in _TASK_ITEM_TOOLS:
        return _compact_task_item(data)
    if short in _PROGRESS_STORE_TOOLS:
        return _compact_progress_store(data)
    if short in _PROGRESS_LOAD_TOOLS:
        return _compact_progress_load(data)
    return None


def compact_tool_response(tool_name: str, payload: Any) -> str | None:
    """Return compacted JSON text, or None if the payload should stay unchanged."""
    data = _unwrap(payload)
    try:
        original = data if isinstance(data, str) else _dumps(data)
    except (TypeError, ValueError):
        return None

    compacted_obj = _dispatch(tool_name, data)
    if compacted_obj is None:
        if len(original) > _UNKNOWN_LOG_CHARS:
            logger.info(
                "tool_compact tool=%s in=%d out=%d ratio=1.00 skipped=unknown",
                tool_name,
                len(original),
                len(original),
            )
        return None

    compact = _dumps(compacted_obj)
    if len(compact) >= len(original):
        return None
    return compact


def compact_payload(tool_name: str, tool_response: Any) -> str | None:
    """Unwrap MCP content blocks then compact."""
    return compact_tool_response(tool_name, tool_response)


def hook_output(text: str) -> dict:
    """PostToolUse rewrite payload: MCP content blocks."""
    blocks = [{"type": "text", "text": text}]
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            MCP_REWRITE_FIELD: blocks,
        }
    }


def _original_len(tool_response: Any) -> int:
    data = _unwrap(tool_response)
    if isinstance(data, str):
        return len(data)
    try:
        return len(_dumps(data))
    except (TypeError, ValueError):
        return len(str(tool_response))


def make_compact_hook():
    """PostToolUse hook: log compact savings, never rewrite (avoids prompt-cache bust)."""

    async def hook(input_data, tool_use_id, context):
        del tool_use_id, context
        tool_name = (input_data or {}).get("tool_name", "")
        tool_response = (input_data or {}).get("tool_response")
        compact = compact_payload(tool_name, tool_response)
        if compact is None:
            return {}
        in_len = _original_len(tool_response)
        out_len = len(compact)
        ratio = out_len / in_len if in_len else 0.0
        logger.info(
            "tool_compact tool=%s in=%d out=%d ratio=%.2f rewrote=0",
            tool_name,
            in_len,
            out_len,
            ratio,
        )
        return {}

    return hook
