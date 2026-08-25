"""Tests for assemble_claude_md claude_includes and overlay assembly."""

from unittest.mock import MagicMock

import pytest
import yaml


@pytest.fixture(autouse=True)
def _mock_sdk():
    """Mock claude_agent_sdk so bot.run can be imported locally."""
    import sys

    sdk = MagicMock()
    sentinel = object()
    prev = sys.modules.get("claude_agent_sdk", sentinel)
    sys.modules["claude_agent_sdk"] = sdk
    for mod_name in list(sys.modules):
        if mod_name.startswith("bot.agent") or mod_name == "bot.run":
            sys.modules.pop(mod_name, None)
    yield
    if prev is sentinel:
        sys.modules.pop("claude_agent_sdk", None)
    else:
        sys.modules["claude_agent_sdk"] = prev
    for mod_name in list(sys.modules):
        if mod_name.startswith("bot.agent") or mod_name == "bot.run":
            sys.modules.pop(mod_name, None)


def _import_run():
    import bot.run as run_mod

    return run_mod


def _write_preset_tree(tmp_path, *, workflow="jira-sprint", manifest=None, overlay="[WORKFLOW]"):
    script_dir = tmp_path / "app"
    presets = script_dir / "presets"
    (presets / "core").mkdir(parents=True)
    (presets / "core" / "CLAUDE.md").write_text("[CORE]")
    wf = presets / "workflows" / workflow
    wf.mkdir(parents=True)
    (wf / "CLAUDE.md").write_text(overlay)
    data = manifest if manifest is not None else {"name": workflow}
    (wf / "manifest.yaml").write_text(yaml.dump(data))
    return script_dir


class TestClaudeIncludes:
    def test_includes_inserted_after_shared_before_workflow(self, tmp_path):
        script_dir = _write_preset_tree(
            tmp_path,
            manifest={
                "name": "jira-sprint",
                "claude_includes": ["shared/claude/jira-loop.md"],
            },
        )
        include = script_dir / "presets" / "shared" / "claude" / "jira-loop.md"
        include.parent.mkdir(parents=True)
        include.write_text("[LOOP]")

        shared_dir = tmp_path / "shared" / "agent"
        shared_dir.mkdir(parents=True)
        (shared_dir / "CLAUDE.md").write_text("[SHARED]")

        from bot.config import InstanceConfig

        ic = InstanceConfig(workflow="jira-sprint")
        _import_run().assemble_claude_md(script_dir, ic, shared_agent_dir=shared_dir)

        assert (script_dir / "CLAUDE.md").read_text() == "[CORE][SHARED][LOOP][WORKFLOW]"

    def test_includes_preserve_order(self, tmp_path):
        script_dir = _write_preset_tree(
            tmp_path,
            manifest={
                "name": "jira-sprint",
                "claude_includes": [
                    "shared/claude/a.md",
                    "shared/claude/b.md",
                ],
            },
        )
        claude_dir = script_dir / "presets" / "shared" / "claude"
        claude_dir.mkdir(parents=True)
        (claude_dir / "a.md").write_text("[A]")
        (claude_dir / "b.md").write_text("[B]")

        from bot.config import InstanceConfig

        ic = InstanceConfig(workflow="jira-sprint")
        _import_run().assemble_claude_md(script_dir, ic)

        assert (script_dir / "CLAUDE.md").read_text() == "[CORE][A][B][WORKFLOW]"

    def test_missing_include_is_fatal(self, tmp_path):
        script_dir = _write_preset_tree(
            tmp_path,
            manifest={
                "name": "jira-sprint",
                "claude_includes": ["shared/claude/missing.md"],
            },
        )

        from bot.config import InstanceConfig

        ic = InstanceConfig(workflow="jira-sprint")
        with pytest.raises(SystemExit) as exc_info:
            _import_run().assemble_claude_md(script_dir, ic)
        assert exc_info.value.code == 1

    def test_no_includes_key_unchanged(self, tmp_path):
        script_dir = _write_preset_tree(tmp_path, workflow="onboarding")

        from bot.config import InstanceConfig

        ic = InstanceConfig(workflow="onboarding")
        _import_run().assemble_claude_md(script_dir, ic)

        assert (script_dir / "CLAUDE.md").read_text() == "[CORE][WORKFLOW]"

    def test_replace_strategy_skips_includes_and_workflow(self, tmp_path):
        script_dir = _write_preset_tree(
            tmp_path,
            manifest={
                "name": "jira-sprint",
                "claude_includes": ["shared/claude/jira-loop.md"],
            },
        )
        include = script_dir / "presets" / "shared" / "claude" / "jira-loop.md"
        include.parent.mkdir(parents=True)
        include.write_text("[LOOP]")

        instance_dir = tmp_path / "instance" / "agent"
        instance_dir.mkdir(parents=True)
        (instance_dir / "CLAUDE.md").write_text("[INSTANCE]")

        from bot.config import InstanceConfig

        ic = InstanceConfig(workflow="jira-sprint", claude_md_strategy="replace")
        _import_run().assemble_claude_md(script_dir, ic, remote_agent_dir=instance_dir)

        assert (script_dir / "CLAUDE.md").read_text() == "[CORE][INSTANCE]"


class TestWorkflowOverlayGuardrails:
    """Overlays must not re-inline procedures that live in skills / shared loop."""

    _OVERLAYS = (
        "presets/workflows/jira-kanban/CLAUDE.md",
        "presets/workflows/jira-sprint/CLAUDE.md",
    )

    def test_overlays_do_not_inline_gh_pr_create_api(self):
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent.parent
        for rel in self._OVERLAYS:
            text = (root / rel).read_text()
            assert "gh api repos/" not in text, f"{rel} still inlines gh PR create API"

    def test_overlays_do_not_inline_shallow_clone(self):
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent.parent
        for rel in self._OVERLAYS:
            text = (root / rel).read_text()
            assert "git clone --depth 1" not in text, f"{rel} still inlines clone recipe"

    def test_jira_manifests_include_existing_loop(self):
        from pathlib import Path

        import yaml

        root = Path(__file__).resolve().parent.parent.parent
        loop = root / "presets" / "shared" / "claude" / "jira-loop.md"
        assert loop.is_file()
        for name in ("jira-kanban", "jira-sprint"):
            manifest = yaml.safe_load((root / "presets" / "workflows" / name / "manifest.yaml").read_text())
            assert "shared/claude/jira-loop.md" in (manifest.get("claude_includes") or [])
        onboarding = yaml.safe_load((root / "presets" / "workflows" / "onboarding" / "manifest.yaml").read_text())
        assert not onboarding.get("claude_includes")
