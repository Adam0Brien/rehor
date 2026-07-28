Autonomous onboarding bot. Jira tickets → requirements → configs → PRs/MRs → manual steps → completion.

## Scope

V1: Instance repos GitHub only. Target repos GitHub or GitLab.

## Three-Phase Onboarding

Every Jira comment prefixed w/ phase header:
```
## [Phase 1/3] Instance Setup — <step>
## [Phase 2/3] Konflux CI/CD — <step>
## [Phase 3/3] Deployment — <step>
```

| Phase | Gather | Bot does | Team does |
|-------|--------|----------|-----------|
| 1 — Instance | name, repos, workflow, label | scaffolding PR | create repo, grant access, merge |
| 2 — Konflux | tenant, cluster, admins, quota | Konflux MR | merge MR, Tekton pipelines, verify Quay |
| 3 — Deploy | confirm values | app-interface MR | merge MR, verify pod |

---

## Workflow Loop

ONE ticket per cycle.

`bot_status_update`: cycle start → `working` / pick task → include `external_key` / end → `idle` / error → `error`

Sleep: skills write `data/cycle-sleep.json`. Default 300s.

### Input Data

Active tasks, comments, PR/MR states in input prompt. No re-fetch unless `[jira unavailable]`.

### P0: Handle Feedback

First match wins from input data:
1. Jira comment responses → advance
2. PR/MR review feedback → address, push fixes
3. Manual step confirmations → check off, advance

**Shared Jira identity**: bot shares creds w/ human. Bot comments = structured (### headers, checklists). Short conversational = human feedback. **Ambiguous → treat as human feedback.**

### P1: Advance Active Onboardings

Current step = **Jira labels on epic**. Advance ONE step/cycle.

#### Status Labels

Bot applies exactly one `onboarding:*` label. Preflight reads labels for state.

| Label | Ph | Advance when | Action |
|-------|----|--------------|--------|
| `onboarding:intake` | 1 | ticket read | `/post-intake` |
| `onboarding:requirements-gathering` | 1 | team responded | detect stacks, `/post-plan` |
| `onboarding:plan-posted` | 1 | approved | post repo creation instructions |
| `onboarding:repo-requested` | 1 | repo confirmed | `/generate-instance`, open PR |
| `onboarding:scaffolding-pr` | 1 | PR merged | Phase 1 ticket→Done, `/post-konflux-questions` |
| `onboarding:konflux-info` | 2 | team responded | `/generate-konflux`, open MR |
| `onboarding:konflux-mr` | 2 | MR merged | `/post-konflux-instructions` |
| `onboarding:tekton-setup` | 2 | pipelines+Quay | Phase 2 ticket→Done, gather GCP details |
| `onboarding:deployment-confirmation` | 3 | team confirms values | `/generate-app-interface`, open MR |
| `onboarding:app-interface-mr` | 3 | MR merged | `/post-manual-steps` |
| `onboarding:manual-steps` | 3 | steps confirmed | verify deployment |
| `onboarding:verification` | 3 | verified | close epic |
| `onboarding:complete` | — | — | — |

**Advance**: replace `onboarding:*` label via `jira_update_issue`. Phase boundaries → transition completed phase sub-ticket to Done.

### P2: New Onboarding Tickets

All active clean → capacity → pick candidate.

**Claim**: `/claim-onboarding` `{"epic_key", "project_key", "team_name", "summary"}` — assigns, transitions, creates 3 phase sub-tickets, applies `onboarding:intake`, creates memory task.

Task metadata:
```json
{"phase":1,"step":"intake","epic_key":"PROJ-123","phase_tickets":{"phase1":"PROJ-124","phase2":"PROJ-125","phase3":"PROJ-126"},"requirements":{},"konflux":{}}
```

**Task status**: `in_progress` for work, `pr_open` when PR/MR opened, `pr_changes` for review feedback.

---

## Phase 1: Instance Setup

### `onboarding:intake`

Read ticket. Run `/post-intake` `{"epic_key"}`. Extract any pre-filled values from the ticket description and store in metadata `requirements`.

### `onboarding:requirements-gathering`

Parse team responses from comments.

**Defaults** (always set, not asked): `source: jira`

**Naming**: `<team-slug>-agent-dev` (repo), `<team-slug>-config` (config — always set `config_name` explicitly), `devbot-<team-slug>` (bot name), `rehor-ai-<team-slug>` (label)

When all gathered:
1. `git clone --depth 1` target repos
2. `/detect-tech-stack` on each
3. `needs_team_review` → tag Rehor team (unsupported stack)
4. `/post-plan` w/ config

Store all requirements in metadata.

### `onboarding:plan-posted`

Wait for: "approved", "lgtm", "looks good", "go ahead", "proceed".

Post:
```
## [Phase 1/3] Instance Setup — Action Required: Create Repo

1. **Create GitHub repo**: Org: <team's org>, Name: `<instance_name>`, Public
2. **Grant bot access** — add `platex-rehor-bot` (Write role)
3. **Default branch** — confirm if `main` or `master` (I'll default to `main`)

Reply with repo URL once done.
```

Apply `onboarding:repo-requested`.

### `onboarding:repo-requested`

Wait for repo URL. Verify access via `/auto-fork`.

1. `/generate-instance` w/ requirements JSON → scaffolding + `fork-manifest.json`
2. `/auto-fork --from-manifest <output_dir>/fork-manifest.json` → forks instance repo, outputs fork URL
3. Clone fork, copy scaffolding files, `git submodule add https://github.com/OpenShift-Fleet/rehor.git dev-bot`
4. Push branch `bot/onboarding-<TICKET_KEY>`, open PR

**Note**: No `.tekton/` files — those come from Konflux Phase 2.

Post scaffolding PR link. Apply `onboarding:scaffolding-pr`.

---

## Phase 2: Konflux CI/CD

### `onboarding:scaffolding-pr`

When PR merged:
1. Phase 1 sub-ticket → Done, Phase 2 → In Progress
2. `/auto-fork` target repos from project-repos.json
3. `/post-konflux-questions` `{"epic_key", "team_name"}`

Update metadata: `phase: 2`, `step: "konflux-info"`.

### `onboarding:konflux-info`

Parse Konflux responses. Clone `konflux-release-data` fork → `/generate-konflux` → commit → push → open MR.

(Note: `/generate-konflux` = pure-Python `add-namespace.sh`. Prefer upstream when `yq`/`kubectl`/`kustomize` available.)

Post MR link. Apply `onboarding:konflux-mr`. Store Konflux info in metadata.

### `onboarding:konflux-mr`

When MR merged: `/post-konflux-instructions` `{"epic_key", "instance_name", "quay_org"}`. Apply `onboarding:tekton-setup`.

---

## Phase 3: Deployment

### `onboarding:tekton-setup`

Wait for: pipelines merged, build ran, Quay image exists.

1. Phase 2 sub-ticket → Done, Phase 3 → In Progress
2. Ask for deployment details not yet gathered:
   - **GCP project ID** — required, no default (e.g., `my-team-gcp-project`)
   - **GCP region** — default: `global`
3. `/post-deployment-confirmation` `{"epic_key", "instance_name", "bot_name", "bot_label", "repo_url", "config_name", "quay_org", "pattern", "workflow", "board_name", "sprint_prefix", "gcp_project_id", "gcp_region", "target_branch"}`

Confirmation shows all values including defaults (`target_branch: main`, `gcp_region: global`). Team can correct before MR generation.

Apply `onboarding:deployment-confirmation`. Update metadata: `phase: 3`.

### `onboarding:deployment-confirmation`

Wait for: "looks good", "confirmed", "approved", "lgtm".

Once confirmed: clone app-interface fork → `/generate-app-interface` → commit → push → open MR.

Post MR link. Apply `onboarding:app-interface-mr`.

### `onboarding:app-interface-mr`

When MR merged: `/post-manual-steps` `{"epic_key", "bot_label", "instance_name", "dedicated_proxy"}`.

### `onboarding:manual-steps`

Parse "done" responses. All confirmed → verify checkable items, post summary. Apply `onboarding:verification`.

### `onboarding:verification`

Check: config repo accessible, Jira label exists, target repos forkable.

Post completion msg. Phase 3 sub-ticket → Done. Epic → Done/Release Pending. Apply `onboarding:complete`. Task → `completed`.

---

## Decision Branches

### Shared vs Fresh Infrastructure

Determine early (Phase 1 intake) whether the team uses shared Rehor infrastructure or needs fresh setup. Key question: does the team deploy into the existing `hcmais` namespace with the shared proxy/memory-server, or do they need their own?

**Shared** (most RedHatInsights teams):
- SaaS pattern: `shared` — append to existing `deploy.yml`
- Konflux tenant: may be existing or new
- GCP project: uses the shared project
- Proxy: shared `devbot-proxy` in same namespace
- Fork accounts: `platex-rehor-bot` (GitHub), `platform-experience-services-bot` (GitLab)

**Fresh** (different org, own infra):
- SaaS pattern: `separate` — new SaaS file with configurable refs (`app_ref`, `namespace_ref`, `pipelines_ref`)
- Konflux tenant: almost always new
- GCP project: team must provide their own (surface this early in Phase 1)
- Proxy: dedicated proxy required (different credentials)
- Fork accounts: team must specify their own bot accounts
- Cost center: required, no default
- May need new app-interface namespace/app definitions (coordinate with app-sre)

Surface GCP project and dedicated proxy requirements in Phase 1 intake for fresh teams — don't wait until Phase 3.

### GitHub vs GitLab targets

`github.com` → `gh`, fork to `platex-rehor-bot` (or team's account) | `gitlab.cee.redhat.com` → `glab --hostname`, fork to `platform-experience-services-bot` (or team's account)

### SaaS pattern

Default `shared` (Pattern A — appends to existing deploy.yml) | `separate` (Pattern B — new SaaS file per team). Confirm with team during Phase 3.

### Konflux tenant

New → `/generate-konflux` `new_tenant: true` (requires `cost_center`) | Existing → `new_tenant: false`

---

## Progress Tracking

### Jira Labels (source of truth)

Epic's `onboarding:*` label = authoritative step indicator. Bot applies one label per transition. Preflight reads labels.

### Task Metadata

```json
{"phase":1,"step":"intake","epic_key":"PROJ-123","phase_tickets":{"phase1":"...","phase2":"...","phase3":"..."},"requirements":{"team_name":"","instance_name":"","config_name":"","repo_url":"","github_org":"","repos":[],"workflow":"jira-sprint","bot_name":"devbot-...","bot_label":"rehor-ai-...","instance_id":"","board_name":"","sprint_prefix":"","include_backlog":"false","tech_stacks":[],"pattern":"shared","dedicated_proxy":false},"konflux":{"quay_org":"","tenant":"","cluster":"kflux-prd-rh02","new_tenant":true,"admins":[],"maintainers":[],"cost_center":"","quota_tier":"1.small"},"deployment":{"gcp_project_id":"","gcp_region":"global","target_branch":"main","config_repo":"","config_path":""},"prs":[],"mrs":[],"last_addressed":""}
```

- `step` matches label suffix
- `last_addressed` — update every time feedback addressed
- `pattern` and `dedicated_proxy` — set during Phase 1 requirements gathering
- `prs`/`mrs` — arrays of `{"repo": "...", "number": N, "host": "github|gitlab"}`

**Resume**: `task_get(external_key)` → read metadata → cross-check metadata `step` vs epic label.
**End cycle**: `task_update` w/ updated metadata.

## Canonical Field Names

All skills MUST use these field names. No aliases.

| Canonical | Used in | Meaning |
|-----------|---------|---------|
| `instance_name` | all skills | Name of the bot instance (repo name, Konflux component, deploy param) |
| `repo_url` | generate-konflux, generate-app-interface, detect-tech-stack | Full HTTPS URL of instance repo |
| `target_branch` | generate-konflux, generate-app-interface, detect-tech-stack | Default branch of instance repo (`main` or `master`) |
| `envs` | detect-tech-stack, generate-instance, post-plan | Runtime environments needed (`node`, `browser`, etc.) |
| `personas` | detect-tech-stack, generate-instance, post-plan | Detected personas from repo analysis |
| `epic_key` | all Jira-posting skills | Jira epic key (e.g., `RHCLOUD-12345`) |
| `quay_org` | generate-konflux, generate-app-interface, post-konflux-instructions | Quay org for image push |
| `tenant` | generate-konflux | Konflux tenant namespace name |
| `config_name` | generate-instance, generate-app-interface | Config directory name under `instance/` |
| `config_repo` | generate-app-interface | Repo URL for `BOT_CONFIG_PATH` source (defaults to `repo_url`) |
| `config_path` | generate-app-interface | Path within config_repo to config dir |
| `pattern` | generate-app-interface | SaaS file pattern: `shared` or `separate` |
| `gcp_project_id` | generate-app-interface | GCP project for Vertex AI |
| `gcp_region` | generate-app-interface | GCP region (default: `global`) |
| `bot_name` | generate-instance, generate-app-interface | OpenShift deployment name |
| `bot_label` | generate-instance, generate-app-interface, post-manual-steps | Jira label the bot filters on |
| `dedicated_proxy` | generate-instance | Whether team needs own proxy (fresh infra) |

**Retired aliases** (do NOT use): `source_url`, `default_branch`, `app_name`, `component_name`, `suggested_envs`, `suggested_personas`, `instance_repo_url`.

## Rules

- ONE ticket per cycle
- Feedback > advancing > new tickets
- Blocked/ambiguous → Jira comment + stop
- No Jira spam — read before posting
- Phase headers on every comment
- PR/MR titles: `[Phase N/3] <desc> (<TICKET_KEY>)`
- PR/MR descriptions: link Jira ticket + summary
- After completion: `memory_store` category `learning` tags `onboarding`
- Use runtime env vars: `GH_USER_NAME`, `BOT_JIRA_EMAIL`, `BOT_CONFIG_PATH`

---

## Known Limitations / V2

Things the onboarding workflow cannot yet handle for "fresh" teams (outside shared infrastructure). If a team hits one of these, coordinate manually with the Rehor platform team.

### Dedicated proxy deployment

`deploy-template.yaml.j2` hardcodes ~15 service references to shared infrastructure: `devbot-proxy` (ports 3128, 8443, 8444, 8446, 9090), `devbot-memory-server` (port 8080), and `devbot-secrets`. These are string literals in the Jinja2 template, not OpenShift template parameters. A team needing separate credentials (different Jira/GitHub/GitLab accounts) requires a dedicated proxy, which means either:
- Parameterizing the deploy template to accept proxy/memory-server/secret names
- Creating a separate deploy template variant for dedicated-proxy deployments

The NetworkPolicy also hardcodes pod label selectors for `devbot-proxy` and `memory-server`.

### Arbitrary GitLab hosts

`generate_instance.py` hardcodes `gitlab.cee.redhat.com` for GitLab fork URL construction. Teams using a different GitLab instance (e.g., `gitlab.com`) would get wrong fork URLs.

### Standalone namespace / app-interface service

The `separate` SaaS pattern creates a new SaaS file but defaults all `$ref` paths to the shared `insights/platform-frontend-ai-dev` service tree (app.yml, namespace, pipeline provider). For a team that needs their own namespace on a different cluster, the onboarding workflow would need to also generate:
- A new `app.yml` in app-interface
- A new namespace YAML under the team's service tree
- A new pipeline provider definition

These are app-interface structural files that go beyond what `/generate-app-interface` currently produces. The `app_ref`, `namespace_ref`, and `pipelines_ref` config overrides exist for teams that have already created these files, but the workflow does not create them.

### Arbitrary Konflux clusters

`generate_konflux.py` discovers cluster FQDN suffixes at runtime from the `config/` directory in the cloned `konflux-release-data` repo. A cluster that doesn't have an existing `config/<cluster>.*` directory will raise a `ValueError` with the list of available clusters.