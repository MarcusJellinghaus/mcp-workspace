"""Private helpers for PR feedback sources (review threads, comments, alerts).

Extracted from `pr_manager.py` to keep that module under the file-size threshold.
These functions are implementation details of `PullRequestManager.get_pr_feedback()`
and should not be called from outside the `github_operations` package.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional, Tuple

from github.GithubException import GithubException, UnknownObjectException
from github.Requester import Requester

if TYPE_CHECKING:
    from .pr_manager import PullRequestManager
    from .pr_types import ChangesRequestedData, ConversationCommentData

logger = logging.getLogger(__name__)

# reviewThreads GraphQL retry config — handles GitHub's eventual-consistency
# flake where a brand-new PR node is not yet visible. GitHub answers HTTP 200
# with a null `pullRequest` for that case, so the retry keys on usability
# ("nothing usable came back and no error is permanent"), not on a status
# code that PyGithub only synthesises. An error is permanent when its type is
# listed below, or when the response has `errors` and no `data` key — GraphQL
# rejected the query at validation. `"data": null` (a timeout) is still
# retried. Genuine HTTP failures raise out of
# `requestJsonAndCheck` and are not retried here; `build_github_client`'s
# `GithubRetry` already covers 403/5xx.
_REVIEW_DATA_MAX_ATTEMPTS = 3
_REVIEW_DATA_RETRY_BASE_DELAY_SECONDS = 1.0
_PERMANENT_GRAPHQL_ERROR_TYPES = frozenset(
    {"FORBIDDEN", "INSUFFICIENT_SCOPES", "RATE_LIMITED"}
)

# Follow-up reviewThreads pages run until hasNextPage is False or this cap is
# reached; hitting the cap while pages remain is reported as a fail-closed
# error rather than silently truncating the thread list.
_MAX_REVIEW_THREAD_PAGES = 10


def _has_permanent_error(result: dict[str, Any]) -> bool:
    """Return True when the response carries an error that retrying cannot fix.

    Two rules: the body has `errors` and no `data` key (GraphQL rejected the
    query at validation), or any `errors` entry names a permanently-failing
    type. A missing `data` key is the marker rather than a missing `type`,
    because the not-found flake has no `type` either but does return `data`.

    Reads the raw `errors` list rather than going through
    `extract_graphql_errors`: the parser is shaped for display, so the
    classifier stays independent of it.

    Returns:
        True if the retry loop should give up immediately.
    """
    errors = result.get("errors")
    if not isinstance(errors, list):
        return False
    if "data" not in result:
        return True
    return any(
        isinstance(entry, dict) and entry.get("type") in _PERMANENT_GRAPHQL_ERROR_TYPES
        for entry in errors
    )


def _build_graphql_exception(
    requester: Requester, headers: dict[str, Any], result: dict[str, Any]
) -> Optional[GithubException]:
    """Return the exception PyGithub's `graphql_query` would have raised, or None.

    Keys on the raw `errors` list rather than on `extract_graphql_errors`
    output: the parser drops entries carrying neither a usable `type` nor a
    usable `message`, which would turn a multi-error body into a lone
    `NOT_FOUND` and flip the exception class that callers observe.

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


def _request_review_page(
    requester: Requester, query: str, variables: dict[str, Any]
) -> Tuple[dict[str, Any], Optional[dict[str, Any]], Optional[GithubException]]:
    """Run one GraphQL request under the existing retry/permanent-error policy.

    Returns:
        (headers, pr_data, error) — pr_data is the repository.pullRequest
        payload, or None; error is what graphql_query would have raised, or
        None. Recovered pr_data is returned alongside error, never instead of it.
    """
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
        if _has_permanent_error(result):
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
    return headers, pr_data, error


def _parse_submitted_at(raw: Optional[str]) -> Optional[str]:
    """Normalize a GraphQL submittedAt value to isoformat, or None on absence/bad input.

    Returns:
        The isoformat string, or None if `raw` is None or unparseable.
    """
    if raw is None:
        return None
    try:
        return datetime.fromisoformat(raw).isoformat()
    except ValueError:
        logger.debug("unparseable submittedAt: %r", raw)
        return None


def _parse_changes_requested(pr_data: dict[str, Any]) -> list["ChangesRequestedData"]:
    """Build standing CHANGES_REQUESTED entries from latestOpinionatedReviews nodes.

    Returns:
        One entry per CHANGES_REQUESTED node, each with author/body/submitted_at.
    """
    result: list["ChangesRequestedData"] = []
    nodes = (pr_data.get("latestOpinionatedReviews") or {}).get("nodes") or []
    for node in nodes:
        if node is None or node.get("state") != "CHANGES_REQUESTED":
            continue
        result.append(
            {
                "author": (node.get("author") or {}).get("login") or "",
                "body": node.get("body") or "",
                "submitted_at": _parse_submitted_at(node.get("submittedAt")),
            }
        )
    return result


def _parse_thread_nodes(pr_data: dict[str, Any]) -> Tuple[list[dict[str, Any]], int]:
    """Parse one page's reviewThreads.nodes into (unresolved_threads, resolved_count).

    Returns:
        Tuple of (unresolved_threads, resolved_count) for this page only —
        callers accumulate across pages.
    """
    unresolved_threads: list[dict[str, Any]] = []
    resolved_count = 0
    thread_nodes = (pr_data.get("reviewThreads") or {}).get("nodes") or []
    for thread in thread_nodes:
        # `nodes` elements are nullable: a per-node error nulls that element
        # only, so skipping it keeps the sibling threads and the error reason
        # instead of raising AttributeError out of this function.
        if thread is None:
            continue
        if thread.get("isResolved"):
            resolved_count += 1
            continue
        comment_nodes = (thread.get("comments") or {}).get("nodes") or []
        first = next((c for c in comment_nodes if c is not None), None)
        if first is None:
            continue
        author = (first.get("author") or {}).get("login") or ""
        unresolved_threads.append(
            {
                "path": first.get("path") or "",
                "line": first.get("line"),
                "author": author,
                "body": first.get("body") or "",
                "diff_hunk": first.get("diffHunk") or "",
                "comment_id": first.get("databaseId"),
                "thread_id": thread.get("id"),
            }
        )
    return unresolved_threads, resolved_count


def fetch_review_data(
    manager: "PullRequestManager", pr_number: int
) -> Tuple[
    list[dict[str, Any]], int, list["ChangesRequestedData"], Optional[GithubException]
]:
    """Fetch paginated review threads + standing CHANGES_REQUESTED reviews via tolerant GraphQL calls.

    Calls `requestJsonAndCheck` directly rather than `graphql_query`, so `data`
    and `errors` arrive together and partial results survive instead of being
    discarded with the exception. Retries while nothing usable came back and no
    error is permanent; a response with errors and no `data` is not retried.

    One query template is reused for every page via `_request_review_page`.
    The first page passes `includeReviews: True, cursor: None`; follow-up
    pages (while `reviewThreads.pageInfo.hasNextPage` is true and the page
    count stays under `_MAX_REVIEW_THREAD_PAGES`) pass `includeReviews: False`
    and the previous page's `endCursor`, so reviews are parsed once from the
    first page only. Each page's threads are parsed via `_parse_thread_nodes`
    and accumulated.

    Returns:
        Tuple of (unresolved_threads, resolved_count, changes_requested_reviews,
        error), where `error` is the `GithubException` `graphql_query` would
        have raised, one synthesized for a truncated page cap, or None.
        `threads`/`resolved_count` reflect every page successfully parsed
        before `error` arose (if any); recovered data is returned alongside
        the error, never instead of it.

    Raises:
        GithubException: Propagated from the first page's `requestJsonAndCheck`
            call on a genuine HTTP failure. Errors on follow-up pages, and a
            page cap reached while pages remain, are returned as the 4th tuple
            element instead of raised.
        ValueError: If the repository is not accessible. `_get_repository`
            swallows the underlying failure, so there is no status to report —
            but returning an empty result would render an unreachable
            repository or an invalid token as "Reviews: clean", the same
            fail-open this function avoids for a null `pullRequest`.
    """  # noqa: DOC502  # GithubException propagates from requestJsonAndCheck
    repo = manager._get_repository()  # pylint: disable=protected-access
    if repo is None:
        raise ValueError("Repository not accessible")

    owner, repo_name = repo.owner.login, repo.name

    query = """
    query($owner: String!, $repo: String!, $prNumber: Int!, $cursor: String, $includeReviews: Boolean!) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $prNumber) {
          reviewThreads(first: 100, after: $cursor) {
            pageInfo { hasNextPage endCursor }
            nodes {
              id
              isResolved
              comments(first: 5) {
                nodes { author { login } body path line diffHunk databaseId }
              }
            }
          }
          latestOpinionatedReviews(first: 100) @include(if: $includeReviews) {
            nodes { state author { login } body submittedAt }
          }
        }
      }
    }
    """

    requester = manager._github_client._Github__requester  # type: ignore[attr-defined]  # pylint: disable=protected-access  # no public GraphQL API in PyGithub

    variables: dict[str, Any] = {
        "owner": owner,
        "repo": repo_name,
        "prNumber": pr_number,
        "cursor": None,
        "includeReviews": True,
    }
    headers, pr_data, error = _request_review_page(requester, query, variables)
    if pr_data is None:
        return ([], 0, [], error)

    changes_requested = _parse_changes_requested(pr_data)
    unresolved_threads, resolved_count = _parse_thread_nodes(pr_data)
    page_info = (pr_data.get("reviewThreads") or {}).get("pageInfo") or {}
    pages = 1

    try:
        while (
            error is None
            and page_info.get("hasNextPage")
            and pages < _MAX_REVIEW_THREAD_PAGES
        ):
            variables = {
                "owner": owner,
                "repo": repo_name,
                "prNumber": pr_number,
                "cursor": page_info.get("endCursor"),
                "includeReviews": False,
            }
            headers, pr_data, error = _request_review_page(requester, query, variables)
            if pr_data is None:
                break
            more_threads, more_resolved = _parse_thread_nodes(pr_data)
            unresolved_threads += more_threads
            resolved_count += more_resolved
            page_info = (pr_data.get("reviewThreads") or {}).get("pageInfo") or {}
            pages += 1
    except GithubException as e:
        error = e

    if (
        pages >= _MAX_REVIEW_THREAD_PAGES
        and page_info.get("hasNextPage")
        and error is None
    ):
        error = GithubException(
            200,
            {
                "errors": [
                    {
                        "message": (
                            f"reviewThreads truncated after "
                            f"{_MAX_REVIEW_THREAD_PAGES} pages"
                        )
                    }
                ]
            },
            headers,
        )

    # `error` is returned alongside recovered data, never instead of it: any
    # GraphQL error keeps `threads` flagged so a hidden blocking thread cannot
    # be reported as clean.
    return (unresolved_threads, resolved_count, changes_requested, error)


def fetch_conversation_comments(
    manager: "PullRequestManager", pr_number: int
) -> list["ConversationCommentData"]:
    """Fetch top-level PR conversation comments via REST.

    Returns:
        List of dicts with ``author``, ``body``, ``id`` and ``created_at``
        keys; empty list when the repository is unavailable.

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
            "id": c.id,
            "created_at": c.created_at.isoformat() if c.created_at else None,
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
