# Dev Bot — Local Development

This file is for **local development only**. At runtime, `bot/run.py` overwrites this file by assembling instructions from `presets/core/CLAUDE.md` + optional `claude_includes` + workflow overlay CLAUDE.md files.

## Source of Truth

- **Runtime instructions**: `presets/core/CLAUDE.md` — edit this when changing bot behavior (security, memory, output mode)
- **Shared Jira loop**: `presets/shared/claude/jira-loop.md` — Priority 0–2, PR maintenance, implement (kanban + sprint)
- **Workflow overlay**: `presets/workflows/<name>/CLAUDE.md` — per-workflow deltas only (candidate source, claim notes)
- **Assembly logic**: `bot/run.py` → `assemble_claude_md()`

## How Assembly Works

Layer order: **core → instance-shared → claude_includes → workflow overlay → instance**.

`claude_includes` come from the workflow `manifest.yaml` (paths relative to `presets/`). A missing include is fatal. `jira-sprint` and `jira-kanban` include `shared/claude/jira-loop.md`. Onboarding does not.

`run.py` then applies the instance `claude_md.strategy`:

- **`ignore`** (default): core + shared + includes + workflow overlay
- **`append`**: same, then instance `agent/CLAUDE.md`
- **`replace`**: core + instance-shared + instance `agent/CLAUDE.md` (skips includes and workflow)

The assembled result overwrites this file at startup, so any local edits here are lost in production.

## Local Dev Tips

- To test bot behavior locally, edit `presets/core/CLAUDE.md` and/or `presets/shared/claude/jira-loop.md`
- To test a specific workflow, also edit the workflow overlay CLAUDE.md
- Run `python bot/run.py` to see the assembled output
- This file is copied into the Docker image but immediately overwritten at container startup
