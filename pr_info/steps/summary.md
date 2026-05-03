# Implementation Summary — git: auto-split `--` into pathspec

## Issue
GitHub #187 — `git: auto-split '--' in args into pathspec for path-supporting commands`.

## Problem
The unified `git` MCP tool currently rejects any `--` token in `args`:

```
Flag '--' is not allowed in args. Use the 'pathspec' parameter instead.
```

Callers who paste a real CLI command (`git diff main...HEAD -- tests/`) hit this every time.

## Solution
Auto-split `args` on the first `--` for pathspec-supporting commands and route the tail into the existing `pathspec` parameter internally. Translation is silent. For commands that don't accept pathspecs, keep rejecting `--` (with clearer wording) so caller mistakes aren't silently swallowed.

## Architectural / Design Changes

### 1. New pure helper: `split_args_pathspec`
Lives in `arg_validation.py` (co-located with the per-command allowlist dicts and `_SUPPORTS_PATHSPEC`). No I/O, no state.

```python
def split_args_pathspec(
    command: str,
    args: list[str],
    pathspec: list[str] | None,
) -> tuple[list[str], list[str] | None]
```

### 2. `_SUPPORTS_PATHSPEC` moves to `arg_validation.py`
Currently lives in `read_operations.py` (used by the `git()` dispatcher's soft-warning logic). Move it next to the allowlist dicts so command-capability metadata is co-located. `read_operations.py` imports it from `arg_validation` — no re-export shim, just a regular import.

### 3. Reworded `validate_args` error
The `--` rejection message changes from:
```
"Flag '--' is not allowed in args. Use the 'pathspec' parameter instead."
```
to:
```
f"git {command} does not accept '--'"
```
After Step 2, `validate_args` only ever sees `--` for non-pathspec commands (the helper strips it for the rest), so the new wording is accurate.

### 4. Helper invoked per-handler, not just dispatcher
`git_log`, `git_diff`, `git_status`, `git_show`, and `_run_simple_command` each call `split_args_pathspec` before `validate_args` and before the `cmd_args += ["--"] + pathspec` injection. Per-handler placement ensures direct importers of these functions benefit, not only callers going through the `git()` dispatcher.

### 5. New error cases (helper)
| Case | Error |
|---|---|
| `--` in args **and** explicit `pathspec` parameter set | `"Specify paths via either '--' in args or the 'pathspec' parameter, not both."` |
| Multiple `--` tokens in args | `"Multiple '--' tokens in args are not allowed."` |
| Empty tail (`args=["--"]`) | No-op — drop the trailing `--`, leave `pathspec` unchanged |

## Scope (commands)

| Command | `--` behaviour after this change |
|---|---|
| `log`, `diff`, `show`, `status`, `ls_tree`, `ls_files` | Auto-split: tail routed into `pathspec` |
| `merge_base`, `fetch`, `rev_parse`, `ls_remote`, `branch` | Rejected with `"git <command> does not accept '--'"` |

## Files Modified

| File | Change |
|---|---|
| `src/mcp_workspace/git_operations/arg_validation.py` | Add `_SUPPORTS_PATHSPEC`; add `split_args_pathspec`; reword `validate_args` `--` error |
| `src/mcp_workspace/git_operations/read_operations.py` | Import `_SUPPORTS_PATHSPEC` from `arg_validation` (remove local def); call `split_args_pathspec` in 5 sites |
| `tests/git_operations/test_arg_validation.py` | Update `test_rejects_double_dash` (use `merge_base` + new wording); add `TestSplitArgsPathspec` class |
| `tests/git_operations/test_read_operations.py` | Add 2 handler-level tests (conflict + happy path) |

**No new files. No new directories. No new dependencies.**

## Step Breakdown

- **Step 1 — Foundation.** Move `_SUPPORTS_PATHSPEC`, add `split_args_pathspec` helper with full unit tests, reword `validate_args` error. Helper exists but is not yet wired into handlers. One commit.
- **Step 2 — Wiring.** Invoke helper in all 5 pathspec-injection sites. Add 2 handler-level integration tests for conflict and happy-path behaviour. One commit.

## Out of Scope
- No change to MCP tool docstrings or runtime hints — translation is silent by design.
- No new validation of pathspec contents (matches existing behaviour — passed straight to `repo.git.<cmd>`).
- No change to `git_branch` interaction (`branch` stays in the reject list, no read-flag interaction needed).
- No GitPython-specific escaping (it forwards `--` literally).
