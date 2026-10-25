# Step 3 — Classic-only refactor into `_rows_from_facts` + `require_pull_request` row

## LLM prompt
> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_3.md`. Steps 1–2 are done.
> TDD: first update and add the tests, then refactor `verification.py`. The existing tests in
> `tests/github_operations/test_verification.py` pin today's row output; keep them green. Run
> pylint, pytest (`-n auto`) and mypy through the MCP tools; all must pass. Format with
> `run_format_code`, then make exactly one commit.

## Scope
Classic protection only. No rules fetch yet; step 4 adds it. Behaviour stays the same apart from
the new `require_pull_request` row.

## WHERE
- `src/mcp_workspace/github_operations/verification.py`
- `tests/github_operations/test_verification.py`

## WHAT
```python
_PROTECTION_KEYS = ("branch_protection", "require_pull_request", "ci_checks_required",
                    "strict_mode", "force_push", "branch_deletion")

def _protection_result(outcome: ProtectionOutcome) -> dict[str, CheckResult]: ...
def _rows_from_facts(facts: ProtectionFacts, source_label: str, *, reason: str | None, error: str) -> dict[str, CheckResult]: ...
```

## HOW
- Import `merge`, `facts_from_classic` and `ProtectionFacts` from `_ruleset_protection`.
- Replace the old checks 5–9 `if/elif` block with:
  ```python
  if outcome is None:
      result.update(_protection_rows(None, "unknown", "repository not accessible"))
  else:
      result.update(_protection_result(outcome))
  ```
- `_classify_protection_failure` stays and supplies the classic `(value, error)` when classic did
  not answer.
- Wording: change the docstrings and comments that say "five rows" / "checks 5–9" / "Check 10" /
  "Runs checks 1–4" so they describe six branch-protection rows.
- `run_permission_probes(..., protection_outcome=outcome)` stays unchanged.

## ALGORITHM
`_protection_result` (classic only; the rules side is a fixed answered-empty `ProtectionFacts()`
until step 4):
```
not_prot = is_branch_not_protected(outcome.exception)
classic, c_reason, c_note = (facts_from_classic(p), None, None) if outcome.protection is not None
    else (ProtectionFacts(), None, None) if not_prot
    else (None, *_classify_protection_failure(outcome.stage, outcome.exception)[1:])
merged = merge(classic, ProtectionFacts())
if merged.protected is False: return _protection_rows(False, "not configured", "no branch protection")
return _rows_from_facts(merged, f"{outcome.branch} protected", reason=c_reason, error=c_note or "")
```
Merging with an answered-empty rules side reproduces today's output exactly: classic OK keeps its
own values, "Branch not protected" gives "not configured", and a classic failure gives `ok=None`
rows with the classic reason and error.

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
- A classic failure gives the same rows as today: value = classic reason, error =
  `"<stage> failed: ..."`.

## Tests (`test_verification.py`)
- `_make_mock_protection`: new parameter `require_pr: bool = True`, which sets
  `protection.required_pull_request_reviews = Mock() if require_pr else None`.
- Add `"require_pull_request"` to `BRANCH_CHECK_KEYS`, after `branch_protection`.
- Rename `test_all_five_checks_ok` → `test_all_protection_checks_ok` and
  `test_all_five_present_and_not_verifiable` → `test_all_protection_rows_present_and_not_verifiable`.
  Update the `TestProtectionOutcomeTable` docstring and the "(5–9)" section comment.
- Key order: the six protection keys appear in `_PROTECTION_KEYS` order in `result`.
- `require_pull_request`: classic with `require_pr=True` → `ok=True`, `required`; with
  `require_pr=False` → `ok=False`, `not required`.
- `TestProtectionOutcomeTable` and every other existing protection test stay green with unchanged
  assertions (apart from the key additions and renames above).
