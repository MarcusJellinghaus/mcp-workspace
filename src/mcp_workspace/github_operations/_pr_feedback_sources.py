"""Private helpers for PR feedback sources (review threads, comments, alerts).

Extracted from `pr_manager.py` to keep that module under the file-size threshold.
These functions are implementation details of `PullRequestManager.get_pr_feedback()`
and should not be called from outside the `github_operations` package.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Optional, Tuple

from github.GithubException import GithubException, UnknownObjectException
from github.Requester import Requester

from ._diagnostics import extract_graphql_errors

if TYPE_CHECKING:
    from .pr_manager import PullRequestManager

logger = logging.getLogger(__name__)

# reviewThreads GraphQL retry config — handles GitHub's eventual-consistency
# flake where a brand-new PR node is not yet visible. GitHub answers HTTP 200
# with a null `pullRequest` for that case, so the retry keys on usability
# ("nothing usable came back and no error type is permanent"), not on a status
# code that PyGithub only synthesises. Genuine HTTP failures raise out of
# `requestJsonAndCheck` and are not retried here; `build_github_client`'s
# `GithubRetry` already covers 403/5xx.
_REVIEW_DATA_MAX_ATTEMPTS = 3
_REVIEW_DATA_RETRY_BASE_DELAY_SECONDS = 1.0
_PERMANENT_GRAPHQL_ERROR_TYPES = frozenset(
    {"FORBIDDEN", "INSUFFICIENT_SCOPES", "RATE_LIMITED"}
)


def _build_graphql_exception(
    requester: Requester, headers: dict[str, Any], result: dict[str, Any]
) -> Optional[GithubException]:
    """Return the exception PyGithub's `graphql_query` would have raised, or None.

    Keys on the raw `errors` list rather than on `extract_graphql_errors`
    output: the parser drops entries lacking a usable message, which would turn
    a multi-error body into a lone `NOT_FOUND` and flip the exception class that
    callers observe.

    Returns:
        `UnknownObjectException` for a single `NOT_FOUND` entry, the exception
        `Requester.createException` builds for status 400 otherwise, or None
        when the body carries no errors.
    """
    errors = result.get("errors")
    if not errors:
        return None
    if (
        isinstance(errors, list)
        and len(errors) == 1
        and isinstance(errors[0], dict)
        and errors[0].get("type") == "NOT_FOUND"
    ):
        return UnknownObjectException(404, result, headers, errors[0].get("message"))
    return requester.createException(400, headers, result)


def fetch_review_data(
    manager: "PullRequestManager", pr_number: int
) -> Tuple[list[dict[str, Any]], int, list[dict[str, Any]], Optional[GithubException]]:
    """Fetch review threads + reviews via a single tolerant GraphQL call.

    Calls `requestJsonAndCheck` directly rather than `graphql_query`, so `data`
    and `errors` arrive together and partial results survive instead of being
    discarded with the exception. Retries while nothing usable came back and no
    error type is permanent.

    Returns:
        Tuple of (unresolved_threads, resolved_count, changes_requested_reviews,
        error), where `error` is the `GithubException` `graphql_query` would
        have raised or None. Recovered data is returned alongside it.

    Raises:
        GithubException: Propagated from `requestJsonAndCheck` on a genuine HTTP
            failure. GraphQL-level errors are returned as the 4th tuple element,
            not raised, and are not retried by this loop.
    """  # noqa: DOC502  # GithubException propagates from requestJsonAndCheck
    repo = manager._get_repository()  # pylint: disable=protected-access
    if repo is None:
        return ([], 0, [], None)

    owner, repo_name = repo.owner.login, repo.name

    query = """
    query($owner: String!, $repo: String!, $prNumber: Int!) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $prNumber) {
          reviewThreads(first: 50) {
            nodes {
              isResolved
              comments(first: 5) {
                nodes { author { login } body path line diffSide diffHunk }
              }
            }
          }
          reviews(first: 50) {
            nodes { state author { login } body submittedAt }
          }
        }
      }
    }
    """

    variables = {"owner": owner, "repo": repo_name, "prNumber": pr_number}

    requester = manager._github_client._Github__requester  # type: ignore[attr-defined]  # pylint: disable=protected-access  # no public GraphQL API in PyGithub

    # Pre-initialised so they are never possibly-unbound after the loop.
    headers: dict[str, Any] = {}
    result: dict[str, Any] = {}
    pr_data: Optional[dict[str, Any]] = None
    for attempt in range(_REVIEW_DATA_MAX_ATTEMPTS):
        # Outside any try: a genuine HTTP failure must propagate unretried.
        headers, result = requester.requestJsonAndCheck(
            "POST",
            requester.graphql_url,
            input={"query": query, "variables": variables},
        )
        # `or {}` at every level: a partial response nulls exactly the field
        # that errored, and `.get(key, {})` would return None for it.
        pr_data = ((result.get("data") or {}).get("repository") or {}).get(
            "pullRequest"
        )
        if pr_data is not None:
            break
        if any(
            err_type in _PERMANENT_GRAPHQL_ERROR_TYPES
            for err_type, _ in extract_graphql_errors(result)
        ):
            break
        if attempt == _REVIEW_DATA_MAX_ATTEMPTS - 1:
            break
        time.sleep(_REVIEW_DATA_RETRY_BASE_DELAY_SECONDS * 2**attempt)

    error = _build_graphql_exception(requester, headers, result)
    if error is None and pr_data is None:
        # Status 200 is the truth here: GitHub answered successfully and simply
        # did not return the node. Fabricating a 400 would repeat the bug.
        error = GithubException(
            200, {"errors": [{"message": "pullRequest not returned"}]}, headers
        )
    if pr_data is None:
        return ([], 0, [], error)

    unresolved_threads: list[dict[str, Any]] = []
    resolved_count = 0
    thread_nodes = (pr_data.get("reviewThreads") or {}).get("nodes") or []
    for thread in thread_nodes:
        if thread.get("isResolved"):
            resolved_count += 1
            continue
        comment_nodes = (thread.get("comments") or {}).get("nodes") or []
        if not comment_nodes:
            continue
        first = comment_nodes[0]
        author = (first.get("author") or {}).get("login") or ""
        unresolved_threads.append(
            {
                "path": first.get("path") or "",
                "line": first.get("line"),
                "author": author,
                "body": first.get("body") or "",
                "diff_hunk": first.get("diffHunk") or "",
            }
        )

    changes_requested: list[dict[str, Any]] = []
    review_nodes = (pr_data.get("reviews") or {}).get("nodes") or []
    for review in review_nodes:
        if review.get("state") != "CHANGES_REQUESTED":
            continue
        author = (review.get("author") or {}).get("login") or ""
        changes_requested.append({"author": author, "body": review.get("body") or ""})

    # `error` is returned alongside recovered data, never instead of it: any
    # GraphQL error keeps `threads` flagged so a hidden blocking thread cannot
    # be reported as clean.
    return (unresolved_threads, resolved_count, changes_requested, error)


def fetch_conversation_comments(
    manager: "PullRequestManager", pr_number: int
) -> list[dict[str, Any]]:
    """Fetch top-level PR conversation comments via REST.

    Returns:
        List of dicts with ``author`` and ``body`` keys; empty list when the
        repository is unavailable.

    Raises:
        IssueIdentityMismatchError: If GitHub returns an issue from another
            repository (the issue was transferred) or with a different number.
    """  # noqa: DOC502  # IssueIdentityMismatchError comes from _get_issue_checked
    repo = manager._get_repository()  # pylint: disable=protected-access
    if repo is None:
        return []

    # pylint: disable-next=protected-access
    issue = manager._get_issue_checked(repo, pr_number)
    comments = issue.get_comments()
    return [
        {
            "author": c.user.login if c.user else "",
            "body": c.body or "",
        }
        for c in comments
    ]


def fetch_code_scanning_alerts(
    manager: "PullRequestManager", pr_number: int
) -> Optional[list[dict[str, Any]]]:
    """Fetch code-scanning alerts for the PR head ref via REST.

    Returns:
        None on 403 (silent skip — caller does not flag as unavailable).
        [] on success with no alerts or if repository is unavailable.
        list of alert dicts on success.

    Raises:
        GithubException: For non-403 errors (caller flags as unavailable).
    """
    repo = manager._get_repository()  # pylint: disable=protected-access
    if repo is None:
        return []

    owner, repo_name = repo.owner.login, repo.name

    try:
        _, data = manager._github_client._Github__requester.requestJsonAndCheck(  # type: ignore[attr-defined]  # pylint: disable=protected-access  # no public alerts API in PyGithub
            "GET",
            f"/repos/{owner}/{repo_name}/code-scanning/alerts",
            parameters={"ref": f"refs/pull/{pr_number}/head"},
        )
    except GithubException as e:
        if e.status == 403:
            logger.debug(
                "Code-scanning alerts unavailable (403): token lacks "
                "security_events:read or code-scanning is disabled"
            )
            return None
        raise

    alerts: list[dict[str, Any]] = []
    for alert in data or []:
        instance = alert.get("most_recent_instance") or {}
        location = instance.get("location") or {}
        message = (instance.get("message") or {}).get("text") or ""
        rule_description = (alert.get("rule") or {}).get("description") or ""
        alerts.append(
            {
                "rule_description": rule_description,
                "message": message,
                "path": location.get("path") or "",
                "line": location.get("start_line"),
            }
        )
    return alerts
