# Step 1 — Shared normalisation and counting from `mcp_coder_utils.fs`

Pure refactoring: no behaviour change. Existing tests pin the behaviour; the only
test change is deleting duplicates of mcp-coder-utils tests.

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_1.md` exactly.
> Use the MCP tools only (see `.claude/CLAUDE.md`). Run the checks listed below;
> all must pass. Then run `run_format_code` and make exactly one commit.

## Precondition

`from mcp_coder_utils.fs import count_line_endings, dominant_newline, normalize_line_endings, write_text, check_path_within`
must import in the project environment (check with `search_library_files`,
scope `mcp_coder_utils`, pattern `def (write_text|check_path_within|dominant_newline)`).
If any is missing: write one line to `pr_info/.blocked.txt` and stop.

## WHERE / WHAT / HOW

### `tach.toml`
- Add, next to the other `mcp_coder_utils.*` entries:
  ```toml
  [[modules]]
  path = "mcp_coder_utils.fs"
  layer = "utilities"
  depends_on = []
  ```
- Add `{ path = "mcp_coder_utils.fs" }` to `depends_on` of
  `mcp_workspace.file_tools` and `mcp_workspace.toolset`.
- `tests` module: unchanged (no test imports `fs` after this plan).

### `src/mcp_workspace/file_tools/path_utils.py`
- Delete `normalize_line_endings`.

### `src/mcp_workspace/file_tools/line_endings.py`
- Delete local `count_line_endings`.
- Add `from mcp_coder_utils.fs import count_line_endings`.
  `describe_line_endings` and `target_newline` keep calling it (unchanged code).

### `src/mcp_workspace/file_tools/edit_file.py`
- `from mcp_coder_utils.fs import normalize_line_endings`
- `from mcp_workspace.file_tools.path_utils import normalize_path`

### `src/mcp_workspace/file_tools/file_operations.py`
- Same import split as `edit_file.py`. `_validate_save_parameters` unchanged otherwise.

### `src/mcp_workspace/toolset/_github_write_helpers.py`
- `from mcp_coder_utils.fs import normalize_line_endings`
- ```python
  def _normalize_newlines(text: str | None) -> str:
      return normalize_line_endings(text or "")
  ```
  Keep the docstring (`""` when text is None). Do not touch the verbatim
  `newline=""` I/O in `save_body` / `resolve_body`.

### Tests — delete duplicates of mcp-coder-utils tests
- `tests/file_tools/test_path_utils.py`: delete `test_normalize_line_endings_crlf`,
  `_standalone_cr`, `_mixed`; import becomes `from mcp_workspace.file_tools.path_utils import normalize_path`.
- `tests/file_tools/test_edit_file_issues.py`: delete method
  `test_normalize_line_endings` and the `normalize_line_endings` import.
- `tests/file_tools/test_line_endings.py`: delete `test_count_line_endings` and
  drop `count_line_endings` from the import.

### `docs/ARCHITECTURE.md`
- Shared Libs row (line 38): `Logging via mcp_coder_utils` →
  `Logging and filesystem helpers (fs: line endings, path containment) via mcp_coder_utils`.

## ALGORITHM

None — imports and deletions only.

## DATA

Unchanged: `count_line_endings(bytes) -> tuple[int, int, int]`,
`normalize_line_endings(str) -> str`, `_normalize_newlines(str | None) -> str`.

## Checks

`run_pylint_check`, `run_pytest_check(extra_args=["-n", "auto"])`, `run_mypy_check`,
`run_ruff_check`, `run_tach_check` (one extra ModuleNotFound warning for
`mcp_coder_utils.fs` is expected), `run_lint_imports_check`, `run_vulture_check`.

## Commit

`refactor(file_tools): take line-ending normalisation and counting from mcp_coder_utils.fs`
