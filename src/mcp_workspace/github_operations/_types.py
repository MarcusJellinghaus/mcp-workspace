"""Shared types for the verification module.

Extracted to break the circular import between ``verification.py`` and
``_permission_probes.py`` — both need ``CheckResult``, but ``verification.py``
also imports ``run_permission_probes`` from ``_permission_probes``.
"""

from typing import Any, Literal, NamedTuple, NotRequired, TypedDict

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


class RulesOutcome(NamedTuple):
    """Result of the effective-rules fetch in verify_github."""

    rules: list[dict[str, Any]] | None  # set on success
    names: list[str] | None  # ruleset names; None when the lookup failed or found none
    exception: Exception | None  # None on success
    note: str | None  # pre-formatted error text; None on success


def short_reason(exc: Exception) -> str:
    """Summarise ``exc`` without its raw response body.

    Args:
        exc: Exception to summarise.

    Returns:
        Short summary of the exception without the raw response body.
    """
    if isinstance(exc, GithubException):
        msg = exc.data.get("message") if isinstance(exc.data, dict) else None
        if isinstance(msg, str) and len(msg) <= 100:
            return f"HTTP {exc.status}: {msg}"
        return f"HTTP {exc.status}"
    return type(exc).__name__


def is_branch_not_protected(exc: Exception | None) -> bool:
    """Return True if ``exc`` is GitHub's 404 ``Branch not protected`` answer."""
    return (
        isinstance(exc, GithubException)
        and exc.status == 404
        and isinstance(exc.data, dict)
        and exc.data.get("message") == "Branch not protected"
    )
