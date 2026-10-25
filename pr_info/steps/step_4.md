# Step 4 — Wire rulesets into `verify_github`

## LLM prompt
> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_4.md`. Steps 1–3 are done.
> TDD: first add the tests, then extend `verification.py`. Keep the existing tests in
> `tests/github_operations/test_verification.py` green. Run pylint, pytest (`-n auto`) and mypy
> through the MCP tools; all must pass. Format with `run_format_code`, then make exactly one commit.

## WHERE
- `src/mcp_workspace/github_operations/verification.py`
- `tests/github_operations/test_verification.py`

## WHAT
```python
def _protection_result(outcome: ProtectionOutcome, rules_outcome: RulesOutcome | None) -> dict[str, CheckResult]: ...
```
`_rows_from_facts` is unchanged from step 3.

## HOW
- Add these imports by name: `fetch_rules`, `facts_from_rules` and `source_label` from
  `_ruleset_protection`, and `RulesOutcome` from `_types`. Tests patch `verification.fetch_rules`,
  so import it by name. `short_reason` (imported from `_types` since step 2) is used in the
  ALGORITHM below.
- Inside the existing guard, right after `outcome = _fetch_protection(manager, repo)`, call
  `fetch_rules(manager, repo, outcome.branch)`, but only when `outcome.branch is not None`.
  Otherwise `rules_outcome = None`. Declare `rules_outcome: RulesOutcome | None = None` beside
  `outcome`.
- The call site becomes `_protection_result(outcome, rules_outcome)`.

## ALGORITHM
`_protection_result` replaces step 3's fixed `ProtectionFacts()` rules side:
```
not_prot = is_branch_not_protected(outcome.exception)
classic, c_reason, c_note = ...  # unchanged from step 3
rules, r_reason, r_note = (None, None, None) if rules_outcome is None
    else (facts_from_rules(rules_outcome.rules), None, None) if rules_outcome.rules is not None
    else (ProtectionFacts(), None, None) if not_prot and 404 GithubException
    else (None, f"not verifiable — {short_reason(exc)}", rules_outcome.note)
merged = merge(classic, rules); if merged.protected is False: return _protection_rows(False, "not configured", "no branch protection")
names = rules_outcome.names if rules_outcome else None
label = f"{outcome.branch} protected" + source_label(bool(classic and classic.protected), bool(rules and rules.protected), names)
return _rows_from_facts(merged, label, reason=c_reason or r_reason, error="; ".join(n for n in (c_note, r_note) if n))
```

## DATA
Classic not answering with rules `[]` gives the same rows as today: value = classic reason,
error = `"<stage> failed: ..."`.

## Tests (`test_verification.py`)
- New autouse fixture `_default_rules_empty`: patches `f"{MODULE}.fetch_rules"` to return
  `RulesOutcome([], None, None, None)`. Existing tests stay green and their `error` assertions don't
  see a rules note.
- Table tests on `_protection_result`, built directly from `ProtectionOutcome` / `RulesOutcome`
  values with no HTTP:
  - ruleset-only (classic "Branch not protected" + rules) → parent `main protected (ruleset: "Protect main")`.
  - Both → `... + classic)`; contexts union counted.
  - Classic 403 + rules `[]` → every row `None`, value contains `token lacks Administration: Read`.
  - Classic 403 + ruleset → protected rows `True` with the `get_protection failed: ...` error; the
    other rows `None`.
  - Classic OK + rules 403 → positives `True`, `require_pull_request` with `require_pr=False` becomes
    `None`, the error contains `rulesets not verifiable: HTTP 403`.
  - Classic "Branch not protected" + rules 500 → all `None`, value contains `HTTP 500`, error is the
    rules note.
  - Classic "Branch not protected" + rules 404 (GHE) → all `False`, "not configured", error
    `no branch protection`.
  - Classic generic 404 + rules 404 → all `None`, error names both sources.
  - Classic OK + rules 404 → handled as an ordinary rules note.
  - Negative `require_pull_request`: both answered, no PR rule → `ok=False`, `not required`.
- `verify_github` level, with `fetch_rules` re-patched:
  - rules called with `outcome.branch`;
  - not called when `get_default_branch` raises;
  - called when `get_branch` fails;
  - not called on `skip`;
  - `perm_administration_read` stays failed for classic 403 even when the rules show protection.
