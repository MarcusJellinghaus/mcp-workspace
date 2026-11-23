# Step 2 — Remove `check_path_not_gitignored` (gap 12)

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_2.md`.
> Check the precondition first. Run pylint, pytest (`-n auto`), mypy and vulture until all pass,
> run `run_format_code`, and make exactly one commit.

## Goal

Delete the dead gitignore-only checker. It ignores `.mcp-file-access`, so the new hint added in
step 3 would be wrong there.

## Precondition

- Search `src/` and `tests/` for `check_path_not_gitignored`.
- Search the mcp_coder reference project with `search_reference_files`; take its name from
  `get_reference_projects`.

If anything other than its own definition, `vulture_whitelist.py` or the docs refers to it,
write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/file_tools/directory_utils.py`
- `vulture_whitelist.py`
- `docs/ARCHITECTURE.md`, `docs/release-notes.md`

## WHAT / HOW

- **`directory_utils.py`:** delete the function `check_path_not_gitignored`. Keep `_excluded_error`
  for now; `file_access` still imports it, and step 3 moves it.
- **`vulture_whitelist.py`:** delete the `_.check_path_not_gitignored` entry and its two-line comment.
- **`docs/ARCHITECTURE.md`, Access Layer section:** the bullet becomes "`is_path_gitignored` and
  `list_files` stay gitignore-only in `directory_utils`, for `check_file_size` and library callers."
- **`docs/release-notes.md`:**
  - Add a bullet to the #404 section: Removed `file_tools.directory_utils.check_path_not_gitignored`
    (no callers; it ignored `.mcp-file-access`).
  - The #83 and #392 bullets that call it unchanged each get the pointer ` Changed in #404, see above.`

## ALGORITHM / DATA

None; this is a removal.

## Tests

There is no new test, since nothing calls the function. The full suite and `run_vulture_check` must
still pass.

## Commit

`refactor(directory_utils): remove unused check_path_not_gitignored (#404)`
