# Step 8 — Delete `get_staged_changes` / `get_unstaged_changes`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_8.md` exactly.
> Run format, pylint, pytest (`-n auto`), mypy, lint-imports and vulture; all must pass.
> Make one commit: `refactor(repository_status): remove the non -z status parsers (#355)`.

## Precondition

Search `src/` for `get_staged_changes` and `get_unstaged_changes`. The only matches must be
their own definitions in `repository_status.py` (steps 3, 5 and 6 removed the callers). If
any other match exists, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/git_operations/repository_status.py`
- `tests/git_operations/test_repository_status.py`

## WHAT

Delete `get_unstaged_changes(project_dir) -> dict[str, list[str]]` and
`get_staged_changes(project_dir) -> list[str]`. Neither is exported from
`git_operations.__init__`.

## HOW

- Delete both functions. Keep `is_git_repository` (used by `is_working_directory_clean` and
  other modules). Remove any import that becomes unused (pylint / ruff will say). Do not
  restructure the rest of the module.
- Tests: remove both names from the import and delete `test_get_staged_changes` and
  `test_get_unstaged_changes`. The step 3 parity tests cover the same behaviour through
  `get_full_status`.

## ALGORITHM

None (deletion).

## DATA

None.

## Verify

Search `src/` and `tests/` for `get_staged_changes|get_unstaged_changes`: no matches.
(`docs/release-notes.md` does not mention them.)
