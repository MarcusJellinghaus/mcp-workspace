"""Decide whether an issue body is trusted, reporting failed lookups as such.

A body is trusted when its author is trusted (role or allowlist) or when its
last editor is trusted (the token user, or an allowlisted login). Unlike
``base_branch_trust``, a failed lookup is reported as ``LOOKUP_FAILED`` rather
than folded into "untrusted", and rate limits raise ``GitHubRateLimitError``.
Nothing here is cached.
"""

from enum import Enum
from typing import NamedTuple

from ..base_manager import BaseGitHubManager
from ..caching.errors import rate_limit_guard
from ..trust import is_trusted_author, normalize_author_association
from .types import IssueData

__all__ = ["BodyTrust", "BodyTrustResult", "check_body_trust"]

# Fixed, log-safe reasons; never derived from exception text.
_AUTHOR_TRUSTED = "author trusted"
_REPOSITORY_NOT_DETECTED = "repository not detected"
_REPOSITORY_UNAVAILABLE = "repository unavailable"
_ISSUE_NUMBER_MISSING = "issue number missing"
_EDITOR_LOGIN_MISSING = "editor login missing"


class BodyTrust(str, Enum):
    """Outcome of an issue body trust check."""

    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"
    LOOKUP_FAILED = "lookup_failed"


class BodyTrustResult(NamedTuple):
    """Body trust outcome with a short, fixed reason."""

    status: BodyTrust
    reason: str


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

    if issue["number"] == 0:
        return BodyTrustResult(BodyTrust.LOOKUP_FAILED, _ISSUE_NUMBER_MISSING)

    # Editor lookup not implemented yet: fail closed.
    return BodyTrustResult(BodyTrust.LOOKUP_FAILED, _EDITOR_LOGIN_MISSING)
