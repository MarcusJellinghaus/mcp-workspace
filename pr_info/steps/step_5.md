# Step 5 — `commit_staged_files` precheck uses `has_staged_changes`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_5.md` exactly.
> Tests first, then code. Run format, pylint, pytest (`-n auto`), mypy; all must pass.
> Make one commit: `refactor(commits): check staged changes via has_staged_changes (#355)`.

## WHERE

- `src/mcp_workspace/git_operations/commits.py` — import line 18, precheck (~line 93–105),
  outer `except` (~line 168), docstring Note (~line 59)
- `tests/git_operations/test_commits.py` — patches at ~207, ~249, ~282, plus one new test

## WHAT

`commit_staged_files(message: str, project_dir: Path) -> CommitResult`: signature unchanged.
New outcome: precheck raises `GitCommandError` → `success=False`,
`error_category="commit_failed"`.

## HOW

- Import: `from .repository_status import has_staged_changes, is_git_repository`.
- Precheck: `if not has_staged_changes(project_dir):` → the existing "No staged files to
  commit" / `validation_failed` return.
- Add one clause after the existing `except InvalidGitRepositoryError` on the outer `try`:
  `except GitCommandError as e:`. No new `try`. The inner `git commit` already catches its
  own `GitCommandError`, so only the precheck can reach this clause.
- Docstring Note: "Uses get_staged_changes() ..." → "Uses has_staged_changes() ...".

## ALGORITHM

```
try:
    if not has_staged_changes(project_dir): return <validation_failed, "No staged files to commit">
    ... unchanged commit block ...
except InvalidGitRepositoryError as e: ... unchanged ...
except GitCommandError as e:
    error_msg = f"Git error checking staged changes: {e}"; logger.error(error_msg)
    return {success False, commit_hash None, error error_msg, error_category "commit_failed",
            returncode e.status if isinstance(e.status, int) else None, stderr str(e.stderr or "")}
```

## DATA

`CommitResult`: `success`, `commit_hash`, `error`, `error_category`, `returncode`, `stderr`.

## Tests (write first)

- Patch target `"mcp_workspace.git_operations.commits.get_staged_changes"` →
  `"mcp_workspace.git_operations.commits.has_staged_changes"`:
  - `return_value=["some_file.py"]` → `return_value=True` (two tests)
  - `no_staged_files` case: `return_value=[]` → `return_value=False`
- New `test_staged_check_failure_is_commit_failed` (in the same class as
  `test_classifies_error_category`): patch `is_git_repository` → True and
  `has_staged_changes` with
  `side_effect=GitCommandError(["git", "diff", "--cached", "--quiet"], 128, stderr="fatal: boom")`.
  Assert `success is False`, `error_category == "commit_failed"`, `returncode == 128`,
  `"boom" in result["stderr"]`.
