# Step 4 — Path containment via `fs.check_path_within`

Refactoring: the containment core of `normalize_path` moves to
`mcp_coder_utils.fs.check_path_within`. Policy stays here. Existing tests pin the
behaviour (`Security error`, `outside the project directory`, `traversal`, the
`OSError` fallback, `project_dir` containing `..`, NUL byte); no new test needed.

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_4.md` exactly.
> Use the MCP tools only. Run the checks below; all must pass. Then run
> `run_format_code` and make exactly one commit.

## WHERE / WHAT / HOW — `src/mcp_workspace/file_tools/path_utils.py`

- `from mcp_coder_utils.fs import check_path_within` (never import `fs.normalize_path`).
- `normalize_path(path: str, project_dir: Path) -> tuple[Path, str]`: signature
  and return unchanged.
- Delete: the local `..` check, the NUL check, and the `resolve()` /
  `is_relative_to` try-block with its `escapes` branch.
- Keep unchanged: `project_dir is None` check, `joined_path`, the `relative_to`
  check with `_outside_error(path, project_dir, "is")`, the `.git` refusal
  (`is_path_in_git_dir` / `resolves_into_git_dir`), the return.
- Keep `_outside_error`, `_UNRESOLVABLE`, `git_dir_error`, `resolves_into_git_dir`,
  `ref_relative_path` code (used by `ref_relative_path` and the `relative_to` branch).

## ALGORITHM

```python
path_obj = Path(path)
joined_path = path_obj if path_obj.is_absolute() else project_dir / path_obj
try:
    check_path_within(path, project_dir)   # raw path, not joined_path (project_dir may contain '..')
except ValueError as exc:
    raise ValueError(f"Security error: {exc}. Path traversal outside the project directory '{project_dir}' is not allowed.") from exc
except OSError:
    logger.warning("Path.resolve() failed for '%s', using fallback check", joined_path)
# relative_to check, .git refusal, return — unchanged
```

No `RuntimeError` handling (known limitation, see docs).

## DATA

Return `(joined_path, relative_posix)` unchanged.

## Docstrings

- `normalize_path`: describe validation as the shared check (`..` segment, NUL
  byte, resolved path inside the resolved project dir) plus `relative_to` and the
  `.git` refusal. "Known limitation": on `OSError` from the shared check,
  validation falls back to the lexical `relative_to` check (`..` is still rejected
  before resolving); a symlink escape is not detected there. Symlink loops: on
  Python 3.13+ a loop takes the lexical fallback and is then treated as missing by
  the file operations; on 3.11/3.12 `resolves_into_git_dir` still raises
  `RuntimeError`.
- `ref_relative_path` Raises: drop "with the same texts as `normalize_path`".

## Tests

- `tests/file_tools/test_ref_relative_path.py`: rename
  `test_error_texts_match_normalize_path` → `test_traversal_error_names_path_and_root`
  (body unchanged).

## Docs

- `docs/file-access.md`, the "One limitation" paragraph under Path Confinement:
  keep the lexical-fallback sentence; add the symlink-loop limitation — Python
  3.13+: a loop passes via the fallback and the path is treated as missing
  (nothing outside the project is opened or written); 3.11/3.12: the operation
  fails with `RuntimeError`.
- `docs/ARCHITECTURE.md` §6 "Absolute paths stay native": add the containment
  wrapper in `path_utils.normalize_path` next to `path_utils._outside_error`; its
  `fs` part also prints native paths (`{path}` as given, root resolved).
- `docs/release-notes.md`, #400 section, add:
  `- Requires mcp-coder-utils with \`fs.write_text\` / \`fs.check_path_within\` (mcp-coder-utils#88 or later).`

## Checks

`run_pylint_check`, `run_pytest_check(extra_args=["-n", "auto"])`, `run_mypy_check`,
`run_ruff_check`, `run_tach_check`, `run_lint_imports_check`, `run_vulture_check`.

## Commit

`refactor(file_tools): check path containment via mcp_coder_utils.fs.check_path_within`
