"""Tests for the pure ruleset/classic protection facts module."""

from typing import Any
from unittest.mock import Mock

import pytest

from mcp_workspace.github_operations._ruleset_protection import (
    ProtectionFacts,
    facts_from_classic,
    facts_from_rules,
    merge,
    source_label,
)


def _classic(
    *,
    status_checks: Any = "default",
    allow_force_pushes: bool = False,
    allow_deletions: bool = False,
    pr_reviews: Any = "default",
) -> Mock:
    protection = Mock()
    if status_checks == "default":
        status_checks = Mock(contexts=["ci", "lint"], strict=True)
    protection.required_status_checks = status_checks
    protection.allow_force_pushes = allow_force_pushes
    protection.allow_deletions = allow_deletions
    protection.required_pull_request_reviews = (
        Mock() if pr_reviews == "default" else pr_reviews
    )
    return protection


class TestFactsFromClassic:
    """Tests for facts_from_classic."""

    def test_full_protection(self) -> None:
        assert facts_from_classic(_classic()) == ProtectionFacts(
            protected=True,
            checks_required=True,
            contexts=frozenset({"ci", "lint"}),
            strict=True,
            force_push_blocked=True,
            deletion_blocked=True,
            require_pr=True,
        )

    def test_no_status_checks(self) -> None:
        facts = facts_from_classic(_classic(status_checks=None))
        assert facts.protected is True
        assert facts.checks_required is False
        assert facts.contexts == frozenset()
        assert facts.strict is False

    def test_pr_reviews_none_means_not_required(self) -> None:
        facts = facts_from_classic(_classic(pr_reviews=None))
        assert facts.require_pr is False

    def test_force_push_and_deletion_allowed(self) -> None:
        facts = facts_from_classic(
            _classic(allow_force_pushes=True, allow_deletions=True)
        )
        assert facts.force_push_blocked is False
        assert facts.deletion_blocked is False


def _checks_rule(contexts: list[str], strict: bool = False) -> dict[str, Any]:
    return {
        "type": "required_status_checks",
        "ruleset_id": 1,
        "parameters": {
            "required_status_checks": [{"context": c} for c in contexts],
            "strict_required_status_checks_policy": strict,
        },
    }


class TestFactsFromRules:
    """Tests for facts_from_rules."""

    def test_empty_rules(self) -> None:
        assert facts_from_rules([]) == ProtectionFacts()

    @pytest.mark.parametrize(
        "rule_type, field",
        [
            ("non_fast_forward", "force_push_blocked"),
            ("deletion", "deletion_blocked"),
            ("pull_request", "require_pr"),
            ("required_status_checks", "checks_required"),
        ],
    )
    def test_rule_type_maps_to_flag(self, rule_type: str, field: str) -> None:
        facts = facts_from_rules([{"type": rule_type}])
        assert facts.protected is True
        assert getattr(facts, field) is True
        others = {
            "checks_required",
            "force_push_blocked",
            "deletion_blocked",
            "require_pr",
        } - {field}
        for other in others:
            assert getattr(facts, other) is False

    def test_checks_rule_with_zero_contexts(self) -> None:
        facts = facts_from_rules([_checks_rule([])])
        assert facts.checks_required is True
        assert facts.contexts == frozenset()
        assert facts.strict is False

    def test_strict_policy(self) -> None:
        facts = facts_from_rules([_checks_rule(["ci"], strict=True)])
        assert facts.strict is True
        assert facts.contexts == frozenset({"ci"})

    def test_contexts_deduplicated_across_rules(self) -> None:
        facts = facts_from_rules(
            [_checks_rule(["ci", "lint"]), _checks_rule(["ci", "test"])]
        )
        assert facts.contexts == frozenset({"ci", "lint", "test"})

    def test_pull_request_rule_alone_is_protected(self) -> None:
        facts = facts_from_rules([{"type": "pull_request", "parameters": {}}])
        assert facts == ProtectionFacts(protected=True, require_pr=True)


_FULL = ProtectionFacts(
    protected=True,
    checks_required=True,
    contexts=frozenset({"ci"}),
    strict=False,
    force_push_blocked=True,
    deletion_blocked=False,
    require_pr=False,
)
_RULES = ProtectionFacts(
    protected=True,
    checks_required=True,
    contexts=frozenset({"lint"}),
    strict=True,
    force_push_blocked=False,
    deletion_blocked=True,
    require_pr=True,
)
_ALL_NONE = ProtectionFacts(
    protected=None,
    checks_required=None,
    contexts=frozenset(),
    strict=None,
    force_push_blocked=None,
    deletion_blocked=None,
    require_pr=None,
)


@pytest.mark.parametrize(
    "classic, rules, expected",
    [
        pytest.param(ProtectionFacts(), _RULES, _RULES, id="ruleset-only"),
        pytest.param(_FULL, ProtectionFacts(), _FULL, id="classic-only"),
        pytest.param(
            _FULL,
            _RULES,
            ProtectionFacts(
                protected=True,
                checks_required=True,
                contexts=frozenset({"ci", "lint"}),
                strict=True,
                force_push_blocked=True,
                deletion_blocked=True,
                require_pr=True,
            ),
            id="both",
        ),
        pytest.param(
            ProtectionFacts(),
            ProtectionFacts(protected=True, deletion_blocked=True),
            ProtectionFacts(protected=True, deletion_blocked=True),
            id="classic-not-protected-plus-ruleset",
        ),
        pytest.param(None, ProtectionFacts(), _ALL_NONE, id="classic-none-no-ruleset"),
        pytest.param(
            None,
            ProtectionFacts(protected=True, force_push_blocked=True),
            ProtectionFacts(
                protected=True,
                checks_required=None,
                contexts=frozenset(),
                strict=None,
                force_push_blocked=True,
                deletion_blocked=None,
                require_pr=None,
            ),
            id="classic-none-plus-ruleset",
        ),
        pytest.param(
            _FULL,
            None,
            ProtectionFacts(
                protected=True,
                checks_required=True,
                contexts=frozenset({"ci"}),
                strict=None,
                force_push_blocked=True,
                deletion_blocked=None,
                require_pr=None,
            ),
            id="classic-ok-rules-none",
        ),
        pytest.param(
            ProtectionFacts(protected=True),
            ProtectionFacts(protected=True, checks_required=True),
            ProtectionFacts(protected=True, checks_required=True, require_pr=False),
            id="negative-require-pr",
        ),
    ],
)
def test_merge(
    classic: ProtectionFacts | None,
    rules: ProtectionFacts | None,
    expected: ProtectionFacts,
) -> None:
    assert merge(classic, rules) == expected


def test_merge_both_none() -> None:
    assert merge(None, None) == _ALL_NONE


class TestSourceLabel:
    """Tests for source_label."""

    def test_classic_only(self) -> None:
        assert source_label(True, False, ["Protect main"]) == ""

    def test_both(self) -> None:
        assert (
            source_label(True, True, ["Protect main"])
            == ' (ruleset: "Protect main" + classic)'
        )

    def test_rules_only(self) -> None:
        assert source_label(False, True, ["A", "B"]) == ' (ruleset: "A", "B")'

    def test_no_names(self) -> None:
        assert source_label(False, True, None) == " (ruleset)"
        assert source_label(True, True, []) == " (ruleset + classic)"

    def test_four_names_truncated(self) -> None:
        assert (
            source_label(False, True, ["A", "B", "C", "D"])
            == ' (ruleset: "A", "B", "C", …)'
        )
