"""Tests for reference project dataclass, URL utilities, and ensure_available."""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mcp_workspace.reference_projects import ReferenceProject


class TestReferenceProjectDataclass:
    """Test ReferenceProject dataclass."""

    def test_create_with_defaults(self) -> None:
        """Test creating with name + path only, url is None."""
        from mcp_workspace.reference_projects import ReferenceProject

        proj = ReferenceProject(name="myproj", path=Path("/tmp/myproj"))
        assert proj.name == "myproj"
        assert proj.path == Path("/tmp/myproj")
        assert proj.url is None

    def test_create_with_url(self) -> None:
        """Test creating with all fields set."""
        from mcp_workspace.reference_projects import ReferenceProject

        proj = ReferenceProject(
            name="myproj",
            path=Path("/tmp/myproj"),
            url="https://github.com/org/repo",
        )
        assert proj.name == "myproj"
        assert proj.url == "https://github.com/org/repo"

    def test_path_is_path_object(self) -> None:
        """Test path stored as Path object."""
        from mcp_workspace.reference_projects import ReferenceProject

        proj = ReferenceProject(name="myproj", path=Path("/tmp/myproj"))
        assert isinstance(proj.path, Path)


class TestNormalizeGitUrl:
    """Test normalize_git_url function."""

    def test_ssh_to_https(self) -> None:
        """Test SSH URL converted to HTTPS."""
        from mcp_workspace.reference_projects import normalize_git_url

        result = normalize_git_url("git@github.com:org/repo.git")
        assert result == "https://github.com/org/repo"

    def test_https_strip_dotgit(self) -> None:
        """Test .git suffix stripped from HTTPS URL."""
        from mcp_workspace.reference_projects import normalize_git_url

        result = normalize_git_url("https://github.com/org/repo.git")
        assert result == "https://github.com/org/repo"

    def test_strip_trailing_slash(self) -> None:
        """Test trailing slash removed."""
        from mcp_workspace.reference_projects import normalize_git_url

        result = normalize_git_url("https://github.com/org/repo/")
        assert result == "https://github.com/org/repo"

    def test_lowercase_host(self) -> None:
        """Test host portion lowercased."""
        from mcp_workspace.reference_projects import normalize_git_url

        result = normalize_git_url("https://GitHub.COM/org/repo")
        assert result == "https://github.com/org/repo"

    def test_ssh_non_github(self) -> None:
        """Test SSH URL from non-GitHub host."""
        from mcp_workspace.reference_projects import normalize_git_url

        result = normalize_git_url("git@gitlab.example.com:team/proj.git")
        assert result == "https://gitlab.example.com/team/proj"

    def test_https_already_clean(self) -> None:
        """Test clean URL passes through unchanged."""
        from mcp_workspace.reference_projects import normalize_git_url

        result = normalize_git_url("https://github.com/org/repo")
        assert result == "https://github.com/org/repo"

    def test_ssh_nested_path(self) -> None:
        """Test SSH URL with nested path preserves path."""
        from mcp_workspace.reference_projects import normalize_git_url

        result = normalize_git_url("git@host.com:org/sub/repo.git")
        assert result == "https://host.com/org/sub/repo"


class TestVerifyUrlMatch:
    """Test verify_url_match function."""

    def test_matching_urls_no_error(self) -> None:
        """Test SSH vs HTTPS for same repo raises no exception."""
        from mcp_workspace.reference_projects import verify_url_match

        # Should not raise
        verify_url_match(
            "git@github.com:org/repo.git",
            "https://github.com/org/repo",
            "myproj",
        )

    def test_mismatching_urls_raises(self) -> None:
        """Test different repos raises ValueError."""
        from mcp_workspace.reference_projects import verify_url_match

        with pytest.raises(ValueError, match="URL mismatch"):
            verify_url_match(
                "https://github.com/org/repo1",
                "https://github.com/org/repo2",
                "myproj",
            )

    def test_mismatch_error_includes_project_name(self) -> None:
        """Test error message contains project name."""
        from mcp_workspace.reference_projects import verify_url_match

        with pytest.raises(ValueError, match="myproj"):
            verify_url_match(
                "https://github.com/org/repo1",
                "https://github.com/org/repo2",
                "myproj",
            )


class TestDetectAndVerifyUrl:
    """Test detect_and_verify_url function."""

    @patch("mcp_workspace.git_operations.remotes.get_remote_url")
    @patch("mcp_workspace.git_operations.is_git_repository")
    def test_detect_explicit_url_matches_remote(
        self, mock_is_git: MagicMock, mock_get_url: MagicMock, tmp_path: Path
    ) -> None:
        """Test explicit URL matches detected remote — returns explicit URL."""
        from mcp_workspace.reference_projects import detect_and_verify_url

        mock_is_git.return_value = True
        mock_get_url.return_value = "https://github.com/org/repo"

        result = detect_and_verify_url(
            tmp_path, "git@github.com:org/repo.git", "myproj"
        )
        assert result == "git@github.com:org/repo.git"

    @patch("mcp_workspace.git_operations.remotes.get_remote_url")
    @patch("mcp_workspace.git_operations.is_git_repository")
    def test_detect_explicit_url_mismatch(
        self, mock_is_git: MagicMock, mock_get_url: MagicMock, tmp_path: Path
    ) -> None:
        """Test explicit URL mismatches detected remote — raises ValueError."""
        from mcp_workspace.reference_projects import detect_and_verify_url

        mock_is_git.return_value = True
        mock_get_url.return_value = "https://github.com/org/other-repo"

        with pytest.raises(ValueError, match="URL mismatch"):
            detect_and_verify_url(tmp_path, "https://github.com/org/repo", "myproj")

    @patch("mcp_workspace.git_operations.remotes.get_remote_url")
    @patch("mcp_workspace.git_operations.is_git_repository")
    def test_detect_auto_from_git(
        self, mock_is_git: MagicMock, mock_get_url: MagicMock, tmp_path: Path
    ) -> None:
        """Test no explicit URL, path exists, is git repo — returns auto-detected URL."""
        from mcp_workspace.reference_projects import detect_and_verify_url

        mock_is_git.return_value = True
        mock_get_url.return_value = "https://github.com/org/repo"

        result = detect_and_verify_url(tmp_path, None, "myproj")
        assert result == "https://github.com/org/repo"

    @patch("mcp_workspace.git_operations.remotes.get_remote_url")
    @patch("mcp_workspace.git_operations.is_git_repository")
    def test_detect_no_url_no_git(
        self, mock_is_git: MagicMock, mock_get_url: MagicMock
    ) -> None:
        """Test no explicit URL, path doesn't exist — returns None."""
        from mcp_workspace.reference_projects import detect_and_verify_url

        result = detect_and_verify_url(Path("/nonexistent/path"), None, "myproj")
        assert result is None

    @patch("mcp_workspace.git_operations.remotes.get_remote_url")
    @patch("mcp_workspace.git_operations.is_git_repository")
    def test_detect_explicit_url_path_missing(
        self, mock_is_git: MagicMock, mock_get_url: MagicMock
    ) -> None:
        """Test explicit URL provided, path doesn't exist — returns explicit URL for lazy cloning."""
        from mcp_workspace.reference_projects import detect_and_verify_url

        result = detect_and_verify_url(
            Path("/nonexistent/path"),
            "https://github.com/org/repo",
            "myproj",
        )
        assert result == "https://github.com/org/repo"


class TestEnsureAvailable:
    """Test ensure_available() with async locking and failure cache."""

    @pytest.mark.asyncio
    async def test_dir_exists_returns_immediately(self, tmp_path: Path) -> None:
        """Path exists → no clone attempted."""
        from mcp_workspace.reference_projects import (
            ReferenceProject,
            clear_clone_failure_cache,
            ensure_available,
        )

        clear_clone_failure_cache()
        proj = ReferenceProject(
            name="existing", path=tmp_path, url="https://github.com/org/repo"
        )
        with patch("mcp_workspace.git_operations.remotes.clone_repo") as mock_clone:
            await ensure_available(proj)
            mock_clone.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_dir_no_url_raises(self) -> None:
        """Path missing, no URL → ValueError."""
        from mcp_workspace.reference_projects import (
            ReferenceProject,
            clear_clone_failure_cache,
            ensure_available,
        )

        clear_clone_failure_cache()
        proj = ReferenceProject(
            name="missing", path=Path("/nonexistent/path/abc123"), url=None
        )
        with pytest.raises(ValueError, match="directory missing and no URL configured"):
            await ensure_available(proj)

    @pytest.mark.asyncio
    async def test_clone_triggered_when_url_set(self, tmp_path: Path) -> None:
        """Path missing, URL set → clone_repo called."""
        from mcp_workspace.reference_projects import (
            ReferenceProject,
            clear_clone_failure_cache,
            ensure_available,
        )

        clear_clone_failure_cache()
        target = tmp_path / "new_clone"
        proj = ReferenceProject(
            name="cloneme", path=target, url="https://github.com/org/repo"
        )
        with patch("mcp_workspace.git_operations.remotes.clone_repo") as mock_clone:
            await ensure_available(proj)
            mock_clone.assert_called_once_with("https://github.com/org/repo", target)

    @pytest.mark.asyncio
    async def test_clone_failure_cached(self, tmp_path: Path) -> None:
        """First call fails → second call raises immediately without re-cloning."""
        from mcp_workspace.reference_projects import (
            ReferenceProject,
            clear_clone_failure_cache,
            ensure_available,
        )

        clear_clone_failure_cache()
        target = tmp_path / "fail_clone"
        proj = ReferenceProject(
            name="failproj", path=target, url="https://github.com/org/repo"
        )
        with patch(
            "mcp_workspace.git_operations.remotes.clone_repo",
            side_effect=ValueError("auth required"),
        ) as mock_clone:
            # First call fails
            with pytest.raises(ValueError, match="Failed to clone"):
                await ensure_available(proj)
            assert mock_clone.call_count == 1

            # Second call raises cached error without cloning again
            with pytest.raises(ValueError, match="Clone previously failed"):
                await ensure_available(proj)
            assert mock_clone.call_count == 1  # Not called again

    @pytest.mark.asyncio
    async def test_cache_cleared(self, tmp_path: Path) -> None:
        """After clear_clone_failure_cache(), retry is allowed."""
        from mcp_workspace.reference_projects import (
            ReferenceProject,
            clear_clone_failure_cache,
            ensure_available,
        )

        clear_clone_failure_cache()
        target = tmp_path / "retry_clone"
        proj = ReferenceProject(
            name="retryproj", path=target, url="https://github.com/org/repo"
        )
        with patch(
            "mcp_workspace.git_operations.remotes.clone_repo",
            side_effect=ValueError("auth required"),
        ):
            with pytest.raises(ValueError, match="Failed to clone"):
                await ensure_available(proj)

        # Clear cache
        clear_clone_failure_cache()

        # Now it should try cloning again (not use cached error)
        with patch("mcp_workspace.git_operations.remotes.clone_repo") as mock_clone:
            await ensure_available(proj)
            mock_clone.assert_called_once()

    @pytest.mark.asyncio
    async def test_concurrent_access_single_clone(self, tmp_path: Path) -> None:
        """Two concurrent calls → only one clone."""
        import asyncio

        from mcp_workspace.reference_projects import (
            ReferenceProject,
            clear_clone_failure_cache,
            ensure_available,
        )

        clear_clone_failure_cache()
        target = tmp_path / "concurrent_clone"
        proj = ReferenceProject(
            name="concurrent", path=target, url="https://github.com/org/repo"
        )

        call_count = 0

        def fake_clone(url: str, path: Path) -> None:
            nonlocal call_count
            call_count += 1
            # Simulate that clone creates the directory
            path.mkdir(parents=True, exist_ok=True)

        with patch(
            "mcp_workspace.git_operations.remotes.clone_repo", side_effect=fake_clone
        ):
            await asyncio.gather(ensure_available(proj), ensure_available(proj))

        assert call_count == 1  # Only one clone despite two concurrent calls
