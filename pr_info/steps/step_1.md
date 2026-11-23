# Step 1 — `.git` refusal uses `normalize_path`'s message (gap 5c)

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_1.md`.
> Write the tests first, then the code. Run pylint, pytest (`-n auto`) and mypy until all pass,
> run `run_format_code`, and make exactly one commit.

## Goal

`require_access` refuses a `.git` path with the same message `normalize_path` uses, with no
gitignore wording and no hint. One helper builds that message for both callers.

## WHERE

- `src/mcp_workspace/file_tools/path_utils.py`
- `src/mcp_workspace/file_tools/file_access.py`
- `tests/file_tools/test_file_access.py`, `tests/test_server.py`, `tests/test_file_access_tools.py`
- `docs/file-access.md`, `docs/release-notes.md`

## WHAT

```python
# path_utils.py
def git_dir_error(path: str) -> ValueError:
    """Build the refusal for a path that is a .git entry or below one."""
    # returns ValueError(f"Security error: Path '{path}' is inside a git directory, "
    #                    "which the file tools do not access.")

# file_access.py
_GIT_DIR = "git directory"   # reason _access returns for .git paths
```

## HOW

- `normalize_path`: replace its inline `ValueError(...)` for `.git` with `raise git_dir_error(path)`.
  The text stays identical.
- `file_access._access`: the `.git` branch returns `(FileAccess.HIDDEN, _GIT_DIR)` instead of
  `(FileAccess.HIDDEN, "")`. Update its Returns docstring to say it returns `git directory` for `.git`.
  The other callers read only `[0]` and are unaffected.
- `file_access.require_access`: import `git_dir_error` from `path_utils`.

## ALGORITHM (`require_access`, after converting an absolute path to relative)

```
access, reason = _access(file_path, project_dir, load_access_rules(project_dir))
if reason == _GIT_DIR:
    raise git_dir_error(file_path)
if access is HIDDEN:
    raise _excluded_error(file_path)      # unchanged in this step
if needed is READ_WRITE and access is READ_ONLY:
    raise ValueError(f"No write access to '{file_path}' ({reason})")
```

## DATA

`_access(".git/config", …)` → `(FileAccess.HIDDEN, "git directory")`.

## Tests (write first)

- **`tests/file_tools/test_file_access.py`:**
  - `require_access(".git/config", project, FileAccess.READ_ONLY)` raises with exactly
    `git_dir_error(".git/config")`'s message, and the message contains neither `.gitignore` nor
    `.mcp-file-access`. Also check `READ_WRITE`.
  - `_access(".git/config", project, load_access_rules(project))` returns
    `(FileAccess.HIDDEN, "git directory")`.
  - `str(normalize_path` error for `.git/config`) equals `str(git_dir_error(".git/config"))`.
- **`tests/test_server.py`:** `test_read_file_git_config` and `test_save_file_git_hooks` change their
  `match=` from `"excluded by .gitignore"` to `"inside a git directory"`.
- **`tests/test_file_access_tools.py`:** `test_git_dir_stays_hidden_under_read_write_rule` asserts
  `save_file(".git/config")` against `GITIGNORE_REFUSAL`; change it to match
  `"inside a git directory"`. With the two `tests/test_server.py` tests, this is the third of the
  about 3 sites.
- Update any other test that now fails because it expected the gitignore message on a `.git`
  path.

## Docs

- **`docs/file-access.md`, "Refusals" paragraph:** add that a `.git` path is refused with
  `Security error: Path '<path>' is inside a git directory, which the file tools do not access.`
  and never with the gitignore message.
- **`docs/release-notes.md`:**
  - Create the section `## Next minor release — .mcp-file-access surfaced to agents (#404)` above
    the existing first section.
  - Add the bullet: `.git` paths refused by `read_file`, the write tools and `read_reference_file`
    now give `Security error: Path '<p>' is inside a git directory, which the file tools do not
    access.` (was the gitignore message).

## Commit

`fix(file_access): refuse .git paths with the git-directory message (#404)`
