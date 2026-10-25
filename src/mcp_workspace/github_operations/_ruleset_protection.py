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

from dataclasses import dataclass, fields
from typing import Any

from github.BranchProtection import BranchProtection

_MAX_LABEL_NAMES = 3


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
    """Build facts from a classic branch protection object."""
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
    """Build facts from the effective rules that apply to a branch."""
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
