# Step 1 — Pure facts module

## LLM prompt
> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_1.md`. TDD: write the tests
> first, then the implementation. Run pylint, pytest (`-n auto`) and mypy through the MCP tools;
> all must pass. Format with `run_format_code`, then make exactly one commit.

## WHERE
- new `src/mcp_workspace/github_operations/_ruleset_protection.py`
- new `tests/github_operations/test_ruleset_protection.py`

## WHAT
```python
@dataclass(frozen=True)
class ProtectionFacts:
    protected: bool | None = False
    checks_required: bool | None = False
    contexts: frozenset[str] = frozenset()
    strict: bool | None = False
    force_push_blocked: bool | None = False
    deletion_blocked: bool | None = False
    require_pr: bool | None = False

def facts_from_classic(protection: BranchProtection) -> ProtectionFacts: ...
def facts_from_rules(rules: list[dict[str, Any]]) -> ProtectionFacts: ...
def merge(classic: ProtectionFacts | None, rules: ProtectionFacts | None) -> ProtectionFacts: ...
def source_label(classic_protected: bool, rules_protected: bool, names: list[str] | None) -> str: ...
```

## HOW
- Module docstring: explain what the module does. Leave a `Token permissions:` paragraph that says
  "not yet verified"; step 4 fills it in.
- Imports: `dataclasses`, `typing.Any`, `github.BranchProtection.BranchProtection`. No imports from
  `verification.py` (that would be circular).
- Classic side: `required_status_checks` may be `None` at runtime even though PyGithub types it
  otherwise, so annotate it as `Any`, as `verification.py` does today.

## ALGORITHM
```
facts_from_classic(p): rsc = p.required_status_checks
  return Facts(True, rsc is not None, frozenset(rsc.contexts if rsc else []), bool(rsc and rsc.strict),
               not p.allow_force_pushes, not p.allow_deletions, p.required_pull_request_reviews is not None)
facts_from_rules(rules): types = {r.get("type") for r}; checks = [r for r if type == "required_status_checks"]
  contexts = {c["context"] for r in checks for c in (r.get("parameters") or {}).get("required_status_checks") or []}
  strict = any((r.get("parameters") or {}).get("strict_required_status_checks_policy") for r in checks)
  return Facts(bool(rules), bool(checks), frozenset(contexts), strict, "non_fast_forward" in types, "deletion" in types, "pull_request" in types)
merge(a, b): per flag f: vals = [getattr(s, f) if s else None for s in (a, b)]
  -> True if True in vals, else None if None in vals, else False; contexts = union of the non-None sources
```

`source_label`:
- `""` when `rules_protected` is false (classic-only keeps today's text).
- Otherwise ` (ruleset: "A", "B", "C", … + classic)`:
  - names are quoted and joined with `", "`; after 3 names, add `", …"`;
  - with no names, the plain word `ruleset`;
  - the ` + classic` suffix only when `classic_protected` is true.

## DATA
- `merge(None, None)` returns all flags `None` and empty `contexts`.
- Examples:
  - `source_label(True, True, ["Protect main"])` → ` (ruleset: "Protect main" + classic)`
  - `source_label(False, True, None)` → ` (ruleset)`

## Tests (`test_ruleset_protection.py`)
- `facts_from_classic`:
  - full protection;
  - `required_status_checks=None`;
  - `required_pull_request_reviews=None` → `require_pr=False`. Set it explicitly: a bare `Mock`
    attribute is truthy.
- `facts_from_rules`:
  - `[]` → `ProtectionFacts()`;
  - each rule type maps to its flag;
  - a `required_status_checks` rule with zero contexts gives `checks_required=True` with empty
    `contexts`;
  - strict policy;
  - contexts deduplicated across two rules;
  - a `pull_request` rule alone gives `protected=True`.
- `merge` table (parametrized):
  - ruleset-only;
  - classic-only;
  - both (contexts union, strict OR);
  - classic not-protected + ruleset;
  - classic `None` + no ruleset → all `None`;
  - classic `None` + ruleset → positives `True`, the rest `None`;
  - classic OK + rules `None` → positives `True`, classic negatives `None`;
  - a negative `require_pr` case (both answered, neither requires a PR → `False`).
- `source_label`: classic-only, both, rules-only, no names, 4 names truncated.
