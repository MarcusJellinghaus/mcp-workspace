# Step 4 — Report fields, `unstable` recommendation wording, `Non-green checks:` line

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_4.md` exactly.
> TDD: write the tests first, see them fail, then change the code. Run pylint, pytest
> (`extra_args: ["-n", "auto"]`) and mypy; all must pass. Run `run_format_code`, then make one commit.
> This step is pure (no GitHub calls). Nothing sets the new fields yet; step 5 does that.

## WHERE

- `src/mcp_workspace/checks/branch_status_rendering.py` — `format_check_names`, `_format_non_green_checks_line`, both format functions
- `src/mcp_workspace/checks/branch_status.py` — two report fields, `_merge_state_recommendation`, `_generate_recommendations`
- `tests/checks/test_branch_status_recommendations.py` — new recommendation tests
- New: `tests/checks/test_branch_status_non_green_checks.py` — rendering tests
- `.claude/skills/check_branch_status/SKILL.md` — three new rows

## WHAT

`branch_status_rendering.py`:

```python
MAX_CHECK_NAMES = 10

def format_check_names(names: Sequence[str]) -> str: ...
def _format_non_green_checks_line(report: "BranchStatusReport") -> Optional[str]: ...
```

`branch_status.py`:

```python
# BranchStatusReport, appended after base_branch_error:
non_green_checks: Optional[tuple[str, ...]] = None  # None = lookup not run; () = ran, none found
non_green_checks_error: Optional[str] = None

def _merge_state_recommendation(
    state: str, names: Optional[tuple[str, ...]], error: Optional[str]
) -> str: ...
```

## HOW

- `branch_status.py` imports `format_check_names` from `branch_status_rendering` (that import block
  already exists).
- In `_generate_recommendations`, replace the body of `if merge_state_blocked:` with
  `recommendations.append(_merge_state_recommendation(pr_mergeable_state, report_data.get("non_green_checks"), report_data.get("non_green_checks_error")))`.
  `merge_state_blocked`, `_BLOCKING_MERGE_STATES` and the `Ready to merge` gate stay as they are.
- Human format: inside the `pr_found` block, directly after `lines.append(f"Mergeable State: ...")`,
  append the `Non-green checks:` line when it is not `None`. If `pr_mergeable_state` is `None`,
  the line isn't rendered; the lookup only ever runs on `unstable`, so this case can't happen.
- LLM format: append the `Non-green checks:` line after the wait-line block and before
  `GitHub Label:`. Leave the `Branch Status:` summary line unchanged.

## ALGORITHM

```
format_check_names(names):
    shown = ", ".join(names[:MAX_CHECK_NAMES])
    extra = len(names) - MAX_CHECK_NAMES
    return f"{shown}, … and {extra} more" if extra > 0 else shown

_format_non_green_checks_line(report):
    if report.non_green_checks_error: return f"Non-green checks: lookup failed — {report.non_green_checks_error}"
    if report.non_green_checks: return f"Non-green checks: {format_check_names(report.non_green_checks)}"
    return None

_merge_state_recommendation(state, names, error):
    if state != "unstable" or (names is None and error is None):
        return f"Not ready to merge (GitHub mergeable_state: {state})"
    prefix = "CI passed but GitHub reports mergeable_state=unstable"
    if error: return f"{prefix} — could not list checks: {error}"
    if names: return f"Not ready to merge — non-green checks: {format_check_names(names)}"
    return f"{prefix} — likely stale, re-check"
```

## DATA

| `non_green_checks` | `non_green_checks_error` | Recommendation | Line |
|---|---|---|---|
| `None` | `None` | `Not ready to merge (GitHub mergeable_state: unstable)` (unchanged) | none |
| `("codecov/patch (pending)",)` | `None` | `Not ready to merge — non-green checks: codecov/patch (pending)` | `Non-green checks: codecov/patch (pending)` |
| `()` | `None` | `CI passed but GitHub reports mergeable_state=unstable — likely stale, re-check` | none |
| `()` | `"<reason>"` | `CI passed but GitHub reports mergeable_state=unstable — could not list checks: <reason>` | `Non-green checks: lookup failed — <reason>` |

## Tests (write first)

`test_branch_status_recommendations.py`, new class `TestUnstableLookupWording`, using hand-built
dicts like `test_unstable_blocks_ready_to_merge`. For CI=PASSED and CI=NOT_CONFIGURED:

1. Names → the names recommendation is present and `Ready to merge` is absent.
2. `()` → "likely stale, re-check" is present and `Ready to merge` is absent.
3. Error = `PERMISSION_ERROR_TEXT` (import from `pr_checks_mixin`), a rate-limit text, and
   `"GitHub API error 500: boom"` → each gives its own "could not list checks: …" text.
4. 12 names → the recommendation contains the first 10 and `… and 2 more`, and not the 11th.
5. `blocked`/`dirty` with fields set → old wording (`_merge_state_recommendation` ignores the fields).

Existing `test_unstable_blocks_ready_to_merge`, `test_unstable_emits_even_when_ci_failed` and
`test_issue_207_continue_on_error_scenario` must pass unchanged.

`tests/checks/test_branch_status_non_green_checks.py` (build reports like
`test_branch_status_pr_fields.py::_make_report`, with `pr_found=True`, `pr_mergeable_state="unstable"`):

1. Names → line present in both formats. Human: the line comes right after `Mergeable State: unstable`.
   LLM: the line comes before `GitHub Label:` and is not part of the `Branch Status:` line; with a
   `WaitContext(ci_elapsed=41, ci_timeout=60)` it comes after the `Wait:` line.
2. Error → `Non-green checks: lookup failed — <reason>` in both formats.
3. `None` and `()` → no `Non-green checks:` line in either format.
4. 12 names → 10 names and `… and 2 more`.
5. `format_check_names` with exactly 10 names → no "more" suffix.

## SKILL.md

Add these rows to the Follow-Up Actions table, after the `Ready to merge` row:

```
| `mergeable_state=unstable — likely stale, re-check` | Re-run `check_branch_status` |
| `Not ready to merge — non-green checks: …` | Wait for, or fix, the named checks |
| `mergeable_state=unstable — could not list checks: …` | Grant the token "Checks: read" / "Commit statuses: read", or wait for the rate-limit reset shown |
```
