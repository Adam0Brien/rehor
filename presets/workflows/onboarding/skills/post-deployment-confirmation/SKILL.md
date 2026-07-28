---
name: post-deployment-confirmation
description: >
  Post Phase 3 deployment value confirmation on the epic.
  Applies onboarding:deployment-confirmation label.
when_to_use: >
  Invoke when Phase 2 is complete and Tekton setup is confirmed.
  Posts the derived values for team confirmation before opening the MR.
user-invocable: true
allowed-tools:
  - "Bash(python3 .claude/skills/post-deployment-confirmation/post_deployment_confirmation.py *)"
  - Read
---

```bash
python3 .claude/skills/post-deployment-confirmation/post_deployment_confirmation.py '<json_config>' 2>&1
```

## Config JSON

```json
{
  "epic_key": "RHCLOUD-12345",
  "instance_name": "my-team-agent-dev",
  "bot_name": "devbot-my-team",
  "bot_label": "rehor-ai-my-team",
  "repo_url": "https://github.com/MyOrg/my-team-agent-dev",
  "config_name": "my-team-config",
  "quay_org": "my-team-tenant",
  "pattern": "shared",
  "workflow": "jira-sprint",
  "board_name": "My Board",
  "sprint_prefix": "Sprint",
  "gcp_project_id": "my-gcp-project",
  "gcp_region": "global",
  "target_branch": "main"
}
```
