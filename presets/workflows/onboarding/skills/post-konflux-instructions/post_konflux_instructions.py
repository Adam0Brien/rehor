#!/usr/bin/env python3
"""Post Tekton pipeline generation instructions.

Usage:
    python3 post_konflux_instructions.py '<json_config>'
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from jira_mcp import jira_cleanup
from onboarding_helpers import apply_label, post_comment

LABEL = "onboarding:tekton-setup"


def _build_comment(config):
    instance_name = config.get("instance_name", "<instance_name>")
    quay_org = config.get("quay_org", "<quay_org>")

    return f"""\
## [Phase 2/3] Konflux CI/CD — Action Required: Generate Tekton Pipelines

The Konflux Component is registered. Now generate the CI pipeline files:

1. **Install the Konflux GitHub app** for your cluster on your instance repo (each cluster has its own app):
   - `kflux-prd-rh02`: install via Konflux UI → Settings → GitHub App
   - `kflux-prd-rh03`: install via Konflux UI → Settings → GitHub App
   This is required before Tekton pipelines can trigger on your repo.
2. **Go to the Konflux UI** and navigate to your component (`{instance_name}`)
3. **Trigger pipeline generation** — use "Send PR" to create a PR on your instance repo with `.tekton/` pipeline files
4. **If "Send PR" fails** (usually due to commit signing requirements), follow this workaround: [Konflux Pipeline Setup Guide](https://docs.google.com/document/d/1c_UraNynI6h-K5ap1ORfO2Lvs0YsE9QFtBw82jZYr6E/edit?usp=sharing)
5. **Merge the pipeline PR**
6. **Verify the initial build** — after merge, the Tekton push pipeline should trigger automatically
7. **Confirm Quay image** — verify the image appears at `quay.io/redhat-services-prod/{quay_org}/{instance_name}`

Reply here once the pipelines are merged and the Quay image is available, and we'll move to Phase 3: Deployment.
"""


def main():
    if len(sys.argv) < 2:
        print("Usage: post_konflux_instructions.py '<json_config>'", file=sys.stderr)
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
