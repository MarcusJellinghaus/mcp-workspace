# Summary — #363: `body_file` for write tools, approximate sub-issue count, `check_file_size(show_allowlisted=True)`

Three independent gaps, delivered as one PR. Full requirements: GitHub issue #363.

## 1. `body_file` on the GitHub write tools

`github_issue_create`, `github_issue_edit`, `github_issue_comment` and `github_pr_create` gain
`body_file: Optional[str] = None`: a project-relative path whose content the server reads and sends
verbatim as the body. The title is never read from the file.

### Design

One private helper in `server.py`, next to `_check_not_gitignored`:

```python
def _resolve_body(body: Optional[str], body_file: Optional[str], conflict: bool) -> Optional[str]:
```

- `body_file is None` → returns `body` unchanged (existing behaviour, untouched).
- `conflict` is True → `ValueError("pass either body or body_file, not both")`.
  The caller decides what a conflict is:
  - create / comment / PR create: `conflict=bool(body)` (`body` defaults to `""`)
  - edit: `conflict=body is not None` (`body=""` clears the body there)
- Path rules are `read_file`'s: `_check_not_gitignored`, `normalize_path` (outside project → error),
  then a single `abs_path.is_file()` check (missing file and directory → one "not found or not a file" error).
- Reads with `open(abs_path, encoding="utf-8-sig", newline="")`: a leading BOM is dropped, CRLF is kept.
  Not `read_file_util`, which folds CRLF to LF.
- `UnicodeDecodeError` → `ValueError("body_file '<path>' is not valid UTF-8")`.

Each tool calls it as the **first statement in its `try`**, so every error goes through the existing
`except Exception → _tool_error(e)` and happens before any manager is built or any write is issued.
Everything after it (`_check_base_branch`, `_edit_change_lines`, manager calls) sees only the resolved `body`
and is unchanged.

`github_issue_comment`: `body: str` becomes `body: str = ""`. Right after `_resolve_body`, before the manager is
built, `if not body: raise ValueError("pass body or body_file")`, so this error precedes any `reference_name` or
token error.
`add_comment` keeps stripping the body (comments are exempt from byte-for-byte).

## 2. Approximate sub-issue count

`_subissue_write` (`server.py`) renders the count as `(~N sub-issues, may lag)`; still omitted when
`link.total is None`. GitHub's `sub_issues_summary` lags after a write; refetching does not help, and counting
via the list endpoint was rejected (API cost). Docstrings point to `github_subissue_list` for the exact set.

## 3. `check_file_size(max_lines=None, show_allowlisted=False)`

One new function in `checks/file_sizes.py`, no new types:

```python
def render_allowlisted(project_dir: Path, max_lines: int, allowlist: Set[str]) -> str:
```

A listing, not a check: every allowlist entry with its size, `not scanned (gitignored/binary)`, or `missing`;
order: sized entries by lines desc then path, then `not scanned`, then `missing`; uncapped; never a pass/fail line.
`check_file_size` branches to it when `show_allowlisted=True`; the default path is byte-identical.
The two "no lift parameter" cap comments are reworded (caps apply to the default report only).

## Architectural / design changes

- No new modules, classes or dataclasses. Two new functions: `_resolve_body` (server.py), `render_allowlisted`
  (checks/file_sizes.py).
- The GitHub write tools can now read project files — under exactly the sandbox rules of `read_file`
  (gitignore boundary + project containment). No new file-reading surface beyond that.
- Library layer (`github_operations/`) is unchanged: `body_file` is resolved entirely in the tool layer.
- `check_file_size` gains a second, read-only mode; the CI gate (default mode) is unchanged.

## Files

### Modified
- `src/mcp_workspace/server.py` — `_resolve_body`; `body_file` on 4 tools; `_subissue_write` count; `check_file_size` flag; docstrings
- `src/mcp_workspace/checks/file_sizes.py` — `render_allowlisted`; cap comments
- `tests/github_operations/test_github_write_tools_subissues.py` — count assertions
- `tests/checks/test_file_sizes.py` — `render_allowlisted` tests
- `tests/test_server_file_size.py` — flag routing tests
- `tests/LLM_Test.md` — sub-issue expectation; `body_file` and `show_allowlisted` steps
- `README.md` — tool table

### Created
- `tests/github_operations/test_github_write_tools_body_file.py` — all `body_file` tests

## Steps

1. `_resolve_body` + `github_issue_create(body_file=...)`
2. `github_issue_edit(body_file=...)`
3. `github_issue_comment(body_file=...)`
4. `github_pr_create(body_file=...)`
5. Approximate sub-issue count
6. `check_file_size(show_allowlisted=True)`
7. README and `tests/LLM_Test.md`
