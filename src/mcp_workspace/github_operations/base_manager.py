"""Base manager class for GitHub operations.

This module provides the BaseGitHubManager class that contains shared
functionality for all GitHub manager classes.
"""

import functools
import logging
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar, cast

from github import Auth, Github
from github.GithubException import GithubException
from github.Repository import Repository
from mcp_coder_utils.log_utils import log_function_call
from mcp_coder_utils.user_app_data import get_user_app_data_dir

from mcp_workspace import git_operations
from mcp_workspace.config import get_github_token
from mcp_workspace.github_operations._diagnostics import extract_diagnostic_headers
from mcp_workspace.utils.repo_identifier import RepoIdentifier, hostname_to_api_base_url
from mcp_workspace.utils.token_fingerprint import format_token_fingerprint

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _handle_github_errors(
    default_return: Any,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator to handle GitHub API errors consistently.

    This decorator handles GithubException and general Exception errors:
    - ValueError: Re-raised to caller (validation errors should propagate)
    - Authentication/permission errors (401, 403): Re-raised to caller
    - Other GithubException errors: Logged and return default_return
    - Other exceptions: Logged and return default_return

    Args:
        default_return: Value to return when handling non-auth errors

    Returns:
        Decorator function that wraps the original function with error handling

    Example:
        @_handle_github_errors(default_return={})
        def create_issue(self, title: str) -> IssueData:
            # Implementation that may raise GithubException
            pass
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                return func(*args, **kwargs)
            except ValueError:
                # Re-raise validation errors to caller
                raise
            except GithubException as e:
                # Re-raise authentication/permission errors
                if e.status in (401, 403):
                    logger.error(
                        f"Authentication/permission error in {func.__name__}: {e}"
                    )
                    raise
                # Log and return default for other GitHub errors
                logger.error(f"GitHub API error in {func.__name__}: {e}")
                return cast(T, default_return)
            except (
                Exception
            ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow exception type
                # Log and return default for unexpected errors
                logger.error(f"Unexpected error in {func.__name__}: {e}")
                return cast(T, default_return)

        return wrapper

    return decorator


def get_authenticated_username(hostname: Optional[str] = None) -> str:
    """Get authenticated GitHub username via PyGithub API.

    Args:
        hostname: GitHub hostname (default: "github.com"). For GHE, e.g. "ghe.corp.com".

    Returns:
        GitHub username string

    Raises:
        ValueError: If GitHub authentication fails or token not configured
    """
    raw_token = get_github_token()

    if not isinstance(raw_token, str):
        raise ValueError(
            "GitHub token not configured. Set via GITHUB_TOKEN environment "
            "variable or config file [github] section"
        )

    base_url = hostname_to_api_base_url(hostname or "github.com")
    try:
        github_client = Github(auth=Auth.Token(raw_token), base_url=base_url)
        user = github_client.get_user()
        return user.login
    except GithubException as e:
        logger.debug(
            "get_authenticated_username GithubException status=%s data=%s "
            "headers=%s base_url=%s token=%s",
            e.status,
            e.data,
            extract_diagnostic_headers(e),
            base_url,
            format_token_fingerprint(raw_token) if raw_token else "<none>",
        )
        raise ValueError(f"Failed to authenticate with GitHub: {e}") from e
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow exception type
        raise ValueError(f"Failed to authenticate with GitHub: {e}") from e


class BaseGitHubManager:
    """Base class for GitHub managers.

    Provides common initialization and validation logic for GitHub API operations.
    All GitHub manager classes should inherit from this base class.

    Attributes:
        project_dir: Optional path to the project directory (when using local git repo)
        github_token: GitHub personal access token
        _cached_repo_identifier: Cached RepoIdentifier (set eagerly for repo_url, lazily for project_dir)
        _cached_github_client: Lazily-created PyGithub client instance
        _repository: Cached GitHub repository object

    Configuration:
        Requires GitHub token in config file (~/.mcp_coder/config.toml):

        [github]
        token = "ghp_your_personal_access_token_here"

        Token needs 'repo' scope for private repositories, 'public_repo' for public.
    """

    def __init__(
        self,
        project_dir: Optional[Path] = None,
        repo_url: Optional[str] = None,
        github_token: Optional[str] = None,
    ) -> None:
        """Initialize the BaseGitHubManager.

        Can be initialized with either a local git repository (project_dir) or
        a GitHub repository URL (repo_url). Exactly one must be provided.

        Args:
            project_dir: Path to the project directory containing git repository
            repo_url: GitHub repository URL (e.g., "https://github.com/user/repo.git")
            github_token: Optional explicit token — overrides config lookup when provided.

        Raises:
            ValueError: If neither or both parameters provided, directory doesn't exist,
                       is not a directory, is not a git repository,
                       or GitHub token is not configured
        """
        # Validate exactly one parameter provided
        if (project_dir is None) == (repo_url is None):
            raise ValueError("Exactly one of project_dir or repo_url must be provided")

        # Initialize attributes
        self.project_dir: Optional[Path] = None
        self._cached_repo_identifier: Optional[RepoIdentifier] = None

        # Validate directory/repository BEFORE checking token
        if project_dir is not None:
            # Validate project_dir
            if not project_dir.exists():
                raise ValueError(f"Directory does not exist: {project_dir}")
            if not project_dir.is_dir():
                raise ValueError(f"Path is not a directory: {project_dir}")
            if not git_operations.is_git_repository(project_dir):
                raise ValueError(f"Directory is not a git repository: {project_dir}")
            self.project_dir = project_dir
        else:
            # Parse repo_url to extract owner/repo
            try:
                self._cached_repo_identifier = RepoIdentifier.from_repo_url(
                    repo_url  # type: ignore[arg-type]
                )
            except ValueError:
                raise ValueError(f"Invalid GitHub repository URL: {repo_url}")

        # Resolve GitHub token (after directory/repository validation).
        if github_token is not None:
            raw_token: object = github_token
        else:
            raw_token = get_github_token()
        if not isinstance(raw_token, str):
            config_path = get_user_app_data_dir("mcp_coder") / "config.toml"
            raise ValueError(
                f"GitHub token not found. Configure it in {config_path} "
                "or set GITHUB_TOKEN environment variable"
            )

        self.github_token = raw_token
        self._cached_github_client: Optional[Github] = None
        self._repository: Optional[Repository] = None

    @property
    def _repo_identifier(self) -> RepoIdentifier:
        """Lazy property — resolves from git remote in project_dir mode."""
        if self._cached_repo_identifier is not None:
            return self._cached_repo_identifier
        # project_dir mode — discover from git remote
        identifier = git_operations.get_repository_identifier(
            self.project_dir  # type: ignore[arg-type]
        )
        if identifier is None:
            raise ValueError("Could not detect repository from git remote")
        self._cached_repo_identifier = identifier
        return identifier

    @property
    def _github_client(self) -> Github:
        """Lazy property — creates Github() with correct base_url."""
        if self._cached_github_client is not None:
            return self._cached_github_client
        base_url = self._repo_identifier.api_base_url
        self._cached_github_client = Github(
            auth=Auth.Token(self.github_token), base_url=base_url
        )
        return self._cached_github_client

    def get_default_branch(self) -> str:
        """Get the default branch name from the GitHub repository.

        Returns:
            Default branch name (e.g., "main", "master", "develop")

        Raises:
            ValueError: If repository is not accessible
        """
        repo = self._get_repository()
        if repo is None:
            raise ValueError("Repository not accessible")
        return repo.default_branch

    @log_function_call
    def _get_repository(self) -> Optional[Repository]:
        """Get the GitHub repository object.

        Uses cached repository if available, otherwise retrieves it from
        the GitHub API using the _repo_identifier.

        Returns:
            Repository object if successful, None otherwise

        Note:
            The repository object is cached after the first successful retrieval
            to avoid unnecessary API calls.
        """
        if self._repository is not None:
            return self._repository

        try:
            self._repository = self._github_client.get_repo(
                self._repo_identifier.full_name
            )
            return self._repository

        except GithubException as e:
            logger.debug(
                "_get_repository GithubException status=%s data=%s headers=%s "
                "full_name=%s api_base_url=%s token=%s",
                e.status,
                e.data,
                extract_diagnostic_headers(e),
                self._repo_identifier.full_name,
                self._repo_identifier.api_base_url,
                (
                    format_token_fingerprint(self.github_token)
                    if self.github_token
                    else "<none>"
                ),
            )
            repo_url = self._repo_identifier.https_url
            if e.status == 404:
                config_path = get_user_app_data_dir("mcp_coder") / "config.toml"
                logger.error(
                    "Repository not found: %s - Check that the repo exists, "
                    "you have access, and the URL in %s is correct.",
                    repo_url,
                    config_path,
                )
            else:
                logger.error(
                    "Failed to access repository %s: %s",
                    repo_url,
                    e,
                )
            return None
        except (
            Exception
        ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow exception type
            logger.error(
                "Unexpected error accessing repository '%s': %s",
                self._repo_identifier.full_name,
                e,
            )
            return None
