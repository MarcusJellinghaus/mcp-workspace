# Step 8 — Tri-state `rebase_needed`; rebase recommendation names the detected base

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_8.md`). Implement
> step 8 only: tests first, then make `rebase_needed` an `Optional[bool]` (None = UNKNOWN) in
> the report, recommendations and both renderers, and make `Rebase onto …` name the detected
> base branch. Run pylint, pytest (`-n auto`) and mypy until green, run `run_format_code`,
> then make one commit.

## WHERE

- `src/mcp_workspace/checks/branch_status.py`
- `src/mcp_workspace/checks/branch_status_rendering.py`
- `tests/checks/test_branch_status_base_branch.py` (new)
- `tests/checks/test_branch_status_recommendations.py`

## WHAT

```python
# BranchStatusReport
rebase_needed: Optional[bool]          # None = UNKNOWN (rebase check skipped)

def _apply_pr_merge_override(
    rebase_needed: Optional[bool], rebase_reason: str, pr_mergeable: Optional[bool]
) -> tuple[Optional[bool], str]: ...   # None passes through unchanged
```

`report_data` gains `"base_branch": base_branch_result` — the raw `Optional[str]` returned by
`detect_base_branch`, **not** the `"unknown"` placeholder that `collect_branch_status` passes
to `_collect_rebase_status`. `None` lets the `or default_branch_name` fallback fire, so the
recommendation never names `origin/unknown`.

## HOW

- `_apply_pr_merge_override`: logic unchanged (`if not rebase_needed: return …` already passes
  `None` through); update annotations + docstring.
- `_generate_recommendations`:
  - rebase recommendation fires only when `rebase_needed is True`;
  - `Rebase onto origin/{base}` with `base = report_data.get("base_branch") or default_branch_name`;
  - `Pull origin/{default_branch_name}` on the default branch is unchanged;
  - `Ready to merge` requires `rebase_needed is False` (UNKNOWN withholds it).
- Renderers (`branch_status_rendering.py`):
  - human: `None` → icon `❓`, text `UNKNOWN`; `True` → `⚠️ BEHIND`; `False` → `✅ UP TO DATE`.
  - LLM: `None` → `Rebase=UNKNOWN`; `True` → `BEHIND`; `False` → `UP_TO_DATE`.
- `create_empty_report` keeps `rebase_needed=False`.

## ALGORITHM (recommendation)

```
if rebase_needed is True and tasks_ok and ci_status != CIStatus.FAILED:
    if is_default_branch: append(f"Pull origin/{default_branch_name}")
    else: append(f"Rebase onto origin/{report_data.get('base_branch') or default_branch_name}")
...
ready = ci_ok and tasks_ok and not pr_blocks and not merge_state_blocked
        and rebase_needed is False and not linked_branch_blocking
```

## DATA

`rebase_needed ∈ {True, False, None}`.

## Tests (write first)

New file:
- `_generate_recommendations` with `rebase_needed=True`, `base_branch="epic/x"`,
  `default_branch_name="main"` → contains `Rebase onto origin/epic/x`, not `origin/main`.
- `collect_branch_status` with `detect_base_branch` → `None`, `needs_rebase` → `(True, …)`,
  `default_branch_name="main"` → recommendation `Rebase onto origin/main`, never
  `origin/unknown`.
- `rebase_needed=None` → no `Rebase onto …` / `Pull …`, no `Ready to merge`.
- `_apply_pr_merge_override(None, "r", True)` → `(None, "r")`.
- `format_report_for_llm` with `rebase_needed=None` → `Rebase=UNKNOWN`.
- `format_report_for_human` with `rebase_needed=None` → `Rebase Status: ❓ UNKNOWN`.

`test_branch_status_recommendations.py`: the two `Rebase onto origin/<default>` tests
(lines ~99, ~127) set `base_branch` in `report_data` and assert it is named
(e.g. `base_branch="main"` → `origin/main`; `base_branch="master"` → `origin/master`).
`Pull origin/…` tests unchanged.
