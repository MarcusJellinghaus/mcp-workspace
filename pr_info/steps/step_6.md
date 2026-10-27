# Step 6 — `stage_all_changes` drops its precheck

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_6.md` exactly.
> Tests first, then code. Run format, pylint, pytest (`-n auto`), mypy; all must pass.
> Make one commit: `fix(staging): stage_all_changes no longer fails open on status error (#355)`.

## WHERE

- `src/mcp_workspace/git_operations/staging.py` — import line 15, `stage_all_changes` (~line 198–258)
- `tests/git_operations/test_staging.py` — `TestStagingOperations`
- `docs/release-notes.md` — Compatibility section

## WHAT

`stage_all_changes(project_dir: Path) -> bool`: signature unchanged. A clean tree is still
`True` (`git add --all` is a no-op). Any git failure, including a status that can't be read
or a held `index.lock`, is `False`.

## HOW

- Import: `from .repository_status import is_git_repository` (drop `get_unstaged_changes`).
- Remove the `get_unstaged_changes` call, the file-list building and the early-return
  no-op. Keep the `is_git_repository` precheck and both existing `except` clauses unchanged.
- Docstring Note: replace "Returns True if no unstaged changes exist (no-op case)" with
  "Returns True on a clean tree (`git add --all` is a no-op)".

## ALGORITHM

```
if not is_git_repository(project_dir): return False
try:
    with safe_repo_context(project_dir) as repo:
        repo.git.add("--all")
    logger.debug("Staged all changes"); return True
except (InvalidGitRepositoryError, GitCommandError) as e: ... unchanged → False
except Exception as e: ... unchanged → False
```

## DATA

`bool`.

## Tests (write first)

In `TestStagingOperations` add `test_stage_all_changes_clean_tree_returns_true`: a
`git_repo_with_commit` with no changes → `stage_all_changes(project_dir) is True`, and
`repo.index.diff("HEAD") == []`. Existing `test_stage_all_changes` must still pass.

## Release notes

In `docs/release-notes.md` → `### Compatibility`, add:

```
- `stage_all_changes` no longer reports success when it cannot read the status; it runs
  `git add --all` directly, so any git failure is `False`.
```
