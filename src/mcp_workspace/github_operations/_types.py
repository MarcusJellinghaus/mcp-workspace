"""Shared types for the verification module.

Extracted to break the circular import between ``verification.py`` and
``_permission_probes.py`` — both need ``CheckResult``, but ``verification.py``
also imports ``run_permission_probes`` from ``_permission_probes``.
"""

from typing import Literal, NamedTuple, NotRequired, TypedDict

from github.BranchProtection import BranchProtection
from github.GithubException import GithubException


class CheckResult(TypedDict):
    """Result of a single verification check.

    ``ok`` is ``True`` for a verified positive, ``False`` for a verified
    negative, and ``None`` when the check could not be verified.
    """

    ok: bool | None
    value: str
    severity: Literal["error", "warning"]
    error: NotRequired[str]
    install_hint: NotRequired[str]
    token_source: NotRequired[Literal["env", "config"]]
    token_fingerprint: NotRequired[str]


class ProtectionOutcome(NamedTuple):
    """Result of the single branch-protection fetch in verify_github."""

    branch: str | None  # None if get_default_branch failed
    stage: Literal["get_branch", "get_protection"]  # step that ran last
    protection: BranchProtection | None  # set on success
    exception: Exception | None  # None on success


def is_branch_not_protected(exc: Exception | None) -> bool:
    """Return True if ``exc`` is GitHub's 404 ``Branch not protected`` answer."""
    return (
        isinstance(exc, GithubException)
        and exc.status == 404
        and isinstance(exc.data, dict)
        and exc.data.get("message") == "Branch not protected"
    )
