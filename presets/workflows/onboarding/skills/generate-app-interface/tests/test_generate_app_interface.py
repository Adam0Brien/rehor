import subprocess

import pytest
from generate_app_interface import (
    _discover_namespace_ref,
    generate,
)

SHARED_CONFIG = {
    "instance_name": "test-agent-dev",
    "bot_name": "devbot-test",
    "bot_label": "rehor-ai-test",
    "instance_id": "test-agent-dev",
    "repo_url": "https://github.com/TestOrg/test-agent-dev",
    "quay_org": "test-tenant",
    "config_name": "test-config",
    "workflow": "jira-sprint",
    "board_name": "Test Board",
    "sprint_prefix": "Sprint",
    "gcp_project_id": "test-gcp-project",
    "gcp_region": "global",
    "target_branch": "main",
    "pattern": "shared",
}

SEPARATE_CONFIG = {**SHARED_CONFIG, "pattern": "separate", "team_name": "testteam"}

KANBAN_CONFIG = {
    **SHARED_CONFIG,
    "workflow": "jira-kanban",
    "board_id": "123",
    "jira_project": "TEST",
}

EXISTING_DEPLOY_CONTENT = """\
---
$schema: /app-sre/saas-file-2.yml

name: platform-frontend-ai-dev
app:
  $ref: /services/insights/platform-frontend-ai-dev/app.yml

imagePatterns:
- quay.io/redhat-services-prod/existing-org/existing-agent

resourceTemplates:
- name: existing-agent
  path: /deploy/template.yaml
  url: https://github.com/ExistingOrg/existing-agent
  targets:
  - namespace:
      $ref: /services/insights/platform-frontend-ai-dev/namespaces/stage.testns01.yml
    ref: main
    images:
    - org:
        $ref: /dependencies/quay/redhat-services-prod.yml
      name: existing-org/existing-agent
    parameters:
      BOT_REPLICAS: '0'
"""

APP_YML_CONTENT = """\
---
name: platform-frontend-ai-dev
codeComponents:
- name: existing-agent
  resource: upstream
  url: https://github.com/ExistingOrg/existing-agent
"""


@pytest.fixture()
def app_interface_repo(tmp_path):
    subprocess.run(
        ["git", "init"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )

    svc_dir = tmp_path / "data" / "services" / "insights" / "platform-frontend-ai-dev"
    svc_dir.mkdir(parents=True)
    (svc_dir / "deploy.yml").write_text(EXISTING_DEPLOY_CONTENT)
    (svc_dir / "app.yml").write_text(APP_YML_CONTENT)

    ns_dir = svc_dir / "namespaces"
    ns_dir.mkdir()
    (ns_dir / "stage.testns01.yml").write_text("---\nname: testns01\n")

    auth_dir = tmp_path / "data" / "services" / "app-sre" / "saas-file-auth"
    auth_dir.mkdir(parents=True)
    (auth_dir / "global.yml").write_text("---\n")

    quay_dir = tmp_path / "data" / "dependencies" / "quay"
    quay_dir.mkdir(parents=True)
    (quay_dir / "redhat-services-prod.yml").write_text("---\n")

    return tmp_path


class TestDiscovery:
    def test_discovers_namespace_ref(self):
        ref = _discover_namespace_ref(EXISTING_DEPLOY_CONTENT)
        assert ref == "/services/insights/platform-frontend-ai-dev/namespaces/stage.testns01.yml"

    def test_returns_none_when_no_namespace(self):
        assert _discover_namespace_ref("no namespace here") is None

    def test_handles_extra_whitespace(self):
        content = "  - namespace:\n        $ref:   /some/path/ns.yml  \n"
        assert _discover_namespace_ref(content) == "/some/path/ns.yml"


class TestSharedPattern:
    def test_returns_modified(self, app_interface_repo):
        result = generate(SHARED_CONFIG, str(app_interface_repo))
        assert result["action"] == "modified"
        assert "deploy.yml" in result["file"]

    def test_deploy_has_instance_name(self, app_interface_repo):
        generate(SHARED_CONFIG, str(app_interface_repo))
        content = (
            app_interface_repo / "data" / "services" / "insights" / "platform-frontend-ai-dev" / "deploy.yml"
        ).read_text()
        assert "- name: test-agent-dev" in content

    def test_deploy_has_image_pattern(self, app_interface_repo):
        generate(SHARED_CONFIG, str(app_interface_repo))
        content = (
            app_interface_repo / "data" / "services" / "insights" / "platform-frontend-ai-dev" / "deploy.yml"
        ).read_text()
        assert "test-tenant/test-agent-dev" in content

    def test_sprint_params(self, app_interface_repo):
        generate(SHARED_CONFIG, str(app_interface_repo))
        content = (
            app_interface_repo / "data" / "services" / "insights" / "platform-frontend-ai-dev" / "deploy.yml"
        ).read_text()
        assert "BOT_BOARD_NAME: Test Board" in content
        assert "BOT_SPRINT_PREFIX: Sprint" in content

    def test_bot_replicas_is_string_zero(self, app_interface_repo):
        generate(SHARED_CONFIG, str(app_interface_repo))
        content = (
            app_interface_repo / "data" / "services" / "insights" / "platform-frontend-ai-dev" / "deploy.yml"
        ).read_text()
        assert "BOT_REPLICAS: '0'" in content

    def test_uses_discovered_namespace_ref(self, app_interface_repo):
        generate(SHARED_CONFIG, str(app_interface_repo))
        content = (
            app_interface_repo / "data" / "services" / "insights" / "platform-frontend-ai-dev" / "deploy.yml"
        ).read_text()
        assert "/services/insights/platform-frontend-ai-dev/namespaces/stage.testns01.yml" in content


class TestDuplicateGuard:
    def test_second_run_unchanged(self, app_interface_repo):
        generate(SHARED_CONFIG, str(app_interface_repo))
        result = generate(SHARED_CONFIG, str(app_interface_repo))
        assert result["action"] == "unchanged"

    def test_no_content_duplication(self, app_interface_repo):
        generate(SHARED_CONFIG, str(app_interface_repo))
        generate(SHARED_CONFIG, str(app_interface_repo))
        content = (
            app_interface_repo / "data" / "services" / "insights" / "platform-frontend-ai-dev" / "deploy.yml"
        ).read_text()
        assert content.count("- name: test-agent-dev") == 1


class TestSeparatePattern:
    def test_returns_created(self, app_interface_repo):
        result = generate(SEPARATE_CONFIG, str(app_interface_repo))
        assert result["action"] == "created"

    def test_has_takeover(self, app_interface_repo):
        result = generate(SEPARATE_CONFIG, str(app_interface_repo))
        saas_path = app_interface_repo / result["file"]
        content = saas_path.read_text()
        assert "takeover: true" in content

    def test_managed_resource_types(self, app_interface_repo):
        result = generate(SEPARATE_CONFIG, str(app_interface_repo))
        saas_path = app_interface_repo / result["file"]
        content = saas_path.read_text()
        assert "ScaledObject.keda.sh" in content

    def test_discovers_namespace_from_shared_deploy(self, app_interface_repo):
        result = generate(SEPARATE_CONFIG, str(app_interface_repo))
        saas_path = app_interface_repo / result["file"]
        content = saas_path.read_text()
        assert "stage.testns01.yml" in content


class TestKanbanWorkflow:
    def test_has_board_id(self, app_interface_repo):
        generate(KANBAN_CONFIG, str(app_interface_repo))
        content = (
            app_interface_repo / "data" / "services" / "insights" / "platform-frontend-ai-dev" / "deploy.yml"
        ).read_text()
        assert "BOT_BOARD_ID: '123'" in content

    def test_no_sprint_params(self, app_interface_repo):
        generate(KANBAN_CONFIG, str(app_interface_repo))
        content = (
            app_interface_repo / "data" / "services" / "insights" / "platform-frontend-ai-dev" / "deploy.yml"
        ).read_text()
        assert "BOT_BOARD_NAME" not in content
        assert "BOT_SPRINT_PREFIX" not in content


class TestCodeComponent:
    def test_adds_code_component(self, app_interface_repo):
        result = generate(SHARED_CONFIG, str(app_interface_repo))
        assert "app_file" in result
        content = (
            app_interface_repo / "data" / "services" / "insights" / "platform-frontend-ai-dev" / "app.yml"
        ).read_text()
        assert "https://github.com/TestOrg/test-agent-dev" in content

    def test_no_duplicate_code_component(self, app_interface_repo):
        generate(SHARED_CONFIG, str(app_interface_repo))
        app_content = (
            app_interface_repo / "data" / "services" / "insights" / "platform-frontend-ai-dev" / "app.yml"
        ).read_text()
        count = app_content.count("https://github.com/TestOrg/test-agent-dev")
        generate(SHARED_CONFIG, str(app_interface_repo))
        app_content2 = (
            app_interface_repo / "data" / "services" / "insights" / "platform-frontend-ai-dev" / "app.yml"
        ).read_text()
        assert app_content2.count("https://github.com/TestOrg/test-agent-dev") == count

    def test_missing_app_yml_no_error(self, app_interface_repo):
        (app_interface_repo / "data" / "services" / "insights" / "platform-frontend-ai-dev" / "app.yml").unlink()
        result = generate(SHARED_CONFIG, str(app_interface_repo))
        assert "app_file" not in result
        assert result["action"] == "modified"
