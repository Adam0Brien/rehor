#!/usr/bin/env python3
"""Post Phase 3 deployment value confirmation.

Usage:
    python3 post_deployment_confirmation.py '<json_config>'
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from jira_mcp import jira_cleanup
from onboarding_helpers import apply_label, post_comment

LABEL = "onboarding:deployment-confirmation"


def _build_comment(config):
    quay_org = config.get("quay_org", "<quay_org>")
    instance_name = config.get("instance_name", "<instance_name>")
    repo_url = config.get("repo_url", "<repo_url>")
    config_name = config.get("config_name", "<config_name>")
    bot_name = config.get("bot_name", "<bot_name>")
    bot_label = config.get("bot_label", "<bot_label>")
    pattern = config.get("pattern", "shared")
    gcp_project_id = config.get("gcp_project_id", "<gcp_project_id>")
    gcp_region = config.get("gcp_region", "global")
    target_branch = config.get("target_branch", "main")
    workflow = config.get("workflow", "jira-sprint")

    workflow_lines = ""
    if workflow == "jira-sprint":
        board_name = config.get("board_name", "")
        sprint_prefix = config.get("sprint_prefix", "")
        workflow_lines = (
            f"\n- **Board name**: `{board_name}`"
            f"\n- **Sprint prefix**: `{sprint_prefix}`"
        )
    elif workflow == "jira-kanban":
        board_id = config.get("board_id", "")
        jira_project = config.get("jira_project", "")
        workflow_lines = f"\n- **Board ID**: `{board_id}`"
        if jira_project:
            workflow_lines += f"\n- **Jira project**: `{jira_project}`"

    return f"""\
## [Phase 3/3] Deployment — Confirming Details

Phase 2 is complete! Final phase — deploying your bot.

Confirming these values for the app-interface MR:
- **Instance name**: `{instance_name}`
- **Bot name**: `{bot_name}`
- **Bot label**: `{bot_label}`
- **Config repo**: `{repo_url}`
- **Config path**: `instance/{config_name}`
- **Target branch**: `{target_branch}`
- **Workflow**: `{workflow}`{workflow_lines}
- **Quay image**: `quay.io/redhat-services-prod/{quay_org}/{instance_name}`
- **SaaS pattern**: {pattern}
- **GCP project**: `{gcp_project_id}`
- **GCP region**: `{gcp_region}`

Any corrections? If not, reply "looks good" and I'll open the deployment MR.
"""


def main():
    if len(sys.argv) < 2:
        print("Usage: post_deployment_confirmation.py '<json_config>'", file=sys.stderr)
        sys.exit(1)

    try:
        config = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    epic_key = config.get("epic_key")
    if not epic_key:
        print("ERROR: epic_key is required", file=sys.stderr)
        sys.exit(1)

    try:
        comment = _build_comment(config)
        ok = post_comment(epic_key, comment)
        if not ok:
            sys.exit(1)

        apply_label(epic_key, LABEL)

        print(json.dumps({"epic_key": epic_key, "label": LABEL, "posted": True}))
    finally:
        jira_cleanup()


if __name__ == "__main__":
    main()
