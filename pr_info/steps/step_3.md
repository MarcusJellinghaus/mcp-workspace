# Step 3 — Wire rulesets into `verify_github`

## LLM prompt
> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_3.md`. Steps 1–2 are done.
> TDD: first update and add the tests, then refactor `verification.py`. The existing tests in
> `tests/github_operations/test_verification.py` pin today's row output; keep them green. Run
> pylint, pytest (`-n auto`) and mypy through the MCP tools; all must pass. Format with
> `run_format_code`, then make exactly one commit.

## WHERE
- `src/mcp_workspace/github_operations/verification.py`
- `tests/github_operations/test_verification.py`

## WHAT
```python
_PROTECTION_KEYS = ("branch_protection", "require_pull_request", "ci_checks_required",
                    "strict_mode", "force_push", "branch_deletion")

def _protection_result(outcome: ProtectionOutcome, rules_outcome: RulesOutcome | None) -> dict[str, CheckResult]: ...
def _rows_from_facts(facts: ProtectionFacts, source_label: str, *, reason: str | None, error: str) -> dict[str, CheckResult]: ...
```

## HOW
- Import `fetch_rules`, `merge`, `facts_from_classic`, `facts_from_rules`, `source_label` and
  `ProtectionFacts` by name, so tests can patch `verification.fetch_rules`.
- Inside the existing guard, right after `outcome = _fetch_protection(manager, repo)`: call
  `fetch_rules(manager, repo, outcome.branch)`, but only when `outcome.branch is not None`.
  Otherwise `rules_outcome = None`.
- Replace the old checks 5–9 `if/elif` block with:
  ```python
  if outcome is None:
      result.update(_protection_rows(None, "unknown", "repository not accessible"))
  else:
      result.update(_protection_result(outcome, rules_outcome))
  ```
- `_classify_protection_failure` stays and supplies the classic `(value, error)` when classic did
  not answer.
- Wording: change the docstrings and comments that say "five rows" / "checks 5–9" / "Check 10" /
  "Runs checks 1–4" to describe six branch-protection rows.
- `run_permission_probes(..., protection_outcome=outcome)` stays unchanged.

## ALGORITHM
`_protection_result`:
```
not_prot = is_branch_not_protected(outcome.exception)
classic, c_reason, c_note = (facts_from_classic(p), None, None) if outcome.protection is not None
    else (ProtectionFacts(), None, None) if not_prot
    else (None, *_classify_protection_failure(outcome.stage, outcome.exception)[1:])
rules, r_reason, r_note = (None, None, None) if rules_outcome is None
    else (facts_from_rules(rules_outcome.rules), None, None) if rules_outcome.rules is not None
    else (ProtectionFacts(), None, None) if not_prot and 404 GithubException
    else (None, f"not verifiable — {short_reason(exc)}", rules_outcome.note)
merged = merge(classic, rules); if merged.protected is False: return _protection_rows(False, "not configured", "no branch protection")
label = f"{outcome.branch} protected" + source_label(bool(classic and classic.protected), bool(rules and rules.protected), names)
return _rows_from_facts(merged, label, reason=c_reason or r_reason, error="; ".join(n for n in (c_note, r_note) if n))
```

`_rows_from_facts`: one helper `row(flag, yes, no)`:
- `flag is None` → `ok=None`, value `reason or "not verifiable"`;
- otherwise `ok=flag`, value `yes if flag else no`;
- `severity="warning"`, and the `error` key only when `error` is non-empty.

Rows, in `_PROTECTION_KEYS` order:

| Row | Flag | Value when `True` | Value when `False` |
|---|---|---|---|
| `branch_protection` | `protected` | `source_label` | `"not configured"` |
| `require_pull_request` | `require_pr` | `"required"` | `"not required"` |
| `ci_checks_required` | `checks_required` | `f"{len(contexts)} checks configured"` | `"not configured"` |
| `strict_mode` | `strict` | `"enabled"` | `"disabled"` |
| `force_push` | `force_push_blocked` | `"disabled"` | `"enabled"` |
| `branch_deletion` | `deletion_blocked` | `"disabled"` | `"enabled"` |

## DATA
- The result is a dict with all six keys, every row `severity="warning"`.
- Classic not answering with rules `[]` gives the same rows as today: value = classic reason,
  error = `"<stage> failed: ..."`.

## Tests (`test_verification.py`)
- New autouse fixture `_default_rules_empty`: patches `f"{MODULE}.fetch_rules"` to return
  `RulesOutcome([], None, None, None)`. Existing tests stay green and their `error` assertions don't
  see a rules note.
- `_make_mock_protection`: new parameter `require_pr: bool = True`, which sets
  `protection.required_pull_request_reviews = Mock() if require_pr else None`.
- Add `"require_pull_request"` to `BRANCH_CHECK_KEYS` (after `branch_protection`).
- Rename `test_all_five_checks_ok` → `test_all_protection_checks_ok` and
  `test_all_five_present_and_not_verifiable` → `test_all_protection_rows_present_and_not_verifiable`.
  Update the `TestProtectionOutcomeTable` docstring and the "(5–9)" section comment.
- Key order: the six protection keys appear in `_PROTECTION_KEYS` order in `result`.
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
