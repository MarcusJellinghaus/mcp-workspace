# Step 3 — Retry `push_current_branch` (MCP `git_push` / `git_push_force` tools)

## LLM prompt

Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_3.md`).
Steps 1 and 2 are already in place. Implement Step 3 only, test first: add the
tests below to `tests/git_operations/test_push_retry.py`, then change the push
call in `push_current_branch`. Run pylint, pytest (`-n auto`) and mypy until
all pass, run the formatter, run the file-size gate below, and make exactly
one commit.

## WHERE

- `src/mcp_workspace/git_operations/remotes.py` — `push_current_branch` only
- `tests/git_operations/test_push_retry.py` — append tests

## WHAT / HOW

Replace

```python
force_args = ["--force-with-lease", "--force-if-includes"] if force else []
result = run_git_timed(project_dir, "push", "-u", *force_args, "origin", refspec)
```

with (fold `-u` into the flag list and use the short name `flags` so the
retried call stays on one line — 85 chars at its 4-space indent, under ruff's 88):

```python
flags = ["-u", "--force-with-lease", "--force-if-includes"] if force else ["-u"]
result = retry_500(run_git_timed, project_dir, "push", *flags, "origin", refspec)
```

- The git argv is unchanged (`push -u [--force-with-lease --force-if-includes] origin <refspec>`), so the existing argv tests in `test_push_current_branch.py` still pass unmodified.
- `run_git_timed` stays imported in `remotes.py` and is passed into `retry_500`; existing `patch("mcp_workspace.git_operations.remotes.run_git_timed")` tests keep working.
- Docstring: add one line, e.g. `A push that GitHub answers with HTTP 500 is retried (3 attempts).`
- The result mapping below the call stays unchanged; no new log line on final failure.
- Do not change the MCP tool docstrings or `toolset/_git_write_helpers.py`.

## ALGORITHM

None new — `retry_500` retries when the returned `GitOutput` has
`success=False` and a 500 line in `stderr`.

## DATA

Unchanged `GitResult`: `{"success", "error", "returncode", "stderr"}` taken
from the last attempt.

## Tests (append to `tests/git_operations/test_push_retry.py`)

Unit tests (no `git_integration` marker). Patch in
`mcp_workspace.git_operations.remotes`: `is_git_repository` → True,
`get_current_branch_name` → `"b"`, `run_git_timed` → `MagicMock(side_effect=[...])`;
for `force=True` additionally `safe_repo_context` (the fake context manager
from step 2) and `_force_push_precondition` → `None`. Patch
`_push_retry.time.sleep`. Build results as
`GitOutput(success=..., error=..., returncode=..., stderr=..., stdout="")`.

- normal: 500 result (`returncode=1`, stderr with ` ! [remote rejected] refs/heads/b -> b (Internal Server Error)`) then success → `success` True, `run_git_timed` called twice with `(project_dir, "push", "-u", "origin", "refs/heads/b:refs/heads/b")`.
- `force=True`: 500 (`returncode=128`, `The requested URL returned error: 500`) then success → success, both calls `(project_dir, "push", "-u", "--force-with-lease", "--force-if-includes", "origin", "refs/heads/b:refs/heads/b")`.
- 500 three times → `success` False, returned `stderr`/`returncode` are the third result's, 3 calls.
- timeout result (`success=False, returncode=None, stderr=None, error="git push timed out after 120 s"`) → exactly 1 call, returned as is.
- stale lease (`" ! [rejected] b -> b (stale info)"`) → exactly 1 call.

## File-size gate

Run `mcp__mcp-workspace__check_file_size(max_lines=750)` (pass the limit
explicitly). If `src/mcp_workspace/git_operations/remotes.py` is over 750
lines, write one line to `pr_info/.blocked.txt` and stop. Do not add it to
`.large-files-allowlist` and do not move unrelated functions out.
