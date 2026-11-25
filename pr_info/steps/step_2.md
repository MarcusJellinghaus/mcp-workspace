# Step 2 — Retry the GitPython pushes: `git_push`, `push_branch`, `delete_branch`

## LLM prompt

Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_2.md`).
Step 1 (`_push_retry.retry_500`) is already in place. Implement Step 2 only,
test first: add the call-site tests below to `tests/git_operations/test_push_retry.py`,
then wrap the three GitPython push calls. Change nothing else in `remotes.py`
or `branches.py` beyond what is listed here. Run pylint, pytest (`-n auto`) and
mypy until all pass, run the formatter, and make exactly one commit.

## WHERE

- `src/mcp_workspace/git_operations/remotes.py` — `git_push`, `push_branch`, imports
- `src/mcp_workspace/git_operations/branches.py` — `delete_branch`, imports
- `tests/git_operations/test_push_retry.py` — append tests

## WHAT / HOW

`remotes.py`:
- Add `from ._push_retry import retry_500` (relative imports, sorted).
- `git_push`:
  - `repo.git.push("--force-with-lease", "origin", current_branch)` → `retry_500(repo.git.push, "--force-with-lease", "origin", current_branch)`
  - `repo.git.push("origin", current_branch)` → `retry_500(repo.git.push, "origin", current_branch)`
  - delete the comments `# Get current branch name` and `# Execute git push origin <current_branch>`.
  - docstring: add one line, e.g. `A push that GitHub answers with HTTP 500 is retried (3 attempts).`
- `push_branch`:
  - `repo.git.push("--set-upstream", "origin", branch_name)` → `retry_500(repo.git.push, "--set-upstream", "origin", branch_name)`
  - `repo.git.push("origin", branch_name)` → `retry_500(repo.git.push, "origin", branch_name)`
  - delete `# Push the branch`, `# Push with upstream tracking`, `# Push without upstream tracking`.
  - same one-line docstring mention.
- Every wrapped call must stay on one line after formatting. The existing
  `except` blocks, log calls and return values stay untouched.

`branches.py`:
- Add `from ._push_retry import retry_500`.
- `delete_branch`: `repo.git.push("origin", "--delete", branch_name)` →
  `retry_500(repo.git.push, "origin", "--delete", branch_name)`; one docstring
  line under `Note:` (e.g. `- A remote delete that GitHub answers with HTTP 500 is retried`).
  Still best-effort: the final `GitCommandError` lands in the existing DEBUG
  `except` and the function returns True.

## ALGORITHM

None new — each call site is `retry_500(repo.git.push, <same args>)`.

## DATA

Unchanged: `git_push` → `{"success": bool, "error": str | None}` with
`error = f"Git error during push: {e}"` from the last attempt's
`GitCommandError`; `push_branch` → `bool`; `delete_branch` → `bool`.

## Tests (append to `tests/git_operations/test_push_retry.py`)

All unit tests (no `git_integration` marker). Patch `_push_retry.time.sleep`.
Fake repo context as in `tests/git_operations/test_verification.py`:

```python
@contextmanager
def fake_safe_repo_context(_path: Path) -> Iterator[Mock]:
    yield repo
```

Patch in the module under test (`...git_operations.remotes` / `...git_operations.branches`):
`is_git_repository` (return True) and `safe_repo_context` (the fake).
`repo.git.push.side_effect = [<GitCommandError>, ...]`.

- `push_branch` additionally: patch `remotes.branch_exists` → True; origin
  remote: `origin = Mock(); origin.name = "origin"; repo.remotes = [origin]`
  (`Mock(name="origin")` does not set `.name`).
- `delete_branch` additionally: `repo.branches` = list of mocks with `.name`
  set (containing the branch), `repo.active_branch.name = "main"`, the same
  origin remote; `repo.git.branch` a plain Mock.

Cases:
- `git_push`: 500 then success → `{"success": True, "error": None}`, `repo.git.push` called twice with `("origin", "b")`.
- `git_push(force_with_lease=True)`: 500 then success → success; both calls `("--force-with-lease", "origin", "b")`.
- `git_push`: 500 three times → `success` False, 3 calls, `error` starts with `"Git error during push: "` and equals `f"Git error during push: {third_error}"`; one ERROR record (caplog).
- `git_push`: 500 then non-fast-forward → 2 calls; returned `error` matches mcp_coder's regex, copied into the test with a comment naming its source (`mcp_coder src/mcp_coder/workflow_steps/commit.py::_REJECTED_STATUS_LINE`):
  ```python
  _REJECTED_STATUS_LINE = re.compile(
      r"^[ \t]*! \[rejected\] .*\((?:fetch first|non-fast-forward)\)", re.MULTILINE
  )
  ```
  Build the non-fast-forward stderr like real git output starting with a `To <url>` line:
  `"To https://github.com/o/r.git\n ! [rejected]        b -> b (non-fast-forward)\nerror: failed to push some refs to 'https://github.com/o/r.git'"`.
- `git_push`: non-fast-forward first → exactly 1 call.
- `push_branch` (`set_upstream=True`): 500 then success → True, 2 calls with `("--set-upstream", "origin", "feature")`.
- `push_branch`: 500 three times → False, 3 calls.
- `delete_branch(..., delete_remote=True)`: 500 then success → True, push called twice with `("origin", "--delete", "feature")`.
- `delete_branch(..., delete_remote=True)`: 500 three times → still True, 3 calls.
