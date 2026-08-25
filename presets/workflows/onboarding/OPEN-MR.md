# Open onboarding MR (GitLab fork)

Do NOT fork — the fork already exists. Do NOT use `glab mr create` (fails for cross-fork MRs). Never `--depth 1` — shallow clones cannot push.

## Parameters

| Param | Konflux | App-interface |
|-------|---------|---------------|
| `repo_key` | `konflux-release-data` | `app-interface` |
| `workdir` | `/tmp/konflux-release-data` | `/tmp/app-interface` |
| `upstream_branch` | `main` | `master` |
| `glab_project` | `releng%2Fkonflux-release-data` | `service%2Fapp-interface` |
| `generate_skill` | `/generate-konflux` | `/generate-app-interface` |
| `title` | `Add Konflux config for <instance_name>` | `[Phase 3/3] Add <instance_name> deployment (<TICKET_KEY>)` |
| `description` | Konflux resources for `<instance_name>` | SaaS deploy file, codeComponents, self-service datafile for `<instance_name>` |

Look up `url` (fork) and `upstream` in `project-repos.json` by `repo_key`.

## Recipe

```bash
git clone <fork-url> <workdir>
cd <workdir>
git remote add upstream <upstream-url>
git fetch upstream <upstream_branch>
git checkout -b bot/onboarding-<TICKET_KEY> upstream/<upstream_branch>
```

Run `<generate_skill>` targeting `<workdir>`. Then any phase-specific steps in CLAUDE.md (e.g. Konflux `build-single.sh` + auto-generated scope check).

Stage + commit generated files.

```bash
git push origin bot/onboarding-<TICKET_KEY>
glab api projects/<glab_project>/merge_requests -X POST \
  -f source_branch="bot/onboarding-<TICKET_KEY>" \
  -f target_branch="<upstream_branch>" \
  -f title="<title>" \
  -f description="$(cat <<'EOF'
<description>
EOF
)" \
  --hostname gitlab.cee.redhat.com
```

**CRITICAL**: glab URL-encodes newlines if description is inline. ALWAYS heredoc for multiline.

Parse MR number + URL from JSON.
