"""Private helpers for PR feedback sources (review threads, comments, alerts).

Extracted from `pr_manager.py` to keep that module under the file-size threshold.
These functions are implementation details of `PullRequestManager.get_pr_feedback()`
and should not be called from outside the `github_operations` package.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Optional, Tuple

from github.GithubException import GithubException

if TYPE_CHECKING:
    from .pr_manager import PullRequestManager

logger = logging.getLogger(__name__)

# reviewThreads GraphQL retry config — handles GitHub's eventual-consistency
# flake where querying a brand-new PR node raises GithubException 400/404.
# Note: a genuinely-missing PR (404) now costs ~3s (1s + 2s backoff) before
# falling through to [unavailable]; 404 is included defensively — only 400 was
# reproduced.
_REVIEW_DATA_MAX_ATTEMPTS = 3
_REVIEW_DATA_RETRY_BASE_DELAY_SECONDS = 1.0


def fetch_review_data(
    manager: "PullRequestManager", pr_number: int
) -> Tuple[list[dict[str, Any]], int, list[dict[str, Any]]]:
    """Fetch review threads + reviews via single GraphQL call.

    Returns:
        Tuple of (unresolved_threads, resolved_count, changes_requested_reviews)
    """
    repo = manager._get_repository()  # pylint: disable=protected-access
    if repo is None:
        return ([], 0, [])

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

    # Default overwritten on success; unused if every attempt raises (satisfies possibly-unbound).
    result: dict[str, Any] = {}
    for attempt in range(_REVIEW_DATA_MAX_ATTEMPTS):
        try:
            _, result = manager._github_client._Github__requester.graphql_query(  # type: ignore[attr-defined]  # pylint: disable=protected-access  # no public GraphQL API in PyGithub
                query=query, variables=variables
            )
            break
        except GithubException as e:
            # permanent error, or retries exhausted -> give up (caller renders unavailable)
            if e.status not in (400, 404) or attempt == _REVIEW_DATA_MAX_ATTEMPTS - 1:
                raise
            time.sleep(_REVIEW_DATA_RETRY_BASE_DELAY_SECONDS * 2**attempt)

    pr_data = result.get("data", {}).get("repository", {}).get("pullRequest")
    if pr_data is None:
        return ([], 0, [])

    unresolved_threads: list[dict[str, Any]] = []
    resolved_count = 0
    thread_nodes = pr_data.get("reviewThreads", {}).get("nodes", []) or []
    for thread in thread_nodes:
        if thread.get("isResolved"):
            resolved_count += 1
            continue
        comment_nodes = thread.get("comments", {}).get("nodes", []) or []
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
    review_nodes = pr_data.get("reviews", {}).get("nodes", []) or []
    for review in review_nodes:
        if review.get("state") != "CHANGES_REQUESTED":
            continue
        author = (review.get("author") or {}).get("login") or ""
        changes_requested.append({"author": author, "body": review.get("body") or ""})

    return (unresolved_threads, resolved_count, changes_requested)


def fetch_conversation_comments(
    manager: "PullRequestManager", pr_number: int
) -> list[dict[str, Any]]:
    """Fetch top-level PR conversation comments via REST."""
    repo = manager._get_repository()  # pylint: disable=protected-access
    if repo is None:
        return []

    issue = repo.get_issue(pr_number)
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
        _, _, data = manager._github_client._Github__requester.requestJsonAndCheck(  # type: ignore[attr-defined]  # pylint: disable=protected-access  # no public alerts API in PyGithub
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
