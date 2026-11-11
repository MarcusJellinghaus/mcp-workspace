# Step 3 — `list_directory` refuses ignored directories

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_3.md`). Steps 1–2 are
> done. Implement **only** this step, test first. Run pylint, pytest (`-n auto`) and mypy;
> all must pass. Format, then make exactly one commit.

## WHERE

- `src/mcp_workspace/toolset/read.py` — the `list_directory` closure in `register`
- `tests/test_server_list_directory.py`

## WHAT

No new functions. `list_directory(path=".", dirs_only=False) -> list[str]` gains one call:
`check_not_gitignored(ctx, path)` (already imported from `toolset._context`).

## HOW

Inside the existing `try`, directly after `abs_path, rel_path = normalize_path(path, ctx.project_dir)`
and before the `abs_path.is_file()` check:

```python
check_not_gitignored(ctx, path)
```

`normalize_path` runs first, so `..` and `.git` paths keep their own error messages. No
special case for `"."`: `is_path_gitignored` never reports the root as ignored. Add the
`ValueError` for an ignored directory to the docstring's `Raises:` section.

## ALGORITHM

```
abs_path, rel_path = normalize_path(path, project_dir)
check_not_gitignored(ctx, path)          # ValueError "Path '<p>' is excluded by .gitignore rules ..."
if abs_path.is_file(): raise ValueError(...)
raw_files = list_files_util(...); return list_directory_tree(...)
```

## DATA

Unchanged return type: `list[str]`. A directory whose files are all ignored returns `[]`.

## Tests (write first, in `tests/test_server_list_directory.py`, no mocks)

Use the `project_dir` and `tools` fixtures; write `project_dir / ".gitignore"`.

1. `.gitignore` = `secret/\n`, file `secret/key.txt` → `tools["list_directory"]("secret")`
   raises `ValueError` matching `excluded by .gitignore rules`; message does not contain `key.txt`.
2. `.gitignore` = `*.log\n`, file `logs/a.log` only → `tools["list_directory"]("logs") == []`.
3. `.gitignore` = `*\n!*/\n!*.py\n`, file `a.py` → `tools["list_directory"](".")` is not
   refused and contains `a.py`.

The existing mocked tests in this file and `TestFileToolsRefuseGitDir` in
`tests/test_file_tool_path_rules.py` must pass unchanged.

## Commit

`fix(toolset): list_directory refuses gitignored directories (#392)`
