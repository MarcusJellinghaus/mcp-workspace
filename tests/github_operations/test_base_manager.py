"""Unit tests for BaseGitHubManager error handling decorator."""

import logging
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from github import Auth
from github.GithubException import GithubException

from mcp_workspace.github_operations.base_manager import (
    BaseGitHubManager,
    _handle_github_errors,
    get_authenticated_username,
)
from mcp_workspace.utils.repo_identifier import RepoIdentifier


class TestHandleGitHubErrorsDecorator:
    """Unit tests for _handle_github_errors decorator."""

    def test_decorator_success_returns_value(self) -> None:
        """Test that decorator returns function value on success."""

        @_handle_github_errors(default_return={})
        def successful_function() -> dict[str, str]:
            return {"result": "success"}

        result = successful_function()
        assert result == {"result": "success"}

    def test_decorator_auth_error_401_raises(self) -> None:
        """Test that decorator re-raises 401 authentication errors."""

        @_handle_github_errors(default_return={})
        def function_with_auth_error() -> dict[str, str]:
            raise GithubException(401, {"message": "Bad credentials"}, None)

        with pytest.raises(GithubException) as exc_info:
            function_with_auth_error()

        assert exc_info.value.status == 401

    def test_decorator_auth_error_403_raises(self) -> None:
        """Test that decorator re-raises 403 permission errors."""

        @_handle_github_errors(default_return={})
        def function_with_permission_error() -> dict[str, str]:
            raise GithubException(403, {"message": "Forbidden"}, None)

        with pytest.raises(GithubException) as exc_info:
            function_with_permission_error()

        assert exc_info.value.status == 403

    def test_decorator_other_github_error_returns_default(self) -> None:
        """Test that decorator returns default for non-auth GitHub errors."""

        @_handle_github_errors(default_return={"error": "default"})
        def function_with_github_error() -> dict[str, str]:
            raise GithubException(404, {"message": "Not found"}, None)

        result = function_with_github_error()
        assert result == {"error": "default"}

    def test_decorator_generic_exception_returns_default(self) -> None:
        """Test that decorator returns default for generic exceptions (except ValueError)."""

        @_handle_github_errors(default_return={"error": "default"})
        def function_with_generic_error() -> dict[str, str]:
            raise RuntimeError("Something went wrong")

        result = function_with_generic_error()
        assert result == {"error": "default"}

    def test_decorator_value_error_propagates(self) -> None:
        """Test that ValueError is propagated (not caught)."""

        @_handle_github_errors(default_return={"error": "default"})
        def function_with_value_error() -> dict[str, str]:
            raise ValueError("Validation failed")

        with pytest.raises(ValueError, match="Validation failed"):
            function_with_value_error()

    def test_decorator_with_list_default_return(self) -> None:
        """Test that decorator works with list as default return value."""

        @_handle_github_errors(default_return=[])
        def function_returning_list() -> list[str]:
            raise GithubException(500, {"message": "Internal error"}, None)

        result = function_returning_list()
        assert result == []

    def test_decorator_with_bool_default_return(self) -> None:
        """Test that decorator works with bool as default return value."""

        @_handle_github_errors(default_return=False)
        def function_returning_bool() -> bool:
            raise GithubException(500, {"message": "Internal error"}, None)

        result = function_returning_bool()
        assert result is False

    def test_decorator_with_none_default_return(self) -> None:
        """Test that decorator works with None as default return value."""

        @_handle_github_errors(default_return=None)
        def function_returning_optional() -> str | None:
            raise RuntimeError("Error")

        result = function_returning_optional()
        assert result is None

    def test_decorator_preserves_function_args(self) -> None:
        """Test that decorator properly passes arguments to wrapped function."""

        @_handle_github_errors(default_return={})
        def function_with_args(a: int, b: str, c: bool = True) -> dict[str, object]:
            return {"a": a, "b": b, "c": c}

        result = function_with_args(42, "test", c=False)
        assert result == {"a": 42, "b": "test", "c": False}

    def test_decorator_preserves_function_name(self) -> None:
        """Test that decorator preserves function name via functools.wraps."""

        @_handle_github_errors(default_return={})
        def my_function() -> dict[str, str]:
            """My function docstring."""
            return {}

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My function docstring."

    def test_decorator_logs_auth_error(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that decorator logs auth/permission errors before re-raising."""

        @_handle_github_errors(default_return={})
        def function_with_auth_error() -> dict[str, str]:
            raise GithubException(401, {"message": "Bad credentials"}, None)

        with pytest.raises(GithubException):
            function_with_auth_error()

        assert (
            "Authentication/permission error in function_with_auth_error" in caplog.text
        )

    def test_decorator_logs_github_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that decorator logs non-auth GitHub errors."""

        @_handle_github_errors(default_return={})
        def function_with_github_error() -> dict[str, str]:
            raise GithubException(404, {"message": "Not found"}, None)

        result = function_with_github_error()

        assert result == {}
        assert "GitHub API error in function_with_github_error" in caplog.text

    def test_decorator_logs_generic_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that decorator logs generic exceptions."""

        @_handle_github_errors(default_return={})
        def function_with_generic_error() -> dict[str, str]:
            raise RuntimeError("Unexpected error")

        result = function_with_generic_error()

        assert result == {}
        assert "Unexpected error in function_with_generic_error" in caplog.text

    def test_decorator_with_method(self) -> None:
        """Test that decorator works with instance methods."""

        class MyManager:
            @_handle_github_errors(default_return={})
            def my_method(self, value: str) -> dict[str, str]:
                if value == "error":
                    raise RuntimeError("Error occurred")
                return {"value": value}

        manager = MyManager()

        # Success case
        result = manager.my_method("test")
        assert result == {"value": "test"}

        # Error case
        result = manager.my_method("error")
        assert result == {}

    def test_decorator_exception_propagation_for_auth_errors(self) -> None:
        """Test that only auth errors (401, 403) are propagated, others are not."""

        @_handle_github_errors(default_return={"status": "error"})
        def function_with_various_errors(status_code: int) -> dict[str, str]:
            raise GithubException(status_code, {"message": "Error"}, None)

        # Auth errors should be raised
        with pytest.raises(GithubException):
            function_with_various_errors(401)

        with pytest.raises(GithubException):
            function_with_various_errors(403)

        # Other errors should return default
        assert function_with_various_errors(400) == {"status": "error"}
        assert function_with_various_errors(404) == {"status": "error"}
        assert function_with_various_errors(500) == {"status": "error"}
        assert function_with_various_errors(502) == {"status": "error"}


class TestBaseGitHubManagerWithProjectDir:
    """Test suite for BaseGitHubManager initialization with project_dir.

    Tests the existing behavior where BaseGitHubManager is initialized
    with a local git repository path (project_dir parameter).
    """

    def test_successful_initialization_with_project_dir(self) -> None:
        """Test successful initialization with valid project directory."""
        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = True

        with (
            patch(
                "mcp_workspace.github_operations.base_manager.git_operations.is_git_repository",
                return_value=True,
            ),
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            manager = BaseGitHubManager(project_dir=mock_path)

            # Verify manager was initialized correctly
            assert manager.project_dir == mock_path
            assert manager.github_token == "fake_token"
            assert manager._repository is None  # Not fetched yet
            # Lazy: _cached_github_client should be None (not created in __init__)
            assert manager._cached_github_client is None
            # _cached_repo_identifier should be None in project_dir mode
            assert manager._cached_repo_identifier is None

            # Verify Github() was NOT called during init (lazy)
            mock_github_class.assert_not_called()

    def test_initialization_fails_directory_not_exists(self) -> None:
        """Test initialization fails when directory does not exist."""
        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = False

        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch("mcp_workspace.github_operations._client.Github"),
        ):
            with pytest.raises(ValueError) as exc_info:
                BaseGitHubManager(project_dir=mock_path)

            assert "does not exist" in str(exc_info.value)

    def test_initialization_fails_path_not_directory(self) -> None:
        """Test initialization fails when path is not a directory."""
        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = False

        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch("mcp_workspace.github_operations._client.Github"),
        ):
            with pytest.raises(ValueError) as exc_info:
                BaseGitHubManager(project_dir=mock_path)

            assert "not a directory" in str(exc_info.value)

    def test_initialization_fails_not_git_repository(self) -> None:
        """Test initialization fails when directory is not a git repository."""
        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = True

        with (
            patch(
                "mcp_workspace.github_operations.base_manager.git_operations.is_git_repository",
                return_value=False,
            ),
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch("mcp_workspace.github_operations._client.Github"),
        ):
            with pytest.raises(ValueError) as exc_info:
                BaseGitHubManager(project_dir=mock_path)

            assert "not a git repository" in str(exc_info.value)

    def test_initialization_fails_no_github_token(self) -> None:
        """Test initialization fails when GitHub token is not configured."""
        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = True

        with (
            patch(
                "mcp_workspace.github_operations.base_manager.git_operations.is_git_repository",
                return_value=True,
            ),
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value=None,  # No token configured
            ),
            patch("mcp_workspace.github_operations._client.Github"),
        ):
            with pytest.raises(ValueError) as exc_info:
                BaseGitHubManager(project_dir=mock_path)

            assert "GitHub token not found" in str(exc_info.value)

    def test_get_repository_with_project_dir_mode(self) -> None:
        """Test _get_repository() in project_dir mode extracts repo from git remote."""
        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = True

        mock_github_repo = Mock()

        with (
            patch(
                "mcp_workspace.github_operations.base_manager.git_operations.is_git_repository",
                return_value=True,
            ),
            patch(
                "mcp_workspace.github_operations.base_manager.git_operations.get_repository_identifier",
                return_value=RepoIdentifier(owner="test-owner", repo_name="test-repo"),
            ),
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            mock_github_client = Mock()
            mock_github_client.get_repo.return_value = mock_github_repo
            mock_github_class.return_value = mock_github_client

            manager = BaseGitHubManager(project_dir=mock_path)

            # Call _get_repository
            result = manager._get_repository()

            # Verify result
            assert result == mock_github_repo
            assert manager._repository == mock_github_repo  # Cached

            # Verify get_repo was called with correct full name
            mock_github_client.get_repo.assert_called_once_with("test-owner/test-repo")

            # Verify Github() was created with correct base_url
            mock_github_class.assert_called_once()
            call_kwargs = mock_github_class.call_args.kwargs
            assert call_kwargs["base_url"] == "https://api.github.com"

    def test_ghe_project_dir_creates_client_with_ghe_base_url(self) -> None:
        """Test that GHE remote in project_dir mode creates Github with GHE base_url."""
        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = True

        mock_github_repo = Mock()

        with (
            patch(
                "mcp_workspace.github_operations.base_manager.git_operations.is_git_repository",
                return_value=True,
            ),
            patch(
                "mcp_workspace.github_operations.base_manager.git_operations.get_repository_identifier",
                return_value=RepoIdentifier(
                    owner="org", repo_name="repo", hostname="ghe.corp.com"
                ),
            ),
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            mock_github_client = Mock()
            mock_github_client.get_repo.return_value = mock_github_repo
            mock_github_class.return_value = mock_github_client

            manager = BaseGitHubManager(project_dir=mock_path)

            # Trigger lazy client creation via _get_repository
            result = manager._get_repository()

            assert result == mock_github_repo
            # Verify Github() was created with GHE base_url
            mock_github_class.assert_called_once()
            call_kwargs = mock_github_class.call_args.kwargs
            assert call_kwargs["base_url"] == "https://ghe.corp.com/api/v3"


class TestBaseGitHubManagerWithRepoUrl:
    """Test suite for BaseGitHubManager initialization with repo_url.

    Tests the new behavior where BaseGitHubManager is initialized
    with a GitHub repository URL (repo_url parameter).
    """

    def test_successful_initialization_with_https_repo_url(self) -> None:
        """Test successful initialization with valid HTTPS repo_url."""
        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            manager = BaseGitHubManager(
                repo_url="https://github.com/test-owner/test-repo.git"
            )

            # Verify manager was initialized correctly
            assert manager.project_dir is None
            assert manager._cached_repo_identifier is not None
            assert manager._cached_repo_identifier.owner == "test-owner"
            assert manager._cached_repo_identifier.repo_name == "test-repo"
            assert manager._cached_repo_identifier.full_name == "test-owner/test-repo"
            assert manager.github_token == "fake_token"
            assert manager._repository is None  # Not fetched yet

            # Verify Github() was NOT called during init (lazy)
            mock_github_class.assert_not_called()

    def test_successful_initialization_with_https_repo_url_no_git_extension(
        self,
    ) -> None:
        """Test successful initialization with HTTPS repo_url without .git extension."""
        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            manager = BaseGitHubManager(
                repo_url="https://github.com/test-owner/test-repo"
            )

            # Verify manager was initialized correctly
            assert manager.project_dir is None
            assert manager._cached_repo_identifier is not None
            assert manager._cached_repo_identifier.owner == "test-owner"
            assert manager._cached_repo_identifier.repo_name == "test-repo"
            assert manager._cached_repo_identifier.full_name == "test-owner/test-repo"
            assert manager.github_token == "fake_token"
            assert manager._repository is None  # Not fetched yet

            # Verify Github() was NOT called during init (lazy)
            mock_github_class.assert_not_called()

    def test_successful_initialization_with_ssh_repo_url(self) -> None:
        """Test successful initialization with valid SSH repo_url."""
        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            manager = BaseGitHubManager(
                repo_url="git@github.com:test-owner/test-repo.git"
            )

            # Verify manager was initialized correctly
            assert manager.project_dir is None
            assert manager._cached_repo_identifier is not None
            assert manager._cached_repo_identifier.owner == "test-owner"
            assert manager._cached_repo_identifier.repo_name == "test-repo"
            assert manager._cached_repo_identifier.full_name == "test-owner/test-repo"
            assert manager.github_token == "fake_token"
            assert manager._repository is None  # Not fetched yet

            # Verify Github() was NOT called during init (lazy)
            mock_github_class.assert_not_called()

    def test_initialization_fails_invalid_repo_url(self) -> None:
        """Test initialization fails with invalid repo_url."""
        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch("mcp_workspace.github_operations._client.Github"),
        ):
            with pytest.raises(ValueError) as exc_info:
                BaseGitHubManager(repo_url="not-a-valid-url")

            assert "Invalid GitHub repository URL" in str(exc_info.value)

    def test_initialization_fails_malformed_repo_url(self) -> None:
        """Test initialization fails with malformed repo_url."""
        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch("mcp_workspace.github_operations._client.Github"),
        ):
            with pytest.raises(ValueError) as exc_info:
                BaseGitHubManager(repo_url="not-a-valid-url")

            assert "Invalid GitHub repository URL" in str(exc_info.value)

    def test_initialization_fails_no_github_token(self) -> None:
        """Test initialization fails when GitHub token is not configured."""
        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value=None,  # No token configured
            ),
            patch("mcp_workspace.github_operations._client.Github"),
        ):
            with pytest.raises(ValueError) as exc_info:
                BaseGitHubManager(
                    repo_url="https://github.com/test-owner/test-repo.git"
                )

            assert "GitHub token not found" in str(exc_info.value)

    def test_get_repository_with_repo_url_mode(self) -> None:
        """Test _get_repository() in repo_url mode uses stored repo_identifier."""
        mock_github_repo = Mock()

        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            mock_github_client = Mock()
            mock_github_client.get_repo.return_value = mock_github_repo
            mock_github_class.return_value = mock_github_client

            manager = BaseGitHubManager(
                repo_url="https://github.com/test-owner/test-repo.git"
            )

            # Call _get_repository
            result = manager._get_repository()

            # Verify result
            assert result == mock_github_repo
            assert manager._repository == mock_github_repo  # Cached

            # Verify get_repo was called with correct full name
            mock_github_client.get_repo.assert_called_once_with("test-owner/test-repo")

            # Verify Github() created with correct base_url
            mock_github_class.assert_called_once()
            call_kwargs = mock_github_class.call_args.kwargs
            assert call_kwargs["base_url"] == "https://api.github.com"

    def test_ghe_repo_url_creates_client_with_ghe_base_url(self) -> None:
        """Test that GHE repo_url creates Github client with GHE base_url."""
        mock_github_repo = Mock()

        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            mock_github_client = Mock()
            mock_github_client.get_repo.return_value = mock_github_repo
            mock_github_class.return_value = mock_github_client

            manager = BaseGitHubManager(repo_url="https://ghe.corp.com/org/repo")

            # Trigger lazy client creation
            result = manager._get_repository()

            assert result == mock_github_repo
            # Verify Github() was created with GHE base_url
            mock_github_class.assert_called_once()
            call_kwargs = mock_github_class.call_args.kwargs
            assert call_kwargs["base_url"] == "https://ghe.corp.com/api/v3"

    def test_get_repository_caching_with_repo_url(self) -> None:
        """Test _get_repository() caches the repository object in repo_url mode."""
        mock_github_repo = Mock()

        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            mock_github_client = Mock()
            mock_github_client.get_repo.return_value = mock_github_repo
            mock_github_class.return_value = mock_github_client

            manager = BaseGitHubManager(
                repo_url="https://github.com/test-owner/test-repo.git"
            )

            # Call _get_repository multiple times
            result1 = manager._get_repository()
            result2 = manager._get_repository()
            result3 = manager._get_repository()

            # Verify all results are the same
            assert result1 == result2 == result3 == mock_github_repo

            # Verify get_repo was called only once (caching works)
            mock_github_client.get_repo.assert_called_once()

    def test_get_repository_github_api_error_with_repo_url(self) -> None:
        """Test _get_repository() returns None when GitHub API returns error."""
        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            mock_github_client = Mock()
            mock_github_client.get_repo.side_effect = GithubException(
                404, {"message": "Not Found"}, None
            )
            mock_github_class.return_value = mock_github_client

            manager = BaseGitHubManager(
                repo_url="https://github.com/test-owner/test-repo.git"
            )

            # Call _get_repository
            result = manager._get_repository()

            # Verify result is None (API error)
            assert result is None

    def test_get_repository_generic_exception_with_repo_url(self) -> None:
        """Test _get_repository() returns None on unexpected exceptions."""
        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            mock_github_client = Mock()
            mock_github_client.get_repo.side_effect = RuntimeError("Unexpected error")
            mock_github_class.return_value = mock_github_client

            manager = BaseGitHubManager(
                repo_url="https://github.com/test-owner/test-repo.git"
            )

            # Call _get_repository
            result = manager._get_repository()

            # Verify result is None (generic exception)
            assert result is None

    def test_get_repository_caching(self) -> None:
        """Test _get_repository() caches the repository object."""
        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = True

        mock_github_repo = Mock()

        with (
            patch(
                "mcp_workspace.github_operations.base_manager.git_operations.is_git_repository",
                return_value=True,
            ),
            patch(
                "mcp_workspace.github_operations.base_manager.git_operations.get_repository_identifier",
                return_value=RepoIdentifier(owner="test-owner", repo_name="test-repo"),
            ),
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            mock_github_client = Mock()
            mock_github_client.get_repo.return_value = mock_github_repo
            mock_github_class.return_value = mock_github_client

            manager = BaseGitHubManager(project_dir=mock_path)

            # Call _get_repository multiple times
            result1 = manager._get_repository()
            result2 = manager._get_repository()
            result3 = manager._get_repository()

            # Verify all results are the same
            assert result1 == result2 == result3 == mock_github_repo

            # Verify get_repo was called only once (caching works)
            mock_github_client.get_repo.assert_called_once()

    def test_get_repository_no_origin_remote(self) -> None:
        """Test _get_repository() returns None when no origin remote exists."""
        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = True

        with (
            patch(
                "mcp_workspace.github_operations.base_manager.git_operations.is_git_repository",
                return_value=True,
            ),
            patch(
                "mcp_workspace.github_operations.base_manager.git_operations.get_repository_identifier",
                return_value=None,  # No origin remote
            ),
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch("mcp_workspace.github_operations._client.Github"),
        ):
            manager = BaseGitHubManager(project_dir=mock_path)

            # _repo_identifier property should raise ValueError
            with pytest.raises(
                ValueError, match="Could not detect repository from git remote"
            ):
                manager._get_repository()

    def test_get_repository_invalid_github_url(self) -> None:
        """Test _get_repository() raises when remote URL is not a valid GitHub URL."""
        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = True

        with (
            patch(
                "mcp_workspace.github_operations.base_manager.git_operations.is_git_repository",
                return_value=True,
            ),
            patch(
                "mcp_workspace.github_operations.base_manager.git_operations.get_repository_identifier",
                return_value=None,  # Could not parse URL
            ),
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch("mcp_workspace.github_operations._client.Github"),
        ):
            manager = BaseGitHubManager(project_dir=mock_path)

            # _repo_identifier property should raise ValueError
            with pytest.raises(
                ValueError, match="Could not detect repository from git remote"
            ):
                manager._get_repository()

    def test_get_repository_github_api_error(self) -> None:
        """Test _get_repository() returns None when GitHub API returns error."""
        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = True

        with (
            patch(
                "mcp_workspace.github_operations.base_manager.git_operations.is_git_repository",
                return_value=True,
            ),
            patch(
                "mcp_workspace.github_operations.base_manager.git_operations.get_repository_identifier",
                return_value=RepoIdentifier(owner="test-owner", repo_name="test-repo"),
            ),
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            mock_github_client = Mock()
            mock_github_client.get_repo.side_effect = GithubException(
                404, {"message": "Not Found"}, None
            )
            mock_github_class.return_value = mock_github_client

            manager = BaseGitHubManager(project_dir=mock_path)

            # Call _get_repository
            result = manager._get_repository()

            # Verify result is None (API error)
            assert result is None

    def test_get_repository_generic_exception(self) -> None:
        """Test _get_repository() returns None on unexpected exceptions."""
        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = True

        with (
            patch(
                "mcp_workspace.github_operations.base_manager.git_operations.is_git_repository",
                return_value=True,
            ),
            patch(
                "mcp_workspace.github_operations.base_manager.git_operations.get_repository_identifier",
                return_value=RepoIdentifier(owner="test-owner", repo_name="test-repo"),
            ),
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            mock_github_client = Mock()
            mock_github_client.get_repo.side_effect = RuntimeError("Unexpected error")
            mock_github_class.return_value = mock_github_client

            manager = BaseGitHubManager(project_dir=mock_path)

            # Call _get_repository
            result = manager._get_repository()

            # Verify result is None (generic exception)
            assert result is None

    def test_ssh_url_format_parsing(self) -> None:
        """Test _get_repository() correctly parses SSH URL format."""
        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = True

        mock_github_repo = Mock()

        with (
            patch(
                "mcp_workspace.github_operations.base_manager.git_operations.is_git_repository",
                return_value=True,
            ),
            patch(
                "mcp_workspace.github_operations.base_manager.git_operations.get_repository_identifier",
                return_value=RepoIdentifier(owner="test-owner", repo_name="test-repo"),
            ),
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            mock_github_client = Mock()
            mock_github_client.get_repo.return_value = mock_github_repo
            mock_github_class.return_value = mock_github_client

            manager = BaseGitHubManager(project_dir=mock_path)

            # Call _get_repository
            result = manager._get_repository()

            # Verify result
            assert result == mock_github_repo

            # Verify get_repo was called with correct full name (SSH parsed correctly)
            mock_github_client.get_repo.assert_called_once_with("test-owner/test-repo")

    def test_https_url_without_git_extension(self) -> None:
        """Test _get_repository() handles HTTPS URL without .git extension."""
        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = True

        mock_github_repo = Mock()

        with (
            patch(
                "mcp_workspace.github_operations.base_manager.git_operations.is_git_repository",
                return_value=True,
            ),
            patch(
                "mcp_workspace.github_operations.base_manager.git_operations.get_repository_identifier",
                return_value=RepoIdentifier(owner="test-owner", repo_name="test-repo"),
            ),
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            mock_github_client = Mock()
            mock_github_client.get_repo.return_value = mock_github_repo
            mock_github_class.return_value = mock_github_client

            manager = BaseGitHubManager(project_dir=mock_path)

            # Call _get_repository
            result = manager._get_repository()

            # Verify result
            assert result == mock_github_repo

            # Verify get_repo was called with correct full name
            mock_github_client.get_repo.assert_called_once_with("test-owner/test-repo")


class TestBaseGitHubManagerParameterValidation:
    """Test suite for BaseGitHubManager parameter validation.

    Tests error cases where neither or both parameters are provided,
    which should raise ValueError.
    """

    def test_initialization_fails_with_neither_parameter(self) -> None:
        """Test initialization fails when neither project_dir nor repo_url provided."""
        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch("mcp_workspace.github_operations._client.Github"),
        ):
            with pytest.raises(ValueError) as exc_info:
                BaseGitHubManager()

            assert "Exactly one of project_dir or repo_url must be provided" in str(
                exc_info.value
            )

    def test_initialization_fails_with_both_parameters(self) -> None:
        """Test initialization fails when both project_dir and repo_url provided."""
        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = True

        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch("mcp_workspace.github_operations._client.Github"),
        ):
            with pytest.raises(ValueError) as exc_info:
                BaseGitHubManager(
                    project_dir=mock_path,
                    repo_url="https://github.com/test-owner/test-repo.git",
                )

            assert "Exactly one of project_dir or repo_url must be provided" in str(
                exc_info.value
            )


class TestGetAuthenticatedUsername:
    """Tests for get_authenticated_username function."""

    def test_get_authenticated_username_default_hostname(self) -> None:
        """Test get_authenticated_username with default hostname (github.com)."""
        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            mock_github_client = Mock()
            mock_user = Mock()
            mock_user.login = "testuser"
            mock_github_client.get_user.return_value = mock_user
            mock_github_class.return_value = mock_github_client

            result = get_authenticated_username()

            assert result == "testuser"
            mock_github_class.assert_called_once()
            call_kwargs = mock_github_class.call_args.kwargs
            assert call_kwargs["base_url"] == "https://api.github.com"

    def test_get_authenticated_username_ghe_hostname(self) -> None:
        """Test get_authenticated_username with GHE hostname."""
        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            mock_github_client = Mock()
            mock_user = Mock()
            mock_user.login = "ghe_user"
            mock_github_client.get_user.return_value = mock_user
            mock_github_class.return_value = mock_github_client

            result = get_authenticated_username(hostname="ghe.corp.com")

            assert result == "ghe_user"
            mock_github_class.assert_called_once()
            call_kwargs = mock_github_class.call_args.kwargs
            assert call_kwargs["base_url"] == "https://ghe.corp.com/api/v3"


class TestGithubTokenForwarding:
    """Test suite for token forwarding through subclasses.

    Verifies that when ``get_github_token`` is not ``None``, the token
    is properly forwarded to subclasses.
    """

    @pytest.mark.parametrize(
        "manager_cls_path",
        [
            "mcp_workspace.github_operations.issues.manager.IssueManager",
            "mcp_workspace.github_operations.issues.branch_manager.IssueBranchManager",
            "mcp_workspace.github_operations.pr_manager.PullRequestManager",
            "mcp_workspace.github_operations.labels_manager.LabelsManager",
            "mcp_workspace.github_operations.ci_results_manager.CIResultsManager",
        ],
    )
    def test_missing_github_token_falls_back_to_config(
        self, manager_cls_path: str
    ) -> None:
        """Without explicit ``github_token``, fallback to get_github_token is preserved."""
        module_path, cls_name = manager_cls_path.rsplit(".", 1)
        import importlib

        manager_cls = getattr(importlib.import_module(module_path), cls_name)

        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = True

        with (
            patch(
                "mcp_workspace.github_operations.base_manager.git_operations.is_git_repository",
                return_value=True,
            ),
            patch(
                "mcp_workspace.github_operations.base_manager.git_operations.get_repository_identifier",
                return_value=RepoIdentifier(owner="test-owner", repo_name="test-repo"),
            ),
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="config-token",
            ) as mock_get_token,
            patch("mcp_workspace.github_operations._client.Github"),
        ):
            manager = manager_cls(project_dir=mock_path)

            assert manager.github_token == "config-token"
            mock_get_token.assert_called_once()


class TestGetDefaultBranch:
    """Tests for BaseGitHubManager.get_default_branch()."""

    def test_get_default_branch_returns_main(self) -> None:
        """Test get_default_branch returns 'main' when repo default is main."""
        mock_github_repo = Mock()
        mock_github_repo.default_branch = "main"

        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            mock_github_client = Mock()
            mock_github_client.get_repo.return_value = mock_github_repo
            mock_github_class.return_value = mock_github_client

            manager = BaseGitHubManager(
                repo_url="https://github.com/test-owner/test-repo.git"
            )
            result = manager.get_default_branch()

            assert result == "main"

    def test_get_default_branch_returns_master(self) -> None:
        """Test get_default_branch returns 'master' when repo default is master."""
        mock_github_repo = Mock()
        mock_github_repo.default_branch = "master"

        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            mock_github_client = Mock()
            mock_github_client.get_repo.return_value = mock_github_repo
            mock_github_class.return_value = mock_github_client

            manager = BaseGitHubManager(
                repo_url="https://github.com/test-owner/test-repo.git"
            )
            result = manager.get_default_branch()

            assert result == "master"

    def test_get_default_branch_repo_not_accessible(self) -> None:
        """Test get_default_branch raises ValueError when repo is not accessible."""
        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            mock_github_client = Mock()
            mock_github_client.get_repo.side_effect = GithubException(
                404, {"message": "Not Found"}, None
            )
            mock_github_class.return_value = mock_github_client

            manager = BaseGitHubManager(
                repo_url="https://github.com/test-owner/test-repo.git"
            )

            with pytest.raises(ValueError, match="Repository not accessible"):
                manager.get_default_branch()


class TestGetRepositoryDebugLogging:
    """Tests for DEBUG companion log in `_get_repository()` GithubException path."""

    _LOGGER_NAME = "mcp_workspace.github_operations.base_manager"

    def test_debug_log_on_401_includes_allow_listed_fields(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """401 GithubException -> DEBUG includes status, body, allow-listed headers."""
        caplog.set_level(logging.DEBUG, logger=self._LOGGER_NAME)
        exc = GithubException(
            401,
            {"message": "Bad credentials"},
            {
                "WWW-Authenticate": "Bearer",
                "X-GitHub-Request-Id": "ABCD:1234",
            },
        )
        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            mock_github_client = Mock()
            mock_github_client.get_repo.side_effect = exc
            mock_github_class.return_value = mock_github_client
            manager = BaseGitHubManager(
                repo_url="https://github.com/test-owner/test-repo.git"
            )

            result = manager._get_repository()

        assert result is None
        assert "status=401" in caplog.text
        assert "Bad credentials" in caplog.text
        assert "X-GitHub-Request-Id" in caplog.text
        assert "WWW-Authenticate" in caplog.text
        assert "full_name=" in caplog.text
        assert "api_base_url=" in caplog.text
        assert "token=" in caplog.text

    def test_debug_log_includes_token_fingerprint(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A long, ghp_-prefixed token is fingerprinted in DEBUG output."""
        caplog.set_level(logging.DEBUG, logger=self._LOGGER_NAME)
        exc = GithubException(401, {"message": "Bad credentials"}, {})
        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="ghp_LongEnoughTokenABCDxyz",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            mock_github_client = Mock()
            mock_github_client.get_repo.side_effect = exc
            mock_github_class.return_value = mock_github_client
            manager = BaseGitHubManager(
                repo_url="https://github.com/test-owner/test-repo.git"
            )

            manager._get_repository()

        assert "token=ghp_..." in caplog.text

    def test_debug_log_on_404_emitted_and_error_remains(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """404 GithubException -> DEBUG with status=404 AND existing ERROR retained."""
        caplog.set_level(logging.DEBUG, logger=self._LOGGER_NAME)
        exc = GithubException(404, {"message": "Not Found"}, {})
        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            mock_github_client = Mock()
            mock_github_client.get_repo.side_effect = exc
            mock_github_class.return_value = mock_github_client
            manager = BaseGitHubManager(
                repo_url="https://github.com/test-owner/test-repo.git"
            )

            result = manager._get_repository()

        assert result is None
        assert "status=404" in caplog.text
        assert "Repository not found" in caplog.text

    def test_debug_log_excludes_non_allow_listed_headers(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """500 GithubException with Set-Cookie header -> Set-Cookie not logged."""
        caplog.set_level(logging.DEBUG, logger=self._LOGGER_NAME)
        exc = GithubException(
            500,
            {"message": "Internal Server Error"},
            {"Set-Cookie": "session=abc", "X-GitHub-Request-Id": "ABCD:1234"},
        )
        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            mock_github_client = Mock()
            mock_github_client.get_repo.side_effect = exc
            mock_github_class.return_value = mock_github_client
            manager = BaseGitHubManager(
                repo_url="https://github.com/test-owner/test-repo.git"
            )

            manager._get_repository()

        assert "status=500" in caplog.text
        assert "X-GitHub-Request-Id" in caplog.text
        assert "Set-Cookie" not in caplog.text

    def test_raw_token_is_never_in_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        """Raw token middle is never present in DEBUG output."""
        caplog.set_level(logging.DEBUG, logger=self._LOGGER_NAME)
        raw_token = "ghp_RAW_SECRET_TOKEN_VALUE_FOR_TEST_xyz"
        exc = GithubException(401, {"message": "Bad credentials"}, {})
        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value=raw_token,
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            mock_github_client = Mock()
            mock_github_client.get_repo.side_effect = exc
            mock_github_class.return_value = mock_github_client
            manager = BaseGitHubManager(
                repo_url="https://github.com/test-owner/test-repo.git"
            )

            manager._get_repository()

        assert raw_token not in caplog.text
        assert "ghp_..._xyz" in caplog.text


class TestGetAuthenticatedUsernameDebugLogging:
    """Tests for DEBUG companion log in `get_authenticated_username()` GithubException path."""

    _LOGGER_NAME = "mcp_workspace.github_operations.base_manager"

    def test_github_exception_emits_debug_with_allow_listed_fields(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """401 GithubException -> DEBUG includes status, body, allow-listed headers, base_url, token."""
        caplog.set_level(logging.DEBUG, logger=self._LOGGER_NAME)
        exc = GithubException(
            401,
            {"message": "Bad credentials"},
            {"X-GitHub-Request-Id": "abc"},
        )
        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            mock_github_client = Mock()
            mock_github_client.get_user.side_effect = exc
            mock_github_class.return_value = mock_github_client

            with pytest.raises(ValueError, match="Failed to authenticate with GitHub"):
                get_authenticated_username()

        assert "status=401" in caplog.text
        assert "Bad credentials" in caplog.text
        assert "X-GitHub-Request-Id" in caplog.text
        assert "base_url=" in caplog.text
        assert "token=" in caplog.text

    def test_github_exception_token_fingerprint_in_debug(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A long, ghp_-prefixed token is fingerprinted in DEBUG output."""
        caplog.set_level(logging.DEBUG, logger=self._LOGGER_NAME)
        exc = GithubException(401, {"message": "Bad credentials"}, {})
        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="ghp_LongEnoughTokenABCDxyz",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            mock_github_client = Mock()
            mock_github_client.get_user.side_effect = exc
            mock_github_class.return_value = mock_github_client

            with pytest.raises(ValueError):
                get_authenticated_username()

        assert "token=ghp_..." in caplog.text

    def test_generic_exception_no_rich_debug_emitted(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Generic RuntimeError -> ValueError; no GithubException-specific DEBUG line."""
        caplog.set_level(logging.DEBUG, logger=self._LOGGER_NAME)
        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value="fake_token",
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            mock_github_client = Mock()
            mock_github_client.get_user.side_effect = RuntimeError("connection reset")
            mock_github_class.return_value = mock_github_client

            with pytest.raises(ValueError, match="Failed to authenticate with GitHub"):
                get_authenticated_username()

        # The GithubException-specific DEBUG line is not present
        assert "get_authenticated_username GithubException" not in caplog.text

    def test_raw_token_is_never_in_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        """Raw token middle is never present in DEBUG output after 401."""
        caplog.set_level(logging.DEBUG, logger=self._LOGGER_NAME)
        raw_token = "ghp_RAW_SECRET_TOKEN_VALUE_FOR_TEST_xyz"
        exc = GithubException(401, {"message": "Bad credentials"}, {})
        with (
            patch(
                "mcp_workspace.github_operations.base_manager.get_github_token",
                return_value=raw_token,
            ),
            patch(
                "mcp_workspace.github_operations._client.Github"
            ) as mock_github_class,
        ):
            mock_github_client = Mock()
            mock_github_client.get_user.side_effect = exc
            mock_github_class.return_value = mock_github_client

            with pytest.raises(ValueError):
                get_authenticated_username()

        assert raw_token not in caplog.text
        assert "ghp_..._xyz" in caplog.text
