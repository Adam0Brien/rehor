#!/usr/bin/env python3
"""Post Phase 2 Konflux info gathering questions.

Usage:
    python3 post_konflux_questions.py '<json_config>'
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from jira_mcp import jira_cleanup
from onboarding_helpers import apply_label, post_comment

LABEL = "onboarding:konflux-info"


def _build_comment(config):
    team_name = config.get("team_name", "your team")
    return f"""\
## [Phase 2/3] Konflux CI/CD — Getting Started

Phase 1 is complete! Now let's set up Konflux CI/CD for your instance.

I need a few details:

1. **Existing Konflux tenant?** Do you already have a tenant namespace, or should I create a new one?
   - If existing: what's the **tenant name** and **which cluster** is it on?
   - If new: I'll derive a tenant name from your team name (you can override)
2. **Quay org** — the Quay organization for your container images. \
This is often the same as the tenant name, but doesn't have to be. \
(e.g., `my-team-tenant` or `rh-platform-experien-tenant`)
3. **Admin usernames** — SSO/Kerberos usernames for Konflux admin access (e.g., `jdoe`)
4. **Maintainer usernames** — SSO/Kerberos usernames for maintainer access
5. **Cost center** — your team's cost center (required for new tenants)
6. **Quota tier** — default: `1.small` (options: `0.base` through `6.xxxlarge`)

Defaults I'll use unless you say otherwise:
- **Cluster**: `kflux-prd-rh02`
- **Tenant name**: `<derived from {team_name}>`
- **Quay org**: same as tenant name
- **Dockerfile**: `dev-bot/Dockerfile.runner`
"""


def main():
    if len(sys.argv) < 2:
        print("Usage: post_konflux_questions.py '<json_config>'", file=sys.stderr)
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
