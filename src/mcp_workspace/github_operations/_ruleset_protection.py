"""Branch protection facts from classic protection and repository rulesets.

`verify_github()` reads branch protection from two sources: the classic API
(`GET /repos/{o}/{r}/branches/{b}/protection`) and the effective-rules
endpoint (`GET /repos/{o}/{r}/rules/branches/{b}`). Each source is reduced to
a `ProtectionFacts`, or `None` when that source did not answer. `merge`
combines them: a positive from either source stands, and a negative needs
both sources to have answered; otherwise the flag is `None` (not verifiable).

Token permissions: not yet verified whether a read-only fine-grained token
can read `GET /repos/{o}/{r}/rules/branches/{b}` and
`GET /repos/{o}/{r}/rulesets`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, fields
from typing import Any
from urllib.parse import quote

from github.BranchProtection import BranchProtection
from github.Repository import Repository

from mcp_workspace.github_operations._types import RulesOutcome, short_reason
from mcp_workspace.github_operations.base_manager import BaseGitHubManager

logger = logging.getLogger(__name__)

_MAX_LABEL_NAMES = 3
_PAGE = {"per_page": 100}


@dataclass(frozen=True)
class ProtectionFacts:
    """Protection flags for one source, or the merge of both.

    Every flag defaults to `False`, so `ProtectionFacts()` is an answered
    "no protection". `None` on a flag means "not verifiable" (merge only).
    """

    protected: bool | None = False
    checks_required: bool | None = False
    contexts: frozenset[str] = frozenset()
    strict: bool | None = False
    force_push_blocked: bool | None = False
    deletion_blocked: bool | None = False
    require_pr: bool | None = False


def facts_from_classic(protection: BranchProtection) -> ProtectionFacts:
    """Build facts from a classic branch protection object.

    Args:
        protection: Classic branch protection returned by PyGithub.

    Returns:
        ``ProtectionFacts`` with ``protected=True`` and flags taken from
        ``protection``.
    """
    # PyGithub types this as non-optional, but it is None at runtime
    # when the GitHub API sends null
    status_checks: Any = protection.required_status_checks
    return ProtectionFacts(
        protected=True,
        checks_required=status_checks is not None,
        contexts=frozenset(status_checks.contexts if status_checks else []),
        strict=bool(status_checks and status_checks.strict),
        force_push_blocked=not protection.allow_force_pushes,
        deletion_blocked=not protection.allow_deletions,
        require_pr=protection.required_pull_request_reviews is not None,
    )


def facts_from_rules(rules: list[dict[str, Any]]) -> ProtectionFacts:
    """Build facts from the effective rules that apply to a branch.

    Args:
        rules: Effective rules from ``GET /repos/{o}/{r}/rules/branches/{b}``.

    Returns:
        ``ProtectionFacts`` built from ``rules``; ``protected`` is set only
        when at least one rule applies.
    """
    types = {rule.get("type") for rule in rules}
    checks = [rule for rule in rules if rule.get("type") == "required_status_checks"]
    contexts = {
        check["context"]
        for rule in checks
        for check in (rule.get("parameters") or {}).get("required_status_checks") or []
    }
    strict = any(
        (rule.get("parameters") or {}).get("strict_required_status_checks_policy")
        for rule in checks
    )
    return ProtectionFacts(
        protected=bool(rules),
        checks_required=bool(checks),
        contexts=frozenset(contexts),
        strict=strict,
        force_push_blocked="non_fast_forward" in types,
        deletion_blocked="deletion" in types,
        require_pr="pull_request" in types,
    )


def merge(
    classic: ProtectionFacts | None, rules: ProtectionFacts | None
) -> ProtectionFacts:
    """Merge both sources; `None` means that source did not answer.

    Per flag: `True` if either source is `True`, `False` if both answered
    and neither is `True`, `None` otherwise. `contexts` is the union of the
    answered sources.

    Args:
        classic: Facts from classic protection, or ``None`` if not answered.
        rules: Facts from the effective rules, or ``None`` if not answered.

    Returns:
        The merged ``ProtectionFacts``.
    """
    sources = (classic, rules)
    flags: dict[str, bool | None] = {}
    for field in fields(ProtectionFacts):
        if field.name == "contexts":
            continue
        values = [getattr(s, field.name) if s else None for s in sources]
        if True in values:
            flags[field.name] = True
        elif None in values:
            flags[field.name] = None
        else:
            flags[field.name] = False
    contexts = frozenset().union(*(s.contexts for s in sources if s))
    return ProtectionFacts(contexts=contexts, **flags)


def source_label(
    classic_protected: bool, rules_protected: bool, names: list[str] | None
) -> str:
    """Suffix for the `branch_protection` row naming the source(s).

    Empty when only classic protection applies, so today's text is kept.

    Args:
        classic_protected: Whether classic protection applies.
        rules_protected: Whether at least one ruleset rule applies.
        names: Names of the applying rulesets, or ``None`` if unknown.

    Returns:
        The label suffix, e.g. ``' (ruleset: "a" + classic)'``, or ``""`` when
        no ruleset applies.
    """
    if not rules_protected:
        return ""
    label = "ruleset"
    if names:
        shown = ", ".join(f'"{name}"' for name in names[:_MAX_LABEL_NAMES])
        if len(names) > _MAX_LABEL_NAMES:
            shown += ", …"
        label += f": {shown}"
    if classic_protected:
        label += " + classic"
    return f" ({label})"


def fetch_rules(
    manager: BaseGitHubManager, repo: Repository, branch: str
) -> RulesOutcome:
    """Fetch the effective rules for ``branch`` and the names of their rulesets.

    Args:
        manager: Manager whose GitHub client sends the raw requests.
        repo: Repository the branch belongs to.
        branch: Branch name; URL-quoted before use.

    Returns:
        ``RulesOutcome`` with the rules and best-effort ruleset names, or the
        exception and a pre-formatted note when the rules call failed.
    """
    try:
        requester = manager._github_client._Github__requester  # type: ignore[attr-defined]  # pylint: disable=protected-access  # no public rulesets API in PyGithub
        base = f"/repos/{repo.owner.login}/{repo.name}"
        _, data = requester.requestJsonAndCheck(
            "GET",
            f"{base}/rules/branches/{quote(branch, safe='')}",
            parameters=dict(_PAGE),
        )
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        logger.debug("rules fetch failed branch=%s exc=%s", branch, exc)
        return RulesOutcome(
            None, None, exc, f"rulesets not verifiable: {short_reason(exc)}"
        )
    rules: list[dict[str, Any]] = list(data or [])
    names = (
        _ruleset_names(
            requester, base, {r["ruleset_id"] for r in rules if "ruleset_id" in r}
        )
        if rules
        else None
    )
    return RulesOutcome(rules, names, None, None)


def _ruleset_names(requester: Any, base: str, ids: set[int]) -> list[str] | None:
    """Return the names of the rulesets in ``ids``, in API order.

    Best effort: any failure, or no match, returns ``None``.
    """
    try:
        _, data = requester.requestJsonAndCheck(
            "GET", f"{base}/rulesets", parameters=dict(_PAGE)
        )
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        logger.debug("rulesets lookup failed exc=%s", exc)
        return None
    names = [rs["name"] for rs in data or [] if rs.get("id") in ids]
    return names or None
