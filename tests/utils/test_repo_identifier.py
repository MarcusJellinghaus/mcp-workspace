"""Tests for RepoIdentifier class and hostname_to_api_base_url()."""

import logging

import pytest

from mcp_workspace.utils.repo_identifier import (
    RepoIdentifier,
    hostname_to_api_base_url,
)


class TestRepoIdentifierFromFullName:
    """Test RepoIdentifier.from_full_name() factory method."""

    def test_valid_owner_repo(self) -> None:
        """Test parsing valid 'owner/repo' format."""
        result = RepoIdentifier.from_full_name("owner/repo")
        assert result.owner == "owner"
        assert result.repo_name == "repo"
        assert result.hostname == "github.com"

    def test_raises_on_no_slash(self) -> None:
        """Test ValueError for input without slash."""
        with pytest.raises(ValueError, match="Invalid repo identifier"):
            RepoIdentifier.from_full_name("just-repo")

    def test_raises_on_multiple_slashes(self) -> None:
        """Test ValueError for input with multiple slashes."""
        with pytest.raises(ValueError, match="Invalid repo identifier"):
            RepoIdentifier.from_full_name("a/b/c")

    def test_raises_on_empty_owner(self) -> None:
        """Test ValueError for '/repo' input."""
        with pytest.raises(ValueError, match="owner cannot be empty"):
            RepoIdentifier.from_full_name("/repo")

    def test_raises_on_empty_repo(self) -> None:
        """Test ValueError for 'owner/' input."""
        with pytest.raises(ValueError, match="repo_name cannot be empty"):
            RepoIdentifier.from_full_name("owner/")

    def test_custom_hostname(self) -> None:
        """Test from_full_name with custom GHE hostname."""
        result = RepoIdentifier.from_full_name("owner/repo", hostname="ghe.corp.com")
        assert result.owner == "owner"
        assert result.repo_name == "repo"
        assert result.hostname == "ghe.corp.com"


class TestRepoIdentifierFromRepoUrl:
    """Test RepoIdentifier.from_repo_url() factory method."""

    def test_https_url(self) -> None:
        """Test parsing HTTPS GitHub URLs."""
        result = RepoIdentifier.from_repo_url("https://github.com/owner/repo")
        assert result.owner == "owner"
        assert result.repo_name == "repo"
        assert result.hostname == "github.com"

    def test_https_url_with_git_suffix(self) -> None:
        """Test parsing HTTPS URLs with .git suffix."""
        result = RepoIdentifier.from_repo_url("https://github.com/owner/repo.git")
        assert result.owner == "owner"
        assert result.repo_name == "repo"
        assert result.hostname == "github.com"

    def test_ssh_url(self) -> None:
        """Test parsing SSH GitHub URLs."""
        result = RepoIdentifier.from_repo_url("git@github.com:owner/repo")
        assert result.owner == "owner"
        assert result.repo_name == "repo"
        assert result.hostname == "github.com"

    def test_ssh_url_with_git_suffix(self) -> None:
        """Test parsing SSH URLs with .git suffix."""
        result = RepoIdentifier.from_repo_url("git@github.com:owner/repo.git")
        assert result.owner == "owner"
        assert result.repo_name == "repo"
        assert result.hostname == "github.com"

    def test_raises_on_invalid_url(self) -> None:
        """Test ValueError for invalid URLs."""
        with pytest.raises(ValueError, match="Invalid repository URL"):
            RepoIdentifier.from_repo_url("invalid")

        with pytest.raises(ValueError, match="Invalid repository URL"):
            RepoIdentifier.from_repo_url("ftp://github.com/owner/repo")

    def test_raises_on_non_string(self) -> None:
        """Test ValueError for non-string input."""
        with pytest.raises(ValueError, match="Repository URL must be a string"):
            RepoIdentifier.from_repo_url(None)  # type: ignore[arg-type]

        with pytest.raises(ValueError, match="Repository URL must be a string"):
            RepoIdentifier.from_repo_url(123)  # type: ignore[arg-type]

    def test_ghe_https_url(self) -> None:
        """Test parsing GHE HTTPS URL."""
        result = RepoIdentifier.from_repo_url("https://ghe.corp.com/org/repo.git")
        assert result.owner == "org"
        assert result.repo_name == "repo"
        assert result.hostname == "ghe.corp.com"

    def test_ghe_ssh_url(self) -> None:
        """Test parsing GHE SSH URL."""
        result = RepoIdentifier.from_repo_url("git@ghe.corp.com:org/repo.git")
        assert result.owner == "org"
        assert result.repo_name == "repo"
        assert result.hostname == "ghe.corp.com"

    def test_https_url_with_token_credentials(self) -> None:
        """Test HTTPS URL with token credentials are stripped."""
        result = RepoIdentifier.from_repo_url("https://token@ghe.corp.com/org/repo.git")
        assert result.owner == "org"
        assert result.repo_name == "repo"
        assert result.hostname == "ghe.corp.com"

    def test_https_url_with_user_pass_credentials(self) -> None:
        """Test HTTPS URL with user:pass credentials are stripped."""
        result = RepoIdentifier.from_repo_url(
            "https://user:pass@github.com/org/repo.git"
        )
        assert result.owner == "org"
        assert result.repo_name == "repo"
        assert result.hostname == "github.com"


class TestRepoIdentifierProperties:
    """Test RepoIdentifier properties and methods."""

    def test_full_name_property(self) -> None:
        """Test full_name returns 'owner/repo' format."""
        repo = RepoIdentifier(owner="MarcusJellinghaus", repo_name="mcp_coder")
        assert repo.full_name == "MarcusJellinghaus/mcp_coder"

    def test_cache_safe_name_property(self) -> None:
        """Test cache_safe_name returns 'hostname_owner_repo' format."""
        repo = RepoIdentifier(owner="MarcusJellinghaus", repo_name="mcp_coder")
        assert repo.cache_safe_name == "github_com_MarcusJellinghaus_mcp_coder"

    def test_cache_safe_name_with_ghe_hostname(self) -> None:
        """Test cache_safe_name includes non-default hostname."""
        repo = RepoIdentifier(
            owner="MarcusJellinghaus",
            repo_name="mcp_coder",
            hostname="ghe.corp.com",
        )
        assert repo.cache_safe_name == "ghe_corp_com_MarcusJellinghaus_mcp_coder"

    def test_str_returns_full_name(self) -> None:
        """Test __str__ returns full_name format."""
        repo = RepoIdentifier(owner="owner", repo_name="repo")
        assert str(repo) == "owner/repo"

    def test_https_url_github_com(self) -> None:
        """Test https_url for github.com."""
        repo = RepoIdentifier(owner="owner", repo_name="repo")
        assert repo.https_url == "https://github.com/owner/repo"

    def test_https_url_ghe(self) -> None:
        """Test https_url for GHE hostname."""
        repo = RepoIdentifier(owner="org", repo_name="app", hostname="ghe.corp.com")
        assert repo.https_url == "https://ghe.corp.com/org/app"

    def test_api_base_url_github_com(self) -> None:
        """Test api_base_url for github.com."""
        repo = RepoIdentifier(owner="owner", repo_name="repo")
        assert repo.api_base_url == "https://api.github.com"

    def test_api_base_url_ghe(self) -> None:
        """Test api_base_url for GHE hostname."""
        repo = RepoIdentifier(owner="org", repo_name="app", hostname="ghe.corp.com")
        assert repo.api_base_url == "https://ghe.corp.com/api/v3"


class TestWebHost:
    """Test RepoIdentifier.web_host property.""" 

    @pytest.mark.parametrize(
        "hostname,expected",
        [
            ("github.com", "https://github.com"),
            ("GitHub.com", "https://github.com"),
            ("tenant.ghe.com", "https://tenant.ghe.com"),
            ("Foo.GHE.com", "https://foo.ghe.com"),
            ("ghe.corp.com", None),
            ("github.example.org", None),
        ],
    )
    def test_web_host(self, hostname: str, expected: str | None) -> None:
        """Test web_host across the three host branches."""
        repo = RepoIdentifier(owner="o", repo_name="r", hostname=hostname)
        assert repo.web_host == expected

    def test_ghe_cloud_no_api_prefix(self) -> None:
        """Test *.ghe.com web_host does NOT contain 'api.' prefix."""
        repo = RepoIdentifier(owner="o", repo_name="r", hostname="tenant.ghe.com")
        assert repo.web_host is not None
        assert "api." not in repo.web_host
        assert repo.web_host == "https://tenant.ghe.com"

    def test_github_com_debug_log(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test github.com branch emits DEBUG with branch and URL."""
        caplog.set_level(logging.DEBUG, logger="mcp_workspace.utils.repo_identifier")
        repo = RepoIdentifier(owner="o", repo_name="r", hostname="github.com")
        _ = repo.web_host
        assert "branch=github.com" in caplog.text
        assert "url=https://github.com" in caplog.text

    def test_ghe_cloud_debug_log(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test *.ghe.com branch emits DEBUG with branch and URL."""
        caplog.set_level(logging.DEBUG, logger="mcp_workspace.utils.repo_identifier")
        repo = RepoIdentifier(owner="o", repo_name="r", hostname="tenant.ghe.com")
        _ = repo.web_host
        assert "branch=ghe.com" in caplog.text
        assert "url=https://tenant.ghe.com" in caplog.text

    def test_ghes_fallback_debug_log(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test GHES fallback branch emits DEBUG with branch and url=None."""
        caplog.set_level(logging.DEBUG, logger="mcp_workspace.utils.repo_identifier")
        repo = RepoIdentifier(owner="o", repo_name="r", hostname="ghe.corp.com")
        _ = repo.web_host
        assert "branch=ghes-fallback" in caplog.text
        assert "url=None" in caplog.text

    def test_mixed_case_input_normalized_in_debug(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test mixed-case input shows both raw and normalized forms in DEBUG."""
        caplog.set_level(logging.DEBUG, logger="mcp_workspace.utils.repo_identifier")
        repo = RepoIdentifier(owner="o", repo_name="r", hostname="GitHub.com")
        _ = repo.web_host
        assert "input=GitHub.com" in caplog.text
        assert "normalized=github.com" in caplog.text


class TestHostnameToApiBaseUrl:
    """Test hostname_to_api_base_url() standalone function."""

    @pytest.mark.parametrize(
        "hostname,expected",
        [
            ("github.com", "https://api.github.com"),
            ("GitHub.com", "https://api.github.com"),
            ("ghe.corp.com", "https://ghe.corp.com/api/v3"),
            ("github.example.org", "https://github.example.org/api/v3"),
        ],
    )
    def test_basic_and_mixed_case(self, hostname: str, expected: str) -> None:
        """Test github.com (with case variations) and GHES fallback."""
        assert hostname_to_api_base_url(hostname) == expected

    def test_ghe_cloud_subdomain(self) -> None:
        """Test *.ghe.com returns subdomain-style API URL."""
        assert (
            hostname_to_api_base_url("tenant.ghe.com") == "https://api.tenant.ghe.com"
        )

    def test_ghe_cloud_mixed_case(self) -> None:
        """Test *.ghe.com lowercases the hostname."""
        assert hostname_to_api_base_url("Foo.GHE.com") == "https://api.foo.ghe.com"

    def test_repo_identifier_api_base_url_propagates_ghe_cloud_fix(self) -> None:
        """Test RepoIdentifier.api_base_url propagates the *.ghe.com fix."""
        repo = RepoIdentifier(owner="o", repo_name="r", hostname="tenant.ghe.com")
        assert repo.api_base_url == "https://api.tenant.ghe.com"


class TestHostnameToApiBaseUrlDebugLogging:
    """Test DEBUG logging output of hostname_to_api_base_url()."""

    def test_github_com_debug_log(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test github.com branch emits DEBUG with branch and URL."""
        caplog.set_level(logging.DEBUG, logger="mcp_workspace.utils.repo_identifier")
        hostname_to_api_base_url("github.com")
        assert "branch=github.com" in caplog.text
        assert "url=https://api.github.com" in caplog.text

    def test_ghe_cloud_debug_log(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test *.ghe.com branch emits DEBUG with branch and URL."""
        caplog.set_level(logging.DEBUG, logger="mcp_workspace.utils.repo_identifier")
        hostname_to_api_base_url("tenant.ghe.com")
        assert "branch=ghe.com" in caplog.text
        assert "url=https://api.tenant.ghe.com" in caplog.text

    def test_ghes_fallback_debug_log(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test GHES fallback branch emits DEBUG with branch and URL."""
        caplog.set_level(logging.DEBUG, logger="mcp_workspace.utils.repo_identifier")
        hostname_to_api_base_url("ghe.corp.com")
        assert "branch=ghes-fallback" in caplog.text
        assert "url=https://ghe.corp.com/api/v3" in caplog.text

    def test_mixed_case_input_normalized_in_debug(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test mixed-case input shows both raw and normalized forms in DEBUG."""
        caplog.set_level(logging.DEBUG, logger="mcp_workspace.utils.repo_identifier")
        hostname_to_api_base_url("GitHub.com")
        assert "input=GitHub.com" in caplog.text
        assert "normalized=github.com" in caplog.text
