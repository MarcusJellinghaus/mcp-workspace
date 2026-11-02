"""Decide whether an issue body is trusted, reporting failed lookups as such.

A body is trusted when its author is trusted (role or allowlist) or when its
last editor is trusted (the token user, or an allowlisted login). Unlike
``base_branch_trust``, a failed lookup is reported as ``LOOKUP_FAILED`` rather
than folded into "untrusted", and rate limits raise ``GitHubRateLimitError``.
Nothing here is cached.
"""

import logging
from enum import Enum
from typing import Any, NamedTuple, Optional

from ..base_manager import BaseGitHubManager, _cached_login
from ..caching.errors import graphql_rate_limit_error, rate_limit_guard
from ..trust import is_trusted_author, normalize_author_association
from .base_branch_trust import _BODY_EDITOR_QUERY
from .types import IssueData

logger = logging.getLogger(__name__)

__all__ = ["BodyTrust", "BodyTrustResult", "check_body_trust"]

# Fixed, log-safe reasons; never derived from exception text.
_AUTHOR_TRUSTED = "author trusted"
_LAST_EDITOR_TRUSTED = "last editor trusted"
_UNTRUSTED = "author and last editor untrusted"
_REPOSITORY_NOT_DETECTED = "repository not detected"
_REPOSITORY_UNAVAILABLE = "repository unavailable"
_ISSUE_NUMBER_MISSING = "issue number missing"
_EDITOR_LOGIN_MISSING = "editor login missing"
_GRAPHQL_ERROR = "GraphQL error"
_ISSUE_NOT_FOUND = "issue not found"


class BodyTrust(str, Enum):
    """Outcome of an issue body trust check."""

    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"
    LOOKUP_FAILED = "lookup_failed"


class BodyTrustResult(NamedTuple):
    """Body trust outcome with a short, fixed reason."""

    status: BodyTrust
    reason: str


class _LookupFailed(Exception):
    """A GitHub lookup failed; carries a fixed, log-safe reason."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _editor_login(result: Any) -> Optional[str]:
    """Return the last body editor's login from a GraphQL response body.

    Args:
        result: Parsed body of the ``_BODY_EDITOR_QUERY`` response.

    Returns:
        The editor's login, with a "[bot]" suffix for bots, or None when the
        body was never edited (``editor`` present and null).

    Raises:
        GitHubRateLimitError: If the body reports a GraphQL rate limit.
        _LookupFailed: If the body has errors or lacks the issue or editor login.
    """
    if isinstance(result, dict) and "errors" in result:
        raise graphql_rate_limit_error(result) or _LookupFailed(_GRAPHQL_ERROR)
    node: Any = result
    for key in ("data", "repository", "issue"):
        if not isinstance(node, dict):
            raise _LookupFailed(_ISSUE_NOT_FOUND)
        node = node.get(key)
    if not isinstance(node, dict):
        raise _LookupFailed(_ISSUE_NOT_FOUND)
    if "editor" not in node:
        raise _LookupFailed(_EDITOR_LOGIN_MISSING)
    editor = node["editor"]
    if editor is None:
        return None
    login = editor.get("login") if isinstance(editor, dict) else None
    if not isinstance(login, str) or not login.strip():
        raise _LookupFailed(_EDITOR_LOGIN_MISSING)
    return f"{login}[bot]" if editor.get("__typename") == "Bot" else login


def check_body_trust(
    manager: BaseGitHubManager, issue: IssueData, allowlist: frozenset[str]
) -> BodyTrustResult:
    """Decide whether an issue body is trusted.

    Args:
        manager: Manager providing the repository and GitHub client.
        issue: Issue whose body is checked; missing ``user`` or
            ``author_association`` keys are treated as absent.
        allowlist: Lowercased allowlist of trusted logins.

    Returns:
        The trust outcome. Never ``TRUSTED`` after a failed lookup.

    Raises:
        GitHubRateLimitError: If a GitHub lookup hits a rate limit.
    """  # noqa: DOC502  # raised by rate_limit_guard
    login = issue.get("user")
    association = normalize_author_association(issue.get("author_association"))
    if is_trusted_author(login, association, allowlist):
        return BodyTrustResult(BodyTrust.TRUSTED, _AUTHOR_TRUSTED)

    try:
        _ = manager.repo_identifier
    except ValueError:
        return BodyTrustResult(BodyTrust.LOOKUP_FAILED, _REPOSITORY_NOT_DETECTED)

    with rate_limit_guard():
        repo = manager._get_repository()  # pylint: disable=protected-access
    if repo is None:
        return BodyTrustResult(BodyTrust.LOOKUP_FAILED, _REPOSITORY_UNAVAILABLE)

    number = issue["number"]
    if number == 0:
        return BodyTrustResult(BodyTrust.LOOKUP_FAILED, _ISSUE_NUMBER_MISSING)

    variables = {"owner": repo.owner.login, "repo": repo.name, "number": number}
    try:
        _, result = manager._github_client._Github__requester.graphql_query(  # type: ignore[attr-defined]  # pylint: disable=protected-access  # no public GraphQL API in PyGithub
            query=_BODY_EDITOR_QUERY, variables=variables
        )
        editor = _editor_login(result)
        if editor is None:
            return BodyTrustResult(BodyTrust.UNTRUSTED, _UNTRUSTED)
        if editor.lower() in allowlist:
            return BodyTrustResult(BodyTrust.TRUSTED, _LAST_EDITOR_TRUSTED)
        # pylint: disable=protected-access
        token_user = _cached_login(
            manager.github_token,
            manager.repo_identifier.api_base_url,
            manager._github_client,
        )
    except _LookupFailed as failed:
        logger.debug(
            "Body trust lookup failed for issue #%s: %s", number, failed.reason
        )
        return BodyTrustResult(BodyTrust.LOOKUP_FAILED, failed.reason)
    if editor.lower() == token_user.lower():
        return BodyTrustResult(BodyTrust.TRUSTED, _LAST_EDITOR_TRUSTED)
    return BodyTrustResult(BodyTrust.UNTRUSTED, _UNTRUSTED)
