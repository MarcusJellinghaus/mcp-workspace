# Step 1 — `auto_delete_branches`: report "not accessible" when the field is unreadable

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_1.md` exactly.
> Follow TDD: write the test change first, then the code change. Use the exact strings given.
> Run pylint, pytest (`extra_args: ["-n", "auto"]`) and mypy; all must pass.
> Run `run_format_code`, then make one commit.

## Precondition

The `auto_delete_branches` block in `verify_github` (`src/mcp_workspace/github_operations/verification.py`)
starts with `if repo.delete_branch_on_merge:`. If it does not, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `tests/github_operations/test_verification.py`
- `src/mcp_workspace/github_operations/verification.py` — `verify_github()`, the
  "auto_delete_branches (repo-level setting)" block

## WHAT

No new functions. Signatures that change (tests only):

```python
def _patch_all_ok(..., delete_branch_on_merge: bool | None = True, ...) -> dict[str, object]
def _run_all_ok_with_branch(..., delete_branch_on_merge: bool | None = True, ...) -> tuple[dict[str, object], Mock]
```

New test in `class TestAutoDeleteBranches`:

```python
def test_not_accessible(self, tmp_path: Path) -> None
```

## Tests (write first)

1. Widen `delete_branch_on_merge` from `bool` to `bool | None` in `_patch_all_ok` and `_run_all_ok_with_branch`.
2. Add `test_not_accessible`, mirroring `test_disabled`:
   ```python
   result = _patch_all_ok(tmp_path, delete_branch_on_merge=None)
   check: CheckResult = result["auto_delete_branches"]  # type: ignore[assignment]
   assert check["ok"] is None
   assert check["value"] == "not accessible — token lacks Contents: Read and write"
   assert check["severity"] == "warning"
   assert check["error"] == "merge settings not returned by GitHub"
   ```
3. Keep `test_enabled` and `test_disabled` unchanged — they cover the truthy and `False` cases.

## HOW / ALGORITHM

Inside `if repo_is_ok and repo is not None:` replace the two-way branch with:

```python
delete_on_merge: bool | None = repo.delete_branch_on_merge
if delete_on_merge is None:
    result["auto_delete_branches"] = CheckResult(
        ok=None,
        value="not accessible — token lacks Contents: Read and write",
        severity="warning",
        error="merge settings not returned by GitHub",
    )
elif delete_on_merge:
    ...  # unchanged: ok=True, "auto-delete on merge"
else:
    ...  # unchanged: ok=False, "not enabled"
```

Rules:
- The local annotated `bool | None` is mandatory (a bare `repo.delete_branch_on_merge is None` is flagged unreachable by mypy).
- Keep `elif delete_on_merge:` a truthiness test, not `is True`.
- Do not use `repo.raw_data`.
- Strings inline, like every other `CheckResult` in `verify_github` — no new constants.
- The `else` branch for "repository not accessible" is unchanged.

## DATA

`result["auto_delete_branches"]` is a `CheckResult`:

| `delete_branch_on_merge` | `ok` | `value` | `error` |
|---|---|---|---|
| `None` | `None` | `not accessible — token lacks Contents: Read and write` | `merge settings not returned by GitHub` |
| truthy | `True` | `auto-delete on merge` | — |
| `False` | `False` | `not enabled` | — |

Severity is `warning` in all cases; `overall_ok` is unaffected.

## Commit message

```
fix(verification): report auto-delete as not accessible when unreadable
```
