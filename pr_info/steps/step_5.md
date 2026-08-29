# Step 5 — Say `Pull origin/main` when the current branch is the default branch

See [summary.md](./summary.md) for context. Independent of steps 1–4, but only
observable in practice once step 4 lets a stale `main` report `BEHIND`.

## WHERE

- **Modify:** `src/mcp_workspace/checks/branch_status.py`
  (functions `collect_branch_status` and `_generate_recommendations`)
- **Modify:** `tests/checks/test_branch_status_recommendations.py`

## WHAT

No signature changes:

```python
def _generate_recommendations(report_data: Dict[str, Any]) -> List[str]: ...
def collect_branch_status(project_dir: Path, max_log_lines: int = 300) -> BranchStatusReport: ...
```

One new `report_data` key, `is_default_branch: bool`, produced by
`collect_branch_status` and consumed by `_generate_recommendations`.

## HOW

- `_generate_recommendations` receives only CI / rebase / task / PR fields, so it
  cannot currently tell which branch it is describing. Plumb one boolean rather
  than the whole branch name — it is the only fact the wording depends on.
- Read it with `report_data.get("is_default_branch", False)` so every existing
  dict-literal call site in `tests/checks/test_branch_status_recommendations.py`
  stays valid without edits.
- Compute it explicitly from `get_default_branch_name(project_dir)`. The tempting
  shortcut is `branch_name == base_branch` (after step 2 those coincide on
  `main`), but that makes the wording depend on a coincidence of the detection
  result and would misfire on an issue with a mis-set `base_branch` field. Add
  `get_default_branch_name` to the existing
  `from mcp_workspace.git_operations.branch_queries import (...)` block — no new
  module dependency.
- Keep the literal `origin/main`, matching the already-hardcoded
  `Rebase onto origin/main` on the line being changed. Interpolating the real
  default branch name would be more correct on a `master` repository, but that is
  a separate change; the issue lists the hardcoded `origin/main` in the
  recommendation as a known out-of-scope defect.
- On `main` the action is a fast-forward, not a rebase — that is the whole point
  of the wording change.

## ALGORITHM

```
# collect_branch_status, step 11 (report_data assembly)
report_data["is_default_branch"] = (branch_name == get_default_branch_name(project_dir))

# _generate_recommendations
is_default_branch = report_data.get("is_default_branch", False)
if rebase_needed and tasks_ok and ci_status != CIStatus.FAILED:
    append("Pull origin/main" if is_default_branch else "Rebase onto origin/main")
```

## DATA

- `report_data` gains `"is_default_branch": bool`.
- `_generate_recommendations` still returns `List[str]`; only one element's text
  changes, and only on the default branch.
- `BranchStatusReport` is **not** changed — no new field, no rendering change.

## Reference implementation

In the import block:

```python
from mcp_workspace.git_operations.branch_queries import (
    extract_issue_number_from_branch,
    get_current_branch_name,
    get_default_branch_name,
)
```

In `collect_branch_status`, inside the `report_data` dict literal (step 11):

```python
            "pr_feedback_blocks_merge": pr_feedback_blocks_merge,
            "is_default_branch": branch_name == get_default_branch_name(project_dir),
        }
```

In `_generate_recommendations`, alongside the other `report_data.get(...)` reads:

```python
    is_default_branch = report_data.get("is_default_branch", False)
```

and:

```python
    if rebase_needed and tasks_ok and ci_status != CIStatus.FAILED:
        recommendations.append(
            "Pull origin/main" if is_default_branch else "Rebase onto origin/main"
        )
```

## TESTS (write first)

Add to `class TestGenerateRecommendations` in
`tests/checks/test_branch_status_recommendations.py`:

```python
    def test_rebase_needed_on_default_branch_says_pull(self) -> None:
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.PASSED,
                "rebase_needed": True,
                "tasks_status": TaskTrackerStatus.N_A,
                "tasks_reason": "No tasks",
                "tasks_is_blocking": False,
                "is_default_branch": True,
            }
        )
        assert "Pull origin/main" in recs
        assert "Rebase onto origin/main" not in recs
```

Notes:

- The existing `test_rebase_needed` passes no `is_default_branch` key and asserts
  `Rebase onto origin/main`, so it already covers the negative case — no second
  new test is needed.
- The new test fails before the change with `'Pull origin/main' not in recs`.

## Definition of done

- The new test passes; every existing test in
  `tests/checks/test_branch_status_recommendations.py` and
  `tests/checks/test_branch_status.py` passes unchanged.
- pylint, mypy, pytest (fast subset) all pass; run the `git_integration` subset too
  since `collect_branch_status` now calls `get_default_branch_name`.
- `./tools/format_all.sh` run, then exactly one commit.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_5.md`, then implement
> step 5 only.
>
> Use the MCP tools exclusively (`mcp__workspace__read_file`,
> `mcp__workspace__edit_file`, `mcp__tools-py__run_pylint_check`,
> `mcp__tools-py__run_pytest_check`, `mcp__tools-py__run_mypy_check`) as required
> by `.claude/CLAUDE.md`.
>
> Work test-first: add `test_rebase_needed_on_default_branch_says_pull` to
> `class TestGenerateRecommendations` in
> `tests/checks/test_branch_status_recommendations.py`, run the fast pytest subset
> and confirm it fails. Then in `src/mcp_workspace/checks/branch_status.py`: import
> `get_default_branch_name` from `git_operations.branch_queries`, add
> `"is_default_branch": branch_name == get_default_branch_name(project_dir)` to the
> `report_data` dict in `collect_branch_status`, and make
> `_generate_recommendations` emit `"Pull origin/main"` instead of
> `"Rebase onto origin/main"` when that key is true (read it with
> `.get("is_default_branch", False)`).
>
> Do not add a field to `BranchStatusReport` and do not change the rendering
> modules. Do not modify existing tests — they must all still pass.
>
> Then run pylint, mypy, the fast pytest subset and the `git_integration` pytest
> run. Fix anything that fails. Finally run `./tools/format_all.sh` and make one
> commit.
