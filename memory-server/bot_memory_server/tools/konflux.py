"""MCP tools for fetching Konflux pipeline failure logs from KubeArchive."""

import json
import os
import re
import ssl
import urllib.request
from urllib.error import HTTPError, URLError

KUBEARCHIVE_TOKEN = os.environ.get("KUBEARCHIVE_TOKEN", "")

MAX_OUTPUT_CHARS = 8000
DETAILS_URL_PATTERN = re.compile(r"https?://konflux-ui\.apps\.([^/]+)/ns/([^/]+)/pipelinerun/([^/]+)")
KUBEARCHIVE_URL_TEMPLATE = "https://kubearchive-api-server-product-kubearchive.apps.{cluster}"


def _api_get(path: str, base_url: str, timeout: int = 30) -> dict | str | None:
    """GET request to KubeArchive API. Returns parsed JSON for JSON responses, raw text for logs."""
    url = f"{base_url}{path}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {KUBEARCHIVE_TOKEN}"})
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read().decode("utf-8", errors="replace")
            if "json" in content_type:
                return json.loads(raw)
            return raw
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200] if e.fp else ""
        return {"error": f"HTTP {e.code}", "message": body}
    except (URLError, TimeoutError) as e:
        return {"error": "connection_failed", "message": str(e)}


def _parse_details_url(url: str) -> tuple[str, str, str] | None:
    """Returns (cluster, namespace, pipelinerun_name) or None."""
    m = DETAILS_URL_PATTERN.search(url)
    if m:
        return m.group(1), m.group(2), m.group(3)
    return None


def _is_failed(conditions: list[dict]) -> bool:
    return any(c.get("type") == "Succeeded" and c.get("status") == "False" for c in conditions)


def _failure_reason(conditions: list[dict]) -> str:
    for c in conditions:
        if c.get("type") == "Succeeded" and c.get("status") == "False":
            return c.get("message", c.get("reason", "Unknown"))
    return "Unknown"


def _failed_steps(steps: list[dict]) -> list[dict]:
    return [
        {
            "name": s["name"],
            "exit_code": s.get("terminated", {}).get("exitCode", -1),
        }
        for s in steps
        if s.get("terminated", {}).get("exitCode", 0) != 0
    ]


def _tail(text: str, n: int) -> str:
    lines = text.rstrip("\n").split("\n")
    if len(lines) <= n:
        return text.rstrip("\n")
    return f"... ({len(lines) - n} lines truncated) ...\n" + "\n".join(lines[-n:])


def register_konflux_tools(mcp):
    @mcp.tool()
    async def konflux_get_build_logs(
        details_url: str,
        tail_lines: int = 100,
    ) -> dict:
        """Fetch Konflux CI pipeline failure logs from KubeArchive.

        Use when a Konflux pipeline check fails on a PR. Provide the
        details_url from the GitHub check's detailsUrl field (the Konflux UI URL).

        Returns failed TaskRun details with step-level logs for diagnosis."""

        if not KUBEARCHIVE_TOKEN:
            return {"error": "KUBEARCHIVE_TOKEN not configured"}

        if details_url:
            parsed = _parse_details_url(details_url)
            if parsed:
                cluster, namespace, pipelinerun_name = parsed
                base_url = KUBEARCHIVE_URL_TEMPLATE.format(cluster=cluster)
            else:
                return {"error": f"Could not parse namespace/pipelinerun from URL: {details_url}"}
        else:
            return {"error": "details_url is required"}

        if not pipelinerun_name:
            return {"error": "pipelinerun_name is required (or provide details_url)"}

        label = urllib.request.quote(f"tekton.dev/pipelineRun={pipelinerun_name}", safe="")
        data = _api_get(f"/apis/tekton.dev/v1/namespaces/{namespace}/taskruns?labelSelector={label}", base_url=base_url)

        if isinstance(data, dict) and "error" in data:
            return data

        items = data.get("items", []) if isinstance(data, dict) else []
        if not items:
            return {
                "pipelinerun": pipelinerun_name,
                "namespace": namespace,
                "error": "No TaskRuns found for this PipelineRun",
            }

        all_tasks = []
        failed_tasks = []
        for tr in items:
            task_name = tr.get("metadata", {}).get("labels", {}).get("tekton.dev/pipelineTask", "unknown")
            conditions = tr.get("status", {}).get("conditions", [])
            failed = _is_failed(conditions)
            all_tasks.append({"task": task_name, "failed": failed})
            if not failed:
                continue

            pod_name = tr.get("status", {}).get("podName", "")
            steps = tr.get("status", {}).get("steps", [])
            bad_steps = _failed_steps(steps)

            task_info = {
                "task": task_name,
                "pod": pod_name,
                "reason": _failure_reason(conditions),
                "steps": [],
            }

            for step in bad_steps:
                step_info = {"name": step["name"], "exit_code": step["exit_code"], "logs": ""}
                if pod_name:
                    log_data = _api_get(
                        f"/api/v1/namespaces/{namespace}/pods/{pod_name}/log?container=step-{step['name']}",
                        base_url=base_url,
                    )
                    if isinstance(log_data, str):
                        step_info["logs"] = _tail(log_data, tail_lines)
                    elif isinstance(log_data, dict) and "error" in log_data:
                        step_info["logs"] = f"[log fetch failed: {log_data.get('message', log_data['error'])}]"
                task_info["steps"].append(step_info)

            failed_tasks.append(task_info)

        result = {
            "pipelinerun": pipelinerun_name,
            "namespace": namespace,
            "total_tasks": len(all_tasks),
            "failed_tasks": failed_tasks,
            "summary": [f"{'FAIL' if t['failed'] else ' OK '} {t['task']}" for t in all_tasks],
        }

        output = json.dumps(result)
        if len(output) > MAX_OUTPUT_CHARS:
            for task in result["failed_tasks"]:
                for step in task["steps"]:
                    step["logs"] = _tail(step["logs"], tail_lines // 2)
            output = json.dumps(result)
            if len(output) > MAX_OUTPUT_CHARS:
                for task in result["failed_tasks"]:
                    for step in task["steps"]:
                        step["logs"] = _tail(step["logs"], 30)

        return result
