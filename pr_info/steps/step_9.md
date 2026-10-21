# Step 9 — Malformed Base Branch in `check_branch_status`

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_9.md`). Implement
> step 9 only: tests first, then surface a malformed Base Branch in `collect_branch_status`
> (no fallback base, rebase skipped), the recommendations and the Review Gate. Run pylint,
> pytest (`-n auto`) and mypy until green, run `run_format_code`, then make one commit.

## WHERE

- `src/mcp_workspace/checks/branch_status.py`
- `src/mcp_workspace/checks/branch_status_rendering.py` — `_review_gate_header`
- `tests/checks/test_branch_status_base_branch.py`
- `tests/checks/test_branch_status_review_gate.py`

## WHAT

```python
# BranchStatusReport (new field, defaulted)
base_branch_error: Optional[str] = None

def _malformed_first_line(body: str) -> str:
    """Return the first line of the malformed Base Branch section ('' if none)."""
```

`report_data` gains `"base_branch_error_issue": Optional[int]`.

## HOW

- Import `MalformedBaseBranchError`, `parse_base_branch` from
  `mcp_workspace.github_operations.issues` (already exported).
- In `collect_branch_status`, after the issue fetch:
  - `base_branch_error = issue_data.get("base_branch_error") if issue_data else None`
  - malformed → skip `detect_base_branch` and `_collect_rebase_status`;
    `base_branch = f"MALFORMED (issue #{n}: {_malformed_first_line(issue_data['body'])!r})"`;
    `rebase_needed, rebase_reason = None, f"base branch malformed in issue #{n}"`;
    `report_data["base_branch"] = None` (raw base unknown).
  - otherwise unchanged (step 8 behaviour).
  - `n = issue_data["number"]`.
- `_generate_recommendations`: when `base_branch_error_issue` is set, append
  `Fix the ### Base Branch section in issue #N` and withhold `Ready to merge`.
  (`Rebase onto …`/`Pull …` already do not fire for `rebase_needed=None`.)
- `_review_gate_header`: after the two UNKNOWN checks, before the linked-branch check:
  `if report.base_branch_error: return "Review Gate: BLOCKED (base branch)"`.
  Docstring: add `report.base_branch_error` to the "pure function of" list and state the order —
  base branch before linked branch, because without a base there is no rebase verdict.
- The human `Base Branch:` / LLM `Base:` lines already print `report.base_branch`; the rebase
  reason line prints `- base branch malformed in issue #N`. No other renderer change.

## ALGORITHM (`_malformed_first_line`)

```
try: parse_base_branch(body)
except MalformedBaseBranchError as exc: return exc.content.splitlines()[0]
return ""
```

## DATA

- `report.base_branch == "MALFORMED (issue #42: 'epic/x')"`
- `report.base_branch_error ==` helper sentence
- `report.rebase_needed is None`, `report.rebase_reason == "base branch malformed in issue #42"`

## Tests (write first)

`collect_branch_status` (mock like `tests/checks/test_branch_status.py`: patch
`IssueManager`, `PullRequestManager`, `get_current_branch_name` → `"42-feature"`,
`detect_base_branch`, `needs_rebase`, CI/linked-branch collectors), issue body
`"### Base Branch\n\nepic/x\nmore\n"` with `base_branch_error` set:
- `detect_base_branch` and `needs_rebase` not called.
- `base_branch == "MALFORMED (issue #42: 'epic/x')"`, `rebase_needed is None`,
  `base_branch_error` set.
- recommendations contain `Fix the ### Base Branch section in issue #42`; no
  `Ready to merge`, no `Rebase onto`, no `Pull`.
- LLM output: `Base: MALFORMED (issue #42: 'epic/x')`, `Rebase=UNKNOWN`,
  `Review Gate: BLOCKED (base branch)` with `fail_on_reviews=True`.
- Human output: `Base Branch: MALFORMED (…)`, `Rebase Status: ❓ UNKNOWN`,
  `- base branch malformed in issue #42`, same Review Gate line.
- Valid issue → `detect_base_branch` called with `issue_data=<fetched>` and no
  `issue_manager` kwarg.

`test_branch_status_review_gate.py`:
- `base_branch_error` + linked-branch `MISMATCH` → `BLOCKED (base branch)` (order).
- `base_branch_error` + `ci_status=UNKNOWN` → `UNKNOWN (undeterminable)`.
- `base_branch_error` + `ci_status=UNAVAILABLE` → `UNKNOWN (no token)`.
