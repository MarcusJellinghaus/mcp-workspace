"""Base manager class for GitHub operations.

This module provides the BaseGitHubManager class that contains shared
functionality for all GitHub manager classes.
"""

import functools
import hashlib
import logging
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar, cast

from github import Github
from github.GithubException import GithubException
from github.Issue import Issue
from github.Repository import Repository
from mcp_coder_utils.log_utils import log_function_call
from mcp_coder_utils.user_app_data import get_user_app_data_dir

from mcp_workspace import git_operations
from mcp_workspace.config import get_github_token
from mcp_workspace.github_operations._client import build_github_client
from mcp_workspace.github_operations._diagnostics import (
    extract_diagnostic_headers,
    format_rate_limit_error,
)
from mcp_workspace.github_operations._network import maybe_log_network_diagnostics
from mcp_workspace.utils.repo_identifier import RepoIdentifier, hostname_to_api_base_url
from mcp_workspace.utils.token_fingerprint import format_token_fingerprint

__all__ = [
    "BaseGitHubManager",
    "GithubException",
    "IssueIdentityMismatchError",
    "clear_login_cache",
    "clear_repository_cache",
    "get_authenticated_username",
]

logger = logging.getLogger(__name__)

T = TypeVar("T")

# (api_base_url, sha256(token) hexdigest) -> login. Never key by format_token_fingerprint.
_login_cache: dict[tuple[str, str], str] = {}

# (api_base_url, sha256(token), full_name.lower()) -> (raw_data, raw_headers).
# Plain data only: each manager rebuilds its own Repository on its own client.
_repository_cache: dict[tuple[str, str, str], tuple[dict[str, Any], dict[str, Any]]] = (
    {}
)


def _token_key(base_url: str, token: str) -> tuple[str, str]:
    """Return the cache key part identifying token on base_url.

    Args:
        base_url: GitHub API base URL the token belongs to.
        token: GitHub token; only its SHA-256 hexdigest is kept.

    Returns:
        ``(base_url, sha256(token).hexdigest())``.
    """
    return (base_url, hashlib.sha256(token.encode()).hexdigest())


def _cached_login(token: str, base_url: str, client: Optional[Github] = None) -> str:
    """Return the login for token on base_url, calling GET /user at most once per key.

    Args:
        token: GitHub token whose login is looked up.
        base_url: GitHub API base URL the token belongs to.
        client: Optional existing client for the lookup; built from token and
            base_url when omitted.

    Returns:
        The authenticated user's login.

    Raises:
        Whatever ``get_user()`` raises; failures are not cached.
    """
    key = _token_key(base_url, token)
    if key not in _login_cache:
        github = client if client is not None else build_github_client(token, base_url)
        _login_cache[key] = github.get_user().login
    return _login_cache[key]


def clear_login_cache() -> None:
    """Forget every cached login (used by tests)."""
    _login_cache.clear()


def clear_repository_cache() -> None:
    """Forget every cached repository (used by tests)."""
    _repository_cache.clear()


class IssueIdentityMismatchError(ValueError):
    """Raised when a fetched issue is not the issue that was requested."""


def _format_error_message(e: BaseException) -> str:
    """Derive a short, secret-free description of a GitHub lookup failure.

    Args:
        e: The caught exception.

    Returns:
        ``"GitHub API error {status}: {message}"`` for a GithubException,
        otherwise ``"network error: {exception type}"``. Headers, the token,
        and non-GitHub exception text are never included.
    """
    if isinstance(e, GithubException):
        message = e.data.get("message", "") if isinstance(e.data, dict) else ""
        return f"GitHub API error {e.status}: {message}"
    return f"network error: {type(e).__name__}"


def _handle_github_errors(
    default_return: Any,
    on_error: Optional[Callable[[BaseException, Any], None]] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator to handle GitHub API errors consistently.

    This decorator handles GithubException and general Exception errors:
    - Rate-limit errors (403 rate limit, 429, `RetryError`): logged and re-raised
    - ValueError: Re-raised to caller (validation errors should propagate)
    - Authentication/permission errors (401, 403): Re-raised to caller
    - Other GithubException errors: Logged and return default_return
    - Other exceptions: Logged and return default_return

    Args:
        default_return: Value to return when handling non-auth errors. If a
            zero-arg callable is provided, it is called (as a factory) to
            produce a fresh return value per failure; otherwise the value is
            returned as-is.
        on_error: Optional callback invoked with the caught exception and the
            resolved default value on the non-auth GithubException and generic
            Exception paths only. Its return value is discarded; it may mutate
            the resolved value in place.

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
                msg = format_rate_limit_error(e)
                if msg is not None:
                    logger.error(f"{msg} in {func.__name__}")
                    raise
                # Re-raise authentication/permission errors
                if e.status in (401, 403):
                    logger.error(
                        f"Authentication/permission error in {func.__name__}: {e}"
                    )
                    raise
                # Log and return default for other GitHub errors
                logger.error(f"GitHub API error in {func.__name__}: {e}")
                resolved = (
                    default_return() if callable(default_return) else default_return
                )
                if on_error is not None:
                    on_error(e, resolved)
                return cast(T, resolved)
            except (
                Exception
            ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow exception type
                msg = format_rate_limit_error(e)
                if msg is not None:
                    logger.error(f"{msg} in {func.__name__}")
                    raise
                # Log and return default for unexpected errors
                logger.error(f"Unexpected error in {func.__name__}: {e}")
                resolved = (
                    default_return() if callable(default_return) else default_return
                )
                if on_error is not None:
                    on_error(e, resolved)
                return cast(T, resolved)

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
        return _cached_login(raw_token, base_url)
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
        msg = format_rate_limit_error(e)
        if msg is not None:
            logger.error(msg)
            raise ValueError(msg) from e
        raise ValueError(f"Failed to authenticate with GitHub: {e}") from e
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow exception type
        msg = format_rate_limit_error(e)
        if msg is not None:
            logger.error(msg)
            raise ValueError(msg) from e
        maybe_log_network_diagnostics(e, base_url)
        raise ValueError(f"Failed to authenticate with GitHub: {e}") from e


class BaseGitHubManager:
    """Base class for GitHub managers.

    Provides common initialization and validation logic for GitHub API operations.
    All GitHub manager classes should inherit from this base class.

    Attributes:
        project_dir: Optional path to the project directory (when using local git repo)
        github_token: GitHub personal access token
        repo_identifier: Read-only RepoIdentifier (lazy in project_dir mode)
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
        self._last_repository_error: Optional[str] = None

    @property
    def _repo_identifier(self) -> RepoIdentifier:
        """Lazy property — resolves from git remote in project_dir mode.

        Raises:
            ValueError: If the repository cannot be detected from the
                git remote.
        """
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
    def repo_identifier(self) -> RepoIdentifier:
        """Repository identifier (read-only, lazy).

        Raises:
            ValueError: In project_dir mode when no repository can be detected
                from the git remote.
        """
        return self._repo_identifier

    @property
    def _github_client(self) -> Github:
        """Lazy property — creates Github() with correct base_url."""
        if self._cached_github_client is not None:
            return self._cached_github_client
        base_url = self._repo_identifier.api_base_url
        self._cached_github_client = build_github_client(self.github_token, base_url)
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

        Raises:
            GithubException: Rate-limit errors (403 rate limit, 429) propagate
                to the caller.

        Note:
            The repository object is cached on the instance after the first
            successful retrieval. Its raw data and headers are also cached per
            process, keyed by API host, token hash and lower-cased full name;
            other managers rebuild their own object from that data on their own
            client instead of calling GET /repos. Failures are not cached. A
            requests RetryError from retries exhausted on rate-limit responses
            (or with an unknown status) also propagates to the caller.
        """
        if self._repository is not None:
            return self._repository

        try:
            ident = self._repo_identifier
            key = (
                *_token_key(ident.api_base_url, self.github_token),
                ident.full_name.lower(),
            )
            if key in _repository_cache:
                raw_data, raw_headers = _repository_cache[key]
                self._repository = self._github_client.create_from_raw_data(
                    Repository, raw_data, raw_headers
                )
                return self._repository
            repo = self._github_client.get_repo(ident.full_name)
            _repository_cache[key] = (repo.raw_data, repo.raw_headers)
            self._repository = repo
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
            msg = format_rate_limit_error(e)
            if msg is not None:
                logger.error("%s (repository %s)", msg, repo_url)
                raise
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
            self._last_repository_error = _format_error_message(e)
            return None
        except (
            Exception
        ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow exception type
            msg = format_rate_limit_error(e)
            if msg is not None:
                logger.error("%s (repository %s)", msg, self._repo_identifier.full_name)
                raise
            maybe_log_network_diagnostics(e, self._repo_identifier.api_base_url)
            logger.error(
                "Unexpected error accessing repository '%s': %s",
                self._repo_identifier.full_name,
                e,
            )
            self._last_repository_error = _format_error_message(e)
            return None

    def _get_issue_checked(self, repo: Repository, issue_number: int) -> Issue:
        """Fetch an issue and verify it is the one that was requested.

        GitHub answers the old URL of a transferred issue with a 301 that
        PyGithub follows silently, so the response can be an issue from a
        different repository. Validates identity against the request.

        Args:
            repo: Repository the issue is requested from
            issue_number: Issue number that was requested

        Returns:
            The fetched Issue object

        Raises:
            IssueIdentityMismatchError: If the returned issue belongs to another
                repository, or its number differs from ``issue_number``.
        """
        issue = repo.get_issue(issue_number)

        actual = "/".join(issue.repository_url.rstrip("/").split("/")[-2:])
        if actual.lower() != repo.full_name.lower():
            raise IssueIdentityMismatchError(
                f"Issue #{issue_number} was transferred to "
                f"{actual}#{issue.number} — {issue.html_url}"
            )
        if issue.number != issue_number:
            raise IssueIdentityMismatchError(
                f"Requested issue #{issue_number} but GitHub returned "
                f"#{issue.number} from {actual}"
            )
        return issue
