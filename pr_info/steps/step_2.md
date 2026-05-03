# Step 2 — Wire `split_args_pathspec` into all 5 pathspec-injection sites

> See `pr_info/steps/summary.md` for the full design rationale.
> **Depends on Step 1** (the helper must already exist).

## Goal
Apply the helper from Step 1 inside every handler that injects pathspec. After this step, callers can pass `--` inside `args` for pathspec-supporting commands and have it transparently rerouted into `pathspec`.

## WHERE
- `src/mcp_workspace/git_operations/read_operations.py` — five sites:
  1. `_run_simple_command` (~line 22) — used by `ls_tree`, `ls_files` (and `fetch`/`rev_parse`/`ls_remote` where the helper is a safe no-op).
  2. `git_log` (~line 65)
  3. `git_diff` (~line 108)
  4. `git_status` (~line 183)
  5. `git_show` (~line 235)
- `tests/git_operations/test_read_operations.py` — add `TestPathspecAutoSplit` class.

## WHAT

### Import update
```python
from .arg_validation import (
    split_args_pathspec,
    validate_args,
    validate_branch_has_read_flag,
)
```

### Per-handler one-liner
At each of the 5 sites, add **one line** immediately before `validate_args(...)`:
```python
safe_args, pathspec = split_args_pathspec(command, safe_args, pathspec)
```
Use the local variable name already in scope:
- `_run_simple_command`: variable is `args`, so `args, pathspec = split_args_pathspec(command, args, pathspec)`.
- `git_log`, `git_status`: variable is `safe_args`.
- `git_diff`, `git_show`: variable is `user_args`.
- For `git_log`/`git_status`/`git_diff`/`git_show` the `command` argument to the helper is the literal string (`"log"`, `"status"`, `"diff"`, `"show"`).

## HOW
- The call must be **before** `validate_args` so the head is what gets allowlist-checked.
- The call must be **before** `cmd_args += ["--"] + pathspec` injection so git never sees two `--` separators.
- Per-handler placement (not dispatcher-only): direct importers of `git_log`/`git_diff`/etc. also benefit.
- For `_run_simple_command`, the `command` parameter is already in scope; the helper is a no-op for `fetch`/`rev_parse`/`ls_remote` because they're not in `_SUPPORTS_PATHSPEC`.
- No signature changes anywhere.

## ALGORITHM
Per handler, the order becomes:
```
safe_args = args or []
safe_args, pathspec = split_args_pathspec("<cmd>", safe_args, pathspec)   # NEW
validate_args("<cmd>", safe_args)
cmd_args = [safety flags] + safe_args
if pathspec:
    cmd_args += ["--"] + pathspec
output = repo.git.<cmd>(*cmd_args)
```

## DATA
No signature changes. No return-type changes. Behaviour change:
- `--` in `args` for pathspec commands is now silently routed into `pathspec`.
- `--` + explicit `pathspec` parameter → `ValueError`.
- Multiple `--` in `args` → `ValueError`.
- `args=["--"]` (empty tail) → no-op.

## Tests (TDD: write FIRST, before wiring)

Add to `tests/git_operations/test_read_operations.py`:
```python
@pytest.mark.git_integration
class TestPathspecAutoSplit:
    """Auto-split '--' from args into pathspec for pathspec commands."""

    def test_diff_double_dash_in_args_equivalent_to_pathspec(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        repo, project_dir = git_repo_with_commit
        (project_dir / "a.txt").write_text("changed")
        repo.index.add(["a.txt"])
        repo.index.commit("change a")

        via_dashes = git_diff(project_dir, args=["HEAD~1", "HEAD", "--", "a.txt"])
        via_pathspec = git_diff(project_dir, args=["HEAD~1", "HEAD"], pathspec=["a.txt"])
        assert via_dashes == via_pathspec

    def test_diff_rejects_double_dash_with_explicit_pathspec(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        _, project_dir = git_repo_with_commit
        with pytest.raises(ValueError, match="either '--' in args or the 'pathspec'"):
            git_diff(
                project_dir,
                args=["HEAD", "--", "a.txt"],
                pathspec=["b.txt"],
            )
```

(Two tests intentionally — one happy path, one conflict. The exhaustive helper-level coverage was added in Step 1, so we don't repeat per-handler permutations here.)

## Code-quality gate (mandatory after edits)
All three must pass:
```
mcp__mcp-tools-py__run_pylint_check
mcp__mcp-tools-py__run_pytest_check  (extra_args=["-n", "auto", "-m",
    "not git_integration and not claude_cli_integration and not claude_api_integration "
    "and not formatter_integration and not github_integration and not langchain_integration"])
mcp__mcp-tools-py__run_mypy_check
```
Plus, run the new git_integration tests once to confirm:
```
mcp__mcp-tools-py__run_pytest_check  (extra_args=["-n", "auto", "-m", "git_integration"])
```

## LLM Prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`. Step 1 must already be merged.
>
> Implement Step 2: in `src/mcp_workspace/git_operations/read_operations.py`, add `split_args_pathspec` to the existing `from .arg_validation import ...` block, and add a single call to `split_args_pathspec(command, args, pathspec)` at the top of each of the five pathspec-injecting sites: `_run_simple_command`, `git_log`, `git_diff`, `git_status`, `git_show`. The call must be placed **before** the `validate_args(...)` call and **before** any `cmd_args += ["--"] + pathspec` injection.
>
> Follow TDD: first add the `TestPathspecAutoSplit` class to `tests/git_operations/test_read_operations.py` exactly as in the Tests section. Then wire the helper into the five handlers to make the tests pass.
>
> Use only MCP tools (`mcp__mcp-workspace__*` for files, `mcp__mcp-tools-py__run_*` for checks). Run pylint, fast pytest (with the no-integration marker filter), and mypy — all must pass. Then run pytest with the `git_integration` marker to verify the two new handler tests pass.
>
> This step must produce exactly one commit.

## Done when
- The two new tests in `TestPathspecAutoSplit` pass under the `git_integration` marker.
- Fast pytest, pylint, and mypy are all green.
- `split_args_pathspec` is called in all five handler sites.
- One commit produced.
