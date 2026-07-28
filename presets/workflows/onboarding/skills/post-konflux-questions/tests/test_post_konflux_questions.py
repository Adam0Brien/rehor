from post_konflux_questions import _build_comment

BASE_CONFIG = {
    "epic_key": "RHCLOUD-123",
    "team_name": "Test Team",
    "instance_name": "test-agent-dev",
}


class TestBuildComment:
    def test_includes_team_name(self):
        comment = _build_comment(BASE_CONFIG)
        assert "Test Team" in comment

    def test_includes_instance_name_in_quay_url(self):
        comment = _build_comment(BASE_CONFIG)
        assert "test-agent-dev" in comment
        assert "<instance_name>" not in comment

    def test_defaults_instance_name_placeholder(self):
        cfg = {"epic_key": "X-1", "team_name": "T"}
        comment = _build_comment(cfg)
        assert "<instance_name>" in comment

    def test_phase_header(self):
        comment = _build_comment(BASE_CONFIG)
        assert "## [Phase 2/3]" in comment

    def test_existing_tenant_section(self):
        comment = _build_comment(BASE_CONFIG)
        assert "Existing tenant" in comment
        assert "Tenant name" in comment

    def test_new_tenant_section(self):
        comment = _build_comment(BASE_CONFIG)
        assert "New tenant" in comment
        assert "Admin usernames" in comment
        assert "Cost center" in comment

    def test_default_team_name(self):
        comment = _build_comment({"epic_key": "X-1"})
        assert "your team" in comment
