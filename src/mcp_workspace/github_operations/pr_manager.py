"""Pull Request Manager for GitHub API operations.

This module provides the PullRequestManager class for managing GitHub pull requests
through the PyGithub library.
"""

import logging
from pathlib import Path
from typing import Any, List, Optional, TypedDict, cast

from github.GithubException import GithubException
from github.PullRequest import PullRequest
from mcp_coder_utils.log_utils import log_function_call

from mcp_workspace.git_operations import get_default_branch_name

from . import _pr_feedback_sources
from .base_manager import BaseGitHubManager, _handle_github_errors

# Configure logger for GitHub operations
logger = logging.getLogger(__name__)


class PullRequestData(TypedDict):
    """TypedDict for pull request data structure."""

    number: int
    title: str
    body: str
    state: str
    head_branch: str
    base_branch: str
    url: str
    created_at: Optional[str]
    updated_at: Optional[str]
    user: Optional[str]
    mergeable: Optional[bool]
    mergeable_state: Optional[str]
    merged: bool
    draft: bool
    assignees: list[str]


class PRFeedback(TypedDict):
    """TypedDict for aggregated PR feedback (review threads, comments, alerts)."""

    unresolved_threads: list[dict[str, Any]]
    resolved_thread_count: int
    changes_requested: list[dict[str, Any]]
    conversation_comments: list[dict[str, Any]]
    alerts: list[dict[str, Any]]
    unavailable: dict[str, Exception]


def _empty_pr_feedback() -> PRFeedback:
    """Return a fresh empty PRFeedback dict."""
    return {
        "unresolved_threads": [],
        "resolved_thread_count": 0,
        "changes_requested": [],
        "conversation_comments": [],
        "alerts": [],
        "unavailable": {},
    }


def _pr_to_data(pr: PullRequest) -> PullRequestData:
    """Flatten a live PyGithub PullRequest into a plain PullRequestData dict."""
    return {
        "number": pr.number,
        "title": pr.title,
        "body": pr.body,
        "state": pr.state,
        "head_branch": pr.head.ref,
        "base_branch": pr.base.ref,
        "url": pr.html_url,
        "created_at": pr.created_at.isoformat() if pr.created_at else None,
        "updated_at": pr.updated_at.isoformat() if pr.updated_at else None,
        "user": pr.user.login if pr.user else None,
        "mergeable": pr.mergeable,
        "mergeable_state": pr.mergeable_state,
        "merged": pr.merged,
        "draft": pr.draft,
        "assignees": [a.login for a in pr.assignees],
    }


class PullRequestManager(BaseGitHubManager):
    """Manages GitHub pull request operations using the GitHub API.

    This class provides methods for creating, retrieving, listing, closing,
    and merging pull requests in a GitHub repository.

    Configuration:
        Requires GitHub token in config file (~/.mcp_coder/config.toml):

        [github]
        token = "ghp_your_personal_access_token_here"

        Token needs 'repo' scope for private repositories, 'public_repo' for public.
    """

    def __init__(self, project_dir: Optional[Path] = None) -> None:
        """Initialize the PullRequestManager.

        Args:
            project_dir: Path to the project directory containing git repository

        Raises:
            ValueError: If project_dir is None, directory doesn't exist, is not a git repository,
                       has no GitHub remote origin, or GitHub token is not configured
        """
        super().__init__(project_dir)

        # _repo_identifier is a lazy property from BaseGitHubManager.
        # Eagerly resolve it here to fail fast if no GitHub remote.
        assert (
            self.project_dir is not None
        ), "project_dir must be set after initialization"
        try:
            _ = self._repo_identifier  # triggers resolution
        except ValueError as e:
            raise ValueError(
                f"Could not detect GitHub repository URL from git remote in: {self.project_dir}. "
                "Make sure the repository has a GitHub remote origin configured."
            ) from e

    def _validate_pr_number(self, pr_number: int) -> bool:
        """Validate pull request number.

        Args:
            pr_number: Pull request number to validate

        Returns:
            True if valid, False otherwise
        """
        if not isinstance(pr_number, int) or pr_number <= 0:
            logger.error(f"Invalid PR number: {pr_number}. Must be a positive integer.")
            return False
        return True

    def _validate_branch_name(self, branch_name: str) -> bool:
        """Validate branch name.

        Args:
            branch_name: Branch name to validate

        Returns:
            True if valid, False otherwise
        """
        if not isinstance(branch_name, str) or not branch_name.strip():
            logger.error(
                f"Invalid branch name: '{branch_name}'. Must be a non-empty string."
            )
            return False
        # GitHub branch name restrictions
        invalid_chars = ["~", "^", ":", "?", "*", "["]
        if any(char in branch_name for char in invalid_chars):
            logger.error(
                f"Invalid branch name: '{branch_name}'. Contains invalid characters: {invalid_chars}"
            )
            return False
        if (
            branch_name.startswith(".")
            or branch_name.endswith(".")
            or branch_name.endswith(".lock")
        ):
            logger.error(
                f"Invalid branch name: '{branch_name}'. Cannot start/end with '.' or end with '.lock'"
            )
            return False
        return True

    @log_function_call
    @_handle_github_errors(cast(PullRequestData, {}))
    def create_pull_request(
        self,
        title: str,
        head_branch: str,
        base_branch: Optional[str] = None,
        body: str = "",
    ) -> PullRequestData:
        """Create a new pull request.

        Args:
            title: Title of the pull request (must be non-empty)
            head_branch: Source branch for the pull request
            base_branch: Target branch for the pull request (default: repository default branch)
            body: Description/body of the pull request (optional)

        Returns:
            PullRequestData containing pull request information or empty dict on failure.

            Success response includes:
            - number: PR number (int)
            - title: PR title (str)
            - body: PR description (str)
            - state: PR state, typically "open" (str)
            - head_branch: Source branch name (str)
            - base_branch: Target branch name (str)
            - url: GitHub URL to the PR (str)
            - created_at: ISO timestamp (str)
            - updated_at: ISO timestamp (str)
            - user: GitHub username of creator (str)
            - mergeable: Whether PR can be merged (bool)
            - mergeable_state: Mergeability state string (str)
            - merged: Whether PR is already merged (bool)
            - draft: Whether PR is a draft (bool)
            - assignees: GitHub usernames assigned to the PR (list[str])
        """
        # Resolve base_branch if not provided
        if base_branch is None:
            if self.project_dir is None:
                logger.error("project_dir required for default branch resolution")
                return cast(PullRequestData, {})
            resolved_base = get_default_branch_name(self.project_dir)
            if resolved_base is None:
                logger.error("Could not determine default branch for repository")
                return cast(PullRequestData, {})
            base_branch = resolved_base
            logger.debug(f"Using repository default branch: {base_branch}")

        # Validate title
        if not isinstance(title, str) or not title.strip():
            logger.error(f"Invalid PR title: '{title}'. Must be a non-empty string.")
            return cast(PullRequestData, {})

        # Validate branch names
        if not self._validate_branch_name(head_branch):
            return cast(PullRequestData, {})
        if not self._validate_branch_name(base_branch):
            return cast(PullRequestData, {})

        repo = self._get_repository()
        if repo is None:
            return cast(PullRequestData, {})

        # Create the pull request using GitHub API
        pr = repo.create_pull(
            title=title, body=body, head=head_branch, base=base_branch
        )

        return _pr_to_data(pr)

    @log_function_call
    @_handle_github_errors(cast(PullRequestData, {}))
    def get_pull_request(self, pr_number: int) -> PullRequestData:
        """Get information about a specific pull request.

        Args:
            pr_number: Pull request number

        Returns:
            PullRequestData containing pull request information or empty dict on failure
        """
        # Validate PR number
        if not self._validate_pr_number(pr_number):
            return cast(PullRequestData, {})

        repo = self._get_repository()
        if repo is None:
            return cast(PullRequestData, {})

        # Get the pull request using GitHub API
        pr = repo.get_pull(pr_number)

        return _pr_to_data(pr)

    @log_function_call
    @_handle_github_errors(lambda: [])
    def list_pull_requests(
        self,
        state: str = "open",
        base_branch: Optional[str] = None,
        max_results: Optional[int] = None,
    ) -> List[PullRequestData]:
        """List pull requests in the repository.

        Args:
            state: State of pull requests to list ("open", "closed", "all")
            base_branch: Filter by base branch (optional)
            max_results: Maximum number of results to return (optional, returns all if None)

        Returns:
            List of PullRequestData containing pull request information or empty list on failure.
            Each item in the list has the same structure as create_pull_request() return value.
        """
        # Validate base_branch if provided
        if base_branch is not None and not self._validate_branch_name(base_branch):
            return []

        try:
            repo = self._get_repository()
            if repo is None:
                return []

            # Get pull requests using GitHub API
            # Handle optional base_branch parameter for GitHub API
            if base_branch is not None:
                prs = repo.get_pulls(state=state, base=base_branch)
            else:
                prs = repo.get_pulls(state=state)

            # Convert to structured list of dictionaries
            pr_list = []
            for i, pr in enumerate(prs):
                # Stop if we've reached max_results limit
                if max_results is not None and i >= max_results:
                    break

                pr_list.append(_pr_to_data(pr))

            return pr_list

        except GithubException as e:
            # Log the error and return empty list on failure
            logger.error(f"GitHub API error listing pull requests: {e}")
            return []

    @log_function_call
    @_handle_github_errors([])
    def find_pull_request_by_head(self, head_branch: str) -> List[PullRequestData]:
        """Find open pull requests by head branch name.

        Args:
            head_branch: Branch name (e.g., "feature/xyz") — method constructs
                        "owner:branch" internally for the GitHub API query.

        Returns:
            List of PullRequestData for matching open PRs, or empty list on error/not found.
        """
        if not self._validate_branch_name(head_branch):
            return []

        repo = self._get_repository()
        if repo is None:
            return []

        owner = self._repo_identifier.owner
        prs = repo.get_pulls(state="open", head=f"{owner}:{head_branch}")

        return [_pr_to_data(pr) for pr in prs]

    @log_function_call
    @_handle_github_errors(cast(PullRequestData, {}))
    def close_pull_request(self, pr_number: int) -> PullRequestData:
        """Close a pull request.

        Args:
            pr_number: Pull request number to close

        Returns:
            PullRequestData containing updated pull request information or empty dict on failure
        """
        # Validate PR number
        if not self._validate_pr_number(pr_number):
            return cast(PullRequestData, {})

        repo = self._get_repository()
        if repo is None:
            return cast(PullRequestData, {})

        # Get the pull request using GitHub API
        pr = repo.get_pull(pr_number)

        # Close the pull request by editing it
        pr.edit(state="closed")

        # Get updated PR information after closing
        updated_pr = repo.get_pull(pr_number)

        return _pr_to_data(updated_pr)

    @log_function_call
    @_handle_github_errors(cast(PullRequestData, {}))
    def add_assignees(self, pr_number: int, *logins: str) -> PullRequestData:
        """Add one or more assignees to an existing pull request.

        Wraps PyGithub's PullRequest.add_to_assignees(*logins) on the authenticated
        PyGithub path. Returns the updated PullRequestData.

        Note: GitHub silently drops logins that are not assignable (not a collaborator /
        no repo access) — add_to_assignees succeeds with no error and no effect, so a
        non-empty return is not proof the user was actually assigned. Intended for
        best-effort use.

        Args:
            pr_number: Pull request number
            *logins: GitHub usernames to assign to the pull request

        Returns:
            PullRequestData containing updated pull request information or empty dict
            on failure
        """
        if not self._validate_pr_number(pr_number):
            return cast(PullRequestData, {})

        repo = self._get_repository()
        if repo is None:
            return cast(PullRequestData, {})

        pr = repo.get_pull(pr_number)

        # Empty *logins -> no API write (no-op); still returns current PR data.
        if logins:
            pr.add_to_assignees(*logins)

        return _pr_to_data(pr)

    @log_function_call
    @_handle_github_errors(default_return=[])
    def get_closing_issue_numbers(self, pr_number: int) -> List[int]:
        """Query closing issue references for a PR via GraphQL.

        Args:
            pr_number: Pull request number to query

        Returns:
            List of issue numbers linked as closing references, or empty list on error
        """
        if not self._validate_pr_number(pr_number):
            return []

        repo = self._get_repository()
        if repo is None:
            return []

        owner, repo_name = repo.owner.login, repo.name

        query = """
        query($owner: String!, $repo: String!, $prNumber: Int!) {
          repository(owner: $owner, name: $repo) {
            pullRequest(number: $prNumber) {
              closingIssuesReferences(first: 10) {
                nodes {
                  number
                }
              }
            }
          }
        }
        """

        variables = {
            "owner": owner,
            "repo": repo_name,
            "prNumber": pr_number,
        }

        _, result = self._github_client._Github__requester.graphql_query(  # type: ignore[attr-defined]  # pylint: disable=protected-access  # no public GraphQL API in PyGithub
            query=query, variables=variables
        )

        try:
            pr_data = result.get("data", {}).get("repository", {}).get("pullRequest")
            if pr_data is None:
                logger.warning(f"PR #{pr_number} not found")
                return []

            nodes = pr_data.get("closingIssuesReferences", {}).get("nodes", [])
            return [node["number"] for node in nodes if node]

        except (KeyError, TypeError) as e:
            logger.error(f"Error parsing GraphQL response: {e}")
            return []

    @log_function_call
    @_handle_github_errors(default_return=_empty_pr_feedback)
    def get_pr_feedback(self, pr_number: int) -> PRFeedback:
        """Fetch aggregated PR feedback (review threads, comments, alerts).

        Args:
            pr_number: Pull request number to query

        Returns:
            PRFeedback dict containing unresolved threads, resolved thread count,
            CHANGES_REQUESTED reviews, conversation comments, code-scanning alerts,
            and a dict mapping failed section names to the raised exception
            (excluding 403 on alerts, which is silently skipped).
        """
        if not self._validate_pr_number(pr_number):
            return _empty_pr_feedback()

        unavailable: dict[str, Exception] = {}

        try:
            threads, resolved_count, changes_requested = (
                _pr_feedback_sources.fetch_review_data(self, pr_number)
            )
        except (
            Exception
        ) as e:  # pylint: disable=broad-exception-caught  # one section failure must not abort
            logger.warning(f"Failed to fetch review data for PR #{pr_number}: {e}")
            threads, resolved_count, changes_requested = ([], 0, [])
            unavailable["threads"] = e

        try:
            comments = _pr_feedback_sources.fetch_conversation_comments(self, pr_number)
        except (
            Exception
        ) as e:  # pylint: disable=broad-exception-caught  # one section failure must not abort
            logger.warning(
                f"Failed to fetch conversation comments for PR #{pr_number}: {e}"
            )
            comments = []
            unavailable["comments"] = e

        try:
            alerts_or_none = _pr_feedback_sources.fetch_code_scanning_alerts(
                self, pr_number
            )
            alerts = alerts_or_none if alerts_or_none is not None else []
        except (
            Exception
        ) as e:  # pylint: disable=broad-exception-caught  # one section failure must not abort
            logger.warning(
                f"Failed to fetch code-scanning alerts for PR #{pr_number}: {e}"
            )
            alerts = []
            unavailable["alerts"] = e

        return {
            "unresolved_threads": threads,
            "resolved_thread_count": resolved_count,
            "changes_requested": changes_requested,
            "conversation_comments": comments,
            "alerts": alerts,
            "unavailable": unavailable,
        }

    @property
    def repository_name(self) -> str:
        """Get the repository name in 'owner/repo' format.

        Returns:
            Repository name in format "owner/repo" or empty string on failure
        """
        try:
            return self._repo_identifier.full_name
        except Exception:  # pylint: disable=broad-exception-caught
            return ""

    @property
    def default_branch(self) -> str:
        """Get the default branch of the repository.

        Returns:
            Default branch name (typically "main" or "master") or empty string on failure
        """
        try:
            # project_dir is guaranteed to be non-None for PullRequestManager
            assert self.project_dir is not None, "project_dir must be set"
            default_branch = get_default_branch_name(self.project_dir)
            return default_branch or ""
        except (
            Exception
        ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow exception type
            logger.debug(f"Error getting default branch: {e}")
            return ""
