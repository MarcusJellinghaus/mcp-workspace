"""Issue Manager for GitHub API operations.

This module provides the IssueManager class that composes all mixin classes
for managing GitHub issues through the PyGithub library.
"""

import functools
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, List, Optional

from github.Issue import Issue
from github.Repository import Repository
from mcp_coder_utils.log_utils import log_function_call

from mcp_workspace import config

from ..base_manager import BaseGitHubManager, _handle_github_errors
from ..trust import normalize_author_association
from .base import (
    MalformedBaseBranchError,
    format_malformed_base_branch,
    parse_base_branch,
    validate_issue_number,
)
from .base_branch_trust import is_body_trusted
from .comments_mixin import CommentsMixin
from .events_mixin import EventsMixin
from .labels_mixin import LabelsMixin
from .sub_issues_mixin import SubIssuesMixin
from .types import IssueData, create_empty_issue_data, issue_to_data

logger = logging.getLogger(__name__)

__all__ = ["IssueManager"]

# (repo, issue, message) keys already warned about, so repeat fetches of the
# same malformed issue log at DEBUG instead of flooding the log
_warned_malformed_base_branch: set[tuple[str, int, str]] = set()


def _parse_base_branch_fields(
    manager: BaseGitHubManager,
    repo: Repository,
    github_issue: Issue,
    allowlist: Callable[[], frozenset[str]],
) -> tuple[Optional[str], Optional[str]]:
    """Return (base_branch, base_branch_error), or (None, None) for an untrusted body.

    Args:
        manager: Manager providing the GitHub client for the trust check
        repo: Repository the issue belongs to
        github_issue: Issue whose body is parsed
        allowlist: Zero-argument callable returning the lowercased allowlist;
            called only when the author's role is not trusted

    Returns:
        ``(branch, None)`` for a valid section, ``(None, None)`` for an absent,
        empty or untrusted one, and ``(None, message)`` for a malformed one.
    """
    number = github_issue.number
    error: Optional[MalformedBaseBranchError] = None
    try:
        value = parse_base_branch(github_issue.body or "")
    except MalformedBaseBranchError as exc:
        value, error = None, exc
    # No section: nothing to trust, so no editor request
    if value is None and error is None:
        return None, None

    login = github_issue.user.login if github_issue.user else None
    association = normalize_author_association(github_issue.author_association)
    if not is_body_trusted(manager, repo, number, login, association, allowlist):
        logger.info(
            "Issue #%d: ignoring Base Branch section from untrusted author @%s",
            number,
            login or "ghost",
        )
        return None, None
    if error is None:
        return value, None

    message = format_malformed_base_branch(error)
    key = (repo.full_name.lower(), number, message)
    level = logging.DEBUG if key in _warned_malformed_base_branch else logging.WARNING
    _warned_malformed_base_branch.add(key)
    logger.log(level, "Issue #%d has malformed base branch: %s", number, message)
    return None, message


class IssueManager(
    CommentsMixin, LabelsMixin, EventsMixin, SubIssuesMixin, BaseGitHubManager
):
    """Manages GitHub issue operations using the GitHub API.

    This class provides methods for creating, retrieving, listing, and managing
    GitHub issues and their comments in a repository.

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
        """Initialize the IssueManager.

        Args:
            project_dir: Path to the project directory containing git repository
            repo_url: GitHub repository URL (e.g., "https://github.com/user/repo.git")
            github_token: Optional explicit token — overrides config lookup when provided.

        """
        super().__init__(
            project_dir=project_dir,
            repo_url=repo_url,
            github_token=github_token,
        )

    @log_function_call
    @_handle_github_errors(default_return=create_empty_issue_data())
    def create_issue(
        self,
        title: str,
        body: str = "",
        labels: Optional[List[str]] = None,
        assignees: Optional[List[str]] = None,
    ) -> IssueData:
        """Create a new issue in the repository.

        Args:
            title: Issue title (required, cannot be empty)
            body: Issue description (optional)
            labels: List of label names to apply (optional)
            assignees: List of GitHub usernames to assign (optional)

        Returns:
            IssueData with created issue information, or empty IssueData on error

        Raises:
            ValueError: If title is empty

        Example:
            >>> issue = manager.create_issue(
            ...     title="Bug: Login fails",
            ...     body="Description of the bug",
            ...     labels=["bug", "high-priority"]
            ... )
            >>> print(f"Created issue #{issue['number']}")
        """
        # Validate title
        if not title or not title.strip():
            raise ValueError("Issue title cannot be empty")

        # Get repository
        repo = self._get_repository()
        if repo is None:
            logger.error("Failed to get repository")
            return create_empty_issue_data()

        # Create issue — optional collections are omitted rather than passed
        # as empty, so the no-labels call stays identical to the previous one.
        kwargs: dict[str, Any] = {"title": title.strip(), "body": body}
        if labels:
            kwargs["labels"] = labels
        if assignees:
            kwargs["assignees"] = assignees
        github_issue = repo.create_issue(**kwargs)

        # Convert to IssueData
        return issue_to_data(github_issue)

    @log_function_call
    @_handle_github_errors(default_return=create_empty_issue_data())
    def get_issue(self, issue_number: int) -> IssueData:
        """Retrieve issue details by number.

        Args:
            issue_number: Issue number to retrieve

        Returns:
            IssueData with issue information, or empty IssueData when the
            repository is unavailable. ``base_branch`` and ``base_branch_error``
            are both None when neither the author nor the last body editor is
            trusted.

        Raises:
            IssueIdentityMismatchError: If GitHub returns an issue from another
                repository (the issue was transferred) or with a different number.

        Example:
            >>> issue = manager.get_issue(123)
            >>> print(f"Issue: {issue['title']}")
            >>> print(f"Assignees: {issue['assignees']}")
        """  # noqa: DOC502  # IssueIdentityMismatchError comes from _get_issue_checked
        # Validate issue number
        validate_issue_number(issue_number)

        # Get repository
        repo = self._get_repository()
        if repo is None:
            logger.error("Failed to get repository")
            return create_empty_issue_data()

        # Get issue
        github_issue = self._get_issue_checked(repo, issue_number)

        # Convert to IssueData and parse base_branch from body. Looked up via
        # the module so one test patch on mcp_workspace.config applies.
        allowlist = functools.cache(config.get_trusted_commenters)
        data = issue_to_data(github_issue)
        data["base_branch"], data["base_branch_error"] = _parse_base_branch_fields(
            self, repo, github_issue, allowlist
        )
        return data

    def _list_issues_no_error_handling(
        self,
        state: str = "open",
        include_pull_requests: bool = False,
        since: Optional[datetime] = None,
        labels: Optional[List[str]] = None,
        assignee: Optional[str] = None,
        max_results: Optional[int] = None,
    ) -> List[IssueData]:
        """List issues without error handling. Raises on API failure.

        Private method for callers that need to detect failures (e.g., cache).

        Returns:
            List of IssueData dictionaries with issue information.

        Raises:
            RuntimeError: If the repository cannot be resolved. Propagating the
                failure lets callers (e.g. the cache snapshot/restore path)
                detect it instead of silently treating it as an empty repo.
        """
        # Get repository
        repo = self._get_repository()
        if repo is None:
            raise RuntimeError("Failed to get repository")

        # Build kwargs for PyGithub's get_issues()
        kwargs: dict[str, Any] = {"state": state}
        if since is not None:
            kwargs["since"] = since
        if labels is not None:
            kwargs["labels"] = labels
        if assignee is not None:
            kwargs["assignee"] = assignee

        issues_list: List[IssueData] = []
        issues_iterator = repo.get_issues(**kwargs)
        # Read at most once for the whole list, and only if some body needs it
        allowlist = functools.cache(config.get_trusted_commenters)

        for issue in issues_iterator:
            # Filter out pull requests if not requested
            if not include_pull_requests and issue.pull_request is not None:
                continue

            # Convert to IssueData and parse base_branch from body
            data = issue_to_data(issue)
            data["base_branch"], data["base_branch_error"] = _parse_base_branch_fields(
                self, repo, issue, allowlist
            )
            issues_list.append(data)

            if max_results is not None and len(issues_list) >= max_results:
                break

        return issues_list

    @log_function_call
    @_handle_github_errors(default_return=[])
    def list_issues(
        self,
        state: str = "open",
        include_pull_requests: bool = False,
        since: Optional[datetime] = None,
        labels: Optional[List[str]] = None,
        assignee: Optional[str] = None,
        max_results: Optional[int] = None,
    ) -> List[IssueData]:
        """List all issues in the repository with pagination support.

        Args:
            state: Issue state filter - 'open', 'closed', or 'all' (default: 'open')
            include_pull_requests: Whether to include PRs in results (default: False)
            since: Only fetch issues updated after this time (optional)
            labels: Filter by label names (optional)
            assignee: Filter by assignee username, 'none', or '*' (optional)
            max_results: Maximum number of issues to return (optional)

        Returns:
            List of IssueData dictionaries with issue information, or empty list on error.
            ``base_branch`` and ``base_branch_error`` are both None for an issue
            whose author and last body editor are both untrusted.

        Example:
            >>> issues = manager.list_issues(state='open', include_pull_requests=False)
            >>> print(f"Found {len(issues)} open issues")
            >>> for issue in issues:
            ...     print(f"#{issue['number']}: {issue['title']}")
            >>> # Get issues updated since a specific time
            >>> from datetime import datetime
            >>> cutoff_time = datetime(2023, 1, 1)
            >>> recent_issues = manager.list_issues(since=cutoff_time)
        """
        return self._list_issues_no_error_handling(
            state=state,
            include_pull_requests=include_pull_requests,
            since=since,
            labels=labels,
            assignee=assignee,
            max_results=max_results,
        )

    @log_function_call
    @_handle_github_errors(default_return=create_empty_issue_data())
    def close_issue(self, issue_number: int) -> IssueData:
        """Close an issue.

        Args:
            issue_number: Issue number to close

        Returns:
            IssueData with updated issue information, or empty IssueData when
            the repository is unavailable

        Raises:
            IssueIdentityMismatchError: If GitHub returns an issue from another
                repository (the issue was transferred) or with a different number.

        Example:
            >>> closed_issue = manager.close_issue(123)
            >>> print(f"Issue state: {closed_issue['state']}")
        """  # noqa: DOC502  # IssueIdentityMismatchError comes from _get_issue_checked
        # Validate issue number
        validate_issue_number(issue_number)

        # Get repository
        repo = self._get_repository()
        if repo is None:
            logger.error("Failed to get repository")
            return create_empty_issue_data()

        # Get and close issue
        github_issue = self._get_issue_checked(repo, issue_number)
        github_issue.edit(state="closed")

        # Get fresh issue data after closing
        return issue_to_data(self._get_issue_checked(repo, issue_number))

    @log_function_call
    @_handle_github_errors(default_return=create_empty_issue_data())
    def reopen_issue(self, issue_number: int) -> IssueData:
        """Reopen a closed issue.

        Args:
            issue_number: Issue number to reopen

        Returns:
            IssueData with updated issue information, or empty IssueData when
            the repository is unavailable

        Raises:
            IssueIdentityMismatchError: If GitHub returns an issue from another
                repository (the issue was transferred) or with a different number.

        Example:
            >>> reopened_issue = manager.reopen_issue(123)
            >>> print(f"Issue state: {reopened_issue['state']}")
        """  # noqa: DOC502  # IssueIdentityMismatchError comes from _get_issue_checked
        # Validate issue number
        validate_issue_number(issue_number)

        # Get repository
        repo = self._get_repository()
        if repo is None:
            logger.error("Failed to get repository")
            return create_empty_issue_data()

        # Get and reopen issue
        github_issue = self._get_issue_checked(repo, issue_number)
        github_issue.edit(state="open")

        # Get fresh issue data after reopening
        return issue_to_data(self._get_issue_checked(repo, issue_number))

    @log_function_call
    @_handle_github_errors(default_return=create_empty_issue_data)
    def edit_issue(
        self,
        issue_number: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
        add_labels: Optional[List[str]] = None,
        remove_labels: Optional[List[str]] = None,
        add_assignees: Optional[List[str]] = None,
        state: Optional[str] = None,
        attempted_writes: Optional[List[str]] = None,
    ) -> IssueData:
        """Apply several edits to an issue in one combined operation.

        Composing close_issue/add_labels/remove_labels would repeat the
        fetch-edit-refetch cycle per operation; this does one fetch, one
        ``edit()`` for the scalars, one server-side call per collection, and
        one refetch.

        Args:
            issue_number: Issue number to edit
            title: New issue title, stripped of surrounding whitespace (optional)
            body: New issue description (optional)
            add_labels: Label names to add (optional)
            remove_labels: Label names to remove (optional)
            add_assignees: GitHub usernames to assign (optional)
            state: New issue state — 'open' or 'closed' (optional)
            attempted_writes: Optional list this method appends to, one entry
                per write call, recorded immediately before the call is issued.
                Empty therefore means no write was ever issued — the failure
                came before the first one, or the request had no write to make.

        Returns:
            IssueData with the refetched issue information, or empty IssueData
            when the repository is unavailable or the API call failed

        Raises:
            ValueError: If the issue number is invalid, a supplied title is
                empty, or state is neither 'open' nor 'closed'.
            IssueIdentityMismatchError: If GitHub returns an issue from another
                repository (the issue was transferred) or with a different number.

        Example:
            >>> updated = manager.edit_issue(
            ...     123, title="New title", add_labels=["bug"], state="closed"
            ... )
            >>> print(f"Labels: {updated['labels']}")
        """  # noqa: DOC502  # IssueIdentityMismatchError comes from _get_issue_checked
        # Validate inputs
        validate_issue_number(issue_number)
        # A title left at None means "don't change it"; only a supplied title
        # has to be non-blank, since the strip below would send "" to GitHub.
        if title is not None and not title.strip():
            raise ValueError("Issue title cannot be empty")
        if state is not None and state not in ("open", "closed"):
            raise ValueError("Issue state must be 'open' or 'closed'")

        # Get repository
        repo = self._get_repository()
        if repo is None:
            logger.error("Failed to get repository")
            return create_empty_issue_data()

        # Every write from here on is recorded before it is issued
        writes = attempted_writes if attempted_writes is not None else []

        # Fetch once — the response already carries the current labels. Keyed
        # by casefolded name because GitHub matches label names
        # case-insensitively: removing "Bug" must detach the repo's "bug".
        github_issue = self._get_issue_checked(repo, issue_number)
        current_labels = {
            label.name.casefold(): label.name for label in github_issue.labels
        }

        # Scalars go out together in a single edit() call. Annotated as Any
        # because PyGithub types each edit() keyword separately, so mypy
        # cannot check a **kwargs unpacking against them.
        # The title is stripped exactly as create_issue strips it, so the same
        # input stores the same title whichever path wrote it.
        scalars: dict[str, Any] = {
            key: value
            for key, value in (
                ("title", title.strip() if title is not None else None),
                ("body", body),
                ("state", state),
            )
            if value is not None
        }
        if scalars:
            writes.append("scalars")
            github_issue.edit(**scalars)

        if add_labels:
            writes.append("add_labels")
            github_issue.add_to_labels(*add_labels)

        # remove_from_labels takes a single label, unlike the add_* varargs
        # calls. Removing an absent label 404s, and the swallowed 404 would
        # report the whole edit as failed after the scalars already landed.
        removable = [
            current_labels[name.casefold()]
            for name in remove_labels or []
            if name.casefold() in current_labels
        ]
        if removable:
            writes.append("remove_labels")
            for label_name in removable:
                github_issue.remove_from_labels(label_name)

        if add_assignees:
            writes.append("add_assignees")
            github_issue.add_to_assignees(*add_assignees)

        # Refetch so the returned labels/assignees are the resulting sets
        return issue_to_data(self._get_issue_checked(repo, issue_number))
