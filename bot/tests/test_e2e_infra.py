"""Tests for E2E infrastructure changes (REHOR-110).

Covers:
- align-playwright-browsers helper script
- 10-chromium.sh credential mapping and extra-hosts loading
- dev-proxy install.sh prerequisite check
- squid.conf playwright domain allowlist
"""

import os
import subprocess
import textwrap

import pytest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestAlignPlaywrightBrowsers:
    """Test the align-playwright-browsers helper embedded in browser/install.sh."""

    @pytest.fixture
    def align_script(self, tmp_path):
        """Extract align-playwright-browsers logic with portable grep (no -P)."""
        script = textwrap.dedent("""\
            #!/bin/bash
            set -e
            REPO_DIR="${1:-.}"
            PW_BROWSERS="${PLAYWRIGHT_BROWSERS_PATH:-/opt/pw-browsers}"
            USER_CACHE="${HOME}/.cache/ms-playwright"

            WANTED=$(cd "$REPO_DIR" && npx playwright install --dry-run 2>&1 | sed -n 's/.*chromium-\\([0-9]*\\).*/\\1/p' | head -1)
            INSTALLED=$(ls -d "$PW_BROWSERS"/chromium-* 2>/dev/null | sed -n 's/.*chromium-\\([0-9]*\\).*/\\1/p' | head -1)

            if [ -z "$WANTED" ] || [ -z "$INSTALLED" ]; then
                echo "[align-pw] Could not determine versions (wanted=$WANTED installed=$INSTALLED)" >&2
                exit 1
            fi

            if [ "$WANTED" = "$INSTALLED" ]; then
                echo "[align-pw] Versions match (chromium-$INSTALLED), no alignment needed"
                exit 0
            fi

            echo "[align-pw] Aligning: repo wants chromium-$WANTED, image has chromium-$INSTALLED"
            mkdir -p "$USER_CACHE"
            for dir in "$PW_BROWSERS"/*/; do
                base=$(basename "$dir")
                target_name=$(echo "$base" | sed "s/-${INSTALLED}/-${WANTED}/")
                if [ "$base" != "$target_name" ]; then
                    ln -sfn "$dir" "$USER_CACHE/$target_name"
                    echo "[align-pw] Linked $target_name -> $dir"
                else
                    ln -sfn "$dir" "$USER_CACHE/$base"
                fi
            done
        """)
        script_path = tmp_path / "align-playwright-browsers"
        script_path.write_text(script)
        script_path.chmod(0o755)
        return script_path

    @pytest.fixture
    def pw_env(self, tmp_path):
        """Set up fake playwright browsers directory."""
        browsers = tmp_path / "pw-browsers"
        (browsers / "chromium-1234").mkdir(parents=True)
        (browsers / "ffmpeg-1011").mkdir(parents=True)

        cache = tmp_path / ".cache" / "ms-playwright"
        cache.mkdir(parents=True)

        return browsers, cache

    def test_versions_match_no_symlinks(self, align_script, pw_env, tmp_path):
        browsers, cache = pw_env
        repo = tmp_path / "repo"
        repo.mkdir()
        mock_npx = repo / "npx"
        mock_npx.write_text("#!/bin/bash\necho 'chromium-1234 some text'\n")
        mock_npx.chmod(0o755)

        env = {
            "PATH": str(repo) + ":" + os.environ.get("PATH", ""),
            "PLAYWRIGHT_BROWSERS_PATH": str(browsers),
            "HOME": str(tmp_path),
        }
        result = subprocess.run(
            ["bash", str(align_script), str(repo)],
            capture_output=True, text=True, env=env, timeout=10,
        )
        assert result.returncode == 0
        assert "Versions match" in result.stdout

    def test_version_mismatch_creates_symlinks(self, align_script, pw_env, tmp_path):
        browsers, cache = pw_env
        repo = tmp_path / "repo"
        repo.mkdir()
        mock_npx = repo / "npx"
        mock_npx.write_text("#!/bin/bash\necho 'chromium-5678 some text'\n")
        mock_npx.chmod(0o755)

        env = {
            "PATH": str(repo) + ":" + os.environ.get("PATH", ""),
            "PLAYWRIGHT_BROWSERS_PATH": str(browsers),
            "HOME": str(tmp_path),
        }
        result = subprocess.run(
            ["bash", str(align_script), str(repo)],
            capture_output=True, text=True, env=env, timeout=10,
        )
        assert result.returncode == 0
        assert "Aligning" in result.stdout
        assert (cache / "chromium-5678").is_symlink()
        assert str(cache / "chromium-5678").endswith("chromium-5678")

    def test_missing_installed_version_exits_1(self, align_script, tmp_path):
        empty_browsers = tmp_path / "empty-browsers"
        empty_browsers.mkdir()
        repo = tmp_path / "repo"
        repo.mkdir()
        mock_npx = repo / "npx"
        mock_npx.write_text("#!/bin/bash\necho 'chromium-1234 some text'\n")
        mock_npx.chmod(0o755)

        env = {
            "PATH": str(repo) + ":" + os.environ.get("PATH", ""),
            "PLAYWRIGHT_BROWSERS_PATH": str(empty_browsers),
            "HOME": str(tmp_path),
        }
        result = subprocess.run(
            ["bash", str(align_script), str(repo)],
            capture_output=True, text=True, env=env, timeout=10,
        )
        assert result.returncode == 1
        assert "Could not determine" in result.stderr


class TestChromiumCredentialMapping:
    """Test E2E credential mapping in 10-chromium.sh."""

    @pytest.fixture
    def credential_script(self, tmp_path):
        """Extract just the credential mapping portion."""
        script = textwrap.dedent("""\
            #!/bin/bash
            # Map SSO credentials to E2E vars (used by Playwright global-setup)
            if [ -n "${SSO_USERNAME:-}" ] && [ -z "${E2E_USER:-}" ]; then
                export E2E_USER="$SSO_USERNAME"
                export E2E_PASSWORD="$SSO_PASSWORD"
            fi
            echo "E2E_USER=${E2E_USER:-unset}"
            echo "E2E_PASSWORD=${E2E_PASSWORD:-unset}"
        """)
        path = tmp_path / "cred-map.sh"
        path.write_text(script)
        path.chmod(0o755)
        return path

    def test_sso_mapped_when_e2e_unset(self, credential_script):
        env = {"SSO_USERNAME": "testuser", "SSO_PASSWORD": "secret123"}
        result = subprocess.run(
            ["bash", str(credential_script)],
            capture_output=True, text=True, env=env, timeout=5,
        )
        assert "E2E_USER=testuser" in result.stdout
        assert "E2E_PASSWORD=secret123" in result.stdout

    def test_e2e_not_overwritten_when_already_set(self, credential_script):
        env = {
            "SSO_USERNAME": "sso-user",
            "SSO_PASSWORD": "sso-pass",
            "E2E_USER": "explicit-user",
            "E2E_PASSWORD": "explicit-pass",
        }
        result = subprocess.run(
            ["bash", str(credential_script)],
            capture_output=True, text=True, env=env, timeout=5,
        )
        assert "E2E_USER=explicit-user" in result.stdout
        assert "E2E_PASSWORD=explicit-pass" in result.stdout

    def test_no_sso_no_mapping(self, credential_script):
        env = {"HOME": "/tmp"}
        result = subprocess.run(
            ["bash", str(credential_script)],
            capture_output=True, text=True, env=env, timeout=5,
        )
        assert "E2E_USER=unset" in result.stdout


class TestExtraHostsLoading:
    """Test extra-hosts file loading from 10-chromium.sh."""

    @pytest.fixture
    def hosts_script(self, tmp_path):
        """Extract just the hosts-loading portion."""
        script = textwrap.dedent("""\
            #!/bin/bash
            HOSTS_FILE="${1:-/dev/null}"
            OUTPUT="${2:-/dev/stdout}"
            > "$OUTPUT"
            if [ -f "$HOSTS_FILE" ]; then
                while IFS= read -r line || [ -n "$line" ]; do
                    line="${line%%#*}"
                    [ -z "${line// /}" ] && continue
                    echo "$line" >> "$OUTPUT"
                done < "$HOSTS_FILE"
            fi
        """)
        path = tmp_path / "load-hosts.sh"
        path.write_text(script)
        path.chmod(0o755)
        return path

    def test_loads_valid_entries(self, hosts_script, tmp_path):
        hosts_file = tmp_path / "extra-hosts"
        hosts_file.write_text("127.0.0.1 stage.foo.redhat.com\n::1 stage.foo.redhat.com\n")
        output = tmp_path / "output"

        subprocess.run(
            ["bash", str(hosts_script), str(hosts_file), str(output)],
            timeout=5, check=True,
        )
        content = output.read_text()
        assert "127.0.0.1 stage.foo.redhat.com" in content
        assert "::1 stage.foo.redhat.com" in content

    def test_strips_comments(self, hosts_script, tmp_path):
        hosts_file = tmp_path / "extra-hosts"
        hosts_file.write_text("# full comment\n127.0.0.1 test.com # inline comment\n")
        output = tmp_path / "output"

        subprocess.run(
            ["bash", str(hosts_script), str(hosts_file), str(output)],
            timeout=5, check=True,
        )
        content = output.read_text()
        assert "full comment" not in content
        assert "127.0.0.1 test.com " in content

    def test_skips_blank_lines(self, hosts_script, tmp_path):
        hosts_file = tmp_path / "extra-hosts"
        hosts_file.write_text("127.0.0.1 a.com\n\n   \n127.0.0.1 b.com\n")
        output = tmp_path / "output"

        subprocess.run(
            ["bash", str(hosts_script), str(hosts_file), str(output)],
            timeout=5, check=True,
        )
        lines = [l for l in output.read_text().strip().split("\n") if l.strip()]
        assert len(lines) == 2


class TestDevProxyInstall:
    """Test dev-proxy/install.sh prerequisite checks."""

    def test_fails_without_go(self, tmp_path):
        script = textwrap.dedent("""\
            #!/bin/bash
            set -e
            if ! command -v go &>/dev/null; then
                echo "ERROR: dev-proxy preset requires go preset (go not found)" >&2
                exit 1
            fi
            echo "go found"
        """)
        path = tmp_path / "check-go.sh"
        path.write_text(script)

        env = {"PATH": "/usr/bin:/bin"}
        result = subprocess.run(
            ["bash", str(path)],
            capture_output=True, text=True, env=env, timeout=5,
        )
        assert result.returncode == 1
        assert "go not found" in result.stderr


class TestSquidPlaywrightAllowlist:
    """Verify squid.conf includes playwright CDN domains."""

    @pytest.fixture
    def squid_conf(self):
        path = os.path.join(REPO_ROOT, "proxy", "squid.conf")
        with open(path) as f:
            return f.read()

    def test_playwright_cdn_allowed(self, squid_conf):
        assert "cdn.playwright.dev" in squid_conf

    def test_playwright_microsoft_cdn_allowed(self, squid_conf):
        assert "playwright.download.prss.microsoft.com" in squid_conf

    def test_redhat_domains_allowed(self, squid_conf):
        assert ".redhat.com" in squid_conf

    def test_no_direct_anthropic_in_allowlist(self, squid_conf):
        lines = [
            l.strip()
            for l in squid_conf.splitlines()
            if l.strip().startswith("acl allowed_domains") and "anthropic" in l.lower()
        ]
        assert len(lines) == 0, "Anthropic API should not be in allowed_domains (goes via Vertex AI)"
