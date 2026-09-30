"""Sub-issues mixin for IssueManager.

This module provides the SubIssuesMixin class containing native GitHub
sub-issue link operations (add, remove, list).
"""

from __future__ import annotations

import logging
from itertools import islice
from typing import List, NamedTuple, Optional, cast

from github.GithubException import GithubException
from github.Issue import Issue, SubIssue
from github.Repository import Repository
from github.SubIssueSummary import SubIssueSummary
from mcp_coder_utils.log_utils import log_function_call

from ..base_manager import BaseGitHubManager, IssueIdentityMismatchError
from .base import validate_issue_number

logger = logging.getLogger(__name__)

__all__ = ["SubIssueLink", "SubIssuesMixin", "sub_issue_total"]


class SubIssueLink(NamedTuple):
    """Outcome of a successful link or unlink."""

    url: str
    """The parent issue's URL."""
    total: Optional[int]
    """The parent's sub-issue count after the write, or None when unknown."""


def sub_issue_total(issue: Issue) -> Optional[int]:
    """Return the issue's sub-issue count, or None when GitHub sent no summary.

    PyGithub annotates ``sub_issues_summary`` as non-Optional but returns None
    when the payload lacks the key; the cast states the real type.

    Args:
        issue: PyGithub Issue to read

    Returns:
        Total number of sub-issues, or None when the summary is absent
    """
    summary = cast(Optional[SubIssueSummary], issue.sub_issues_summary)
    return None if summary is None else summary.total


def _fetch_issue(manager: BaseGitHubManager, repo: Repository, number: int) -> Issue:
    """Fetch an issue with the transferred-issue guard and reject pull requests.

    Args:
        manager: Manager used to fetch the issue
        repo: Repository to fetch from
        number: Issue number

    Returns:
        The fetched issue

    Raises:
        ValueError: If the number refers to a pull request.
    """
    issue = manager._get_issue_checked(repo, number)  # pylint: disable=protected-access
    if issue.pull_request is not None:
        raise ValueError(f"#{number} is a pull request, not an issue")
    return issue


def _write_link(
    manager: BaseGitHubManager,
    parent_number: int,
    child_number: int,
    unlink: bool,
) -> Optional[SubIssueLink]:
    """Link or unlink a sub-issue and report the parent's resulting state.

    Args:
        manager: Manager used for the API calls
        parent_number: Parent issue number
        child_number: Child issue number
        unlink: Remove the link when True, add it when False

    Returns:
        The parent's URL and sub-issue count, or None when the repository is
        unavailable
    """
    validate_issue_number(parent_number)
    validate_issue_number(child_number)

    repo = manager._get_repository()  # pylint: disable=protected-access
    if repo is None:
        logger.error("Failed to get repository")
        return None

    parent = _fetch_issue(manager, repo, parent_number)
    # The child is fetched for the guard and for its internal id, which
    # PyGithub reads off the object — the API does not take the issue number.
    child = _fetch_issue(manager, repo, child_number)
    if unlink:
        parent.remove_sub_issue(child)
    else:
        parent.add_sub_issue(child)

    # Refetch: the pre-write parent's summary does not include this write.
    # The write has landed, so a failed refetch only loses the count.
    try:
        refetched = manager._get_issue_checked(  # pylint: disable=protected-access
            repo, parent_number
        )
    except (GithubException, IssueIdentityMismatchError) as exc:
        logger.warning("Refetching #%d after the write failed: %s", parent_number, exc)
        return SubIssueLink(parent.html_url, None)
    return SubIssueLink(refetched.html_url, sub_issue_total(refetched))


# No @_handle_github_errors here, unlike the other mixins: that decorator
# (base_manager.py:78) swallows every non-401/403 GithubException, which would
# discard the 404/422 text the tools must surface. GithubException propagates
# to the server layer instead.
class SubIssuesMixin:
    """Mixin providing native sub-issue link operations.

    This mixin is designed to be used with BaseGitHubManager.
    """

    @log_function_call
    def add_sub_issue(
        self: "BaseGitHubManager", parent_number: int, child_number: int
    ) -> Optional[SubIssueLink]:
        """Link an existing issue as a sub-issue of another.

        Args:
            parent_number: Parent issue number
            child_number: Issue number to link under the parent

        Returns:
            The parent's URL and sub-issue count (count None when the
            post-write refetch fails), or None when the repository is
            unavailable

        Raises:
            ValueError: If a number is invalid or refers to a pull request.
            IssueIdentityMismatchError: If GitHub returns an issue from another
                repository (the issue was transferred) or with a different number.
            GithubException: If the API call fails.
        """  # noqa: DOC502  # raised by _write_link and PyGithub
        return _write_link(self, parent_number, child_number, unlink=False)

    @log_function_call
    def remove_sub_issue(
        self: "BaseGitHubManager", parent_number: int, child_number: int
    ) -> Optional[SubIssueLink]:
        """Unlink a sub-issue from its parent.

        Args:
            parent_number: Parent issue number
            child_number: Issue number to unlink from the parent

        Returns:
            The parent's URL and sub-issue count (count None when the
            post-write refetch fails), or None when the repository is
            unavailable

        Raises:
            ValueError: If a number is invalid or refers to a pull request.
            IssueIdentityMismatchError: If GitHub returns an issue from another
                repository (the issue was transferred) or with a different number.
            GithubException: If the API call fails.
        """  # noqa: DOC502  # raised by _write_link and PyGithub
        return _write_link(self, parent_number, child_number, unlink=True)

    @log_function_call
    def list_sub_issues(
        self: "BaseGitHubManager", parent_number: int, max_results: int = 30
    ) -> Optional[List[SubIssue]]:
        """List an issue's sub-issues.

        Args:
            parent_number: Parent issue number
            max_results: Maximum number of sub-issues to return

        Returns:
            Sub-issues in API order, or None when the repository is unavailable

        Raises:
            ValueError: If the number is invalid or refers to a pull request.
            IssueIdentityMismatchError: If GitHub returns an issue from another
                repository (the issue was transferred) or with a different number.
            GithubException: If the API call fails.
        """  # noqa: DOC502  # raised by _fetch_issue and PyGithub
        validate_issue_number(parent_number)

        repo = self._get_repository()
        if repo is None:
            logger.error("Failed to get repository")
            return None

        parent = _fetch_issue(self, repo, parent_number)
        return list(islice(parent.get_sub_issues(), max(0, max_results)))
