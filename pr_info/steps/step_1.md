# Step 1 — `_resolve_body` helper + `github_issue_create(body_file=...)`

## LLM prompt

> Read `pr_info/steps/summary.md` (section 1) and this file, `pr_info/steps/step_1.md`.
> Implement exactly this step with TDD: write the tests first, then the code.
> Run pylint, pytest (`-n auto`) and mypy; all must pass. Run format_code, then make one commit.

## WHERE
- `src/mcp_workspace/server.py` — new `_resolve_body` (directly after `_check_not_gitignored`); `github_issue_create`
- `tests/github_operations/test_github_write_tools_body_file.py` — **new**

## WHAT

```python
def _resolve_body(
    body: Optional[str], body_file: Optional[str], conflict: bool
) -> Optional[str]:
    """Return the body to send: body unchanged, or body_file's text verbatim.

    Raises:
        ValueError: conflict is True, the project directory is unset, the path is
            gitignored / outside the project / not a file, or the file is not UTF-8.
    """

def github_issue_create(
    title: str,
    body: str = "",
    labels: Optional[List[str]] = None,
    assignees: Optional[List[str]] = None,
    reference_name: Optional[str] = None,
    body_file: Optional[str] = None,
) -> str:
```

`body_file` goes **last** so existing positional callers are unaffected.

## HOW
- Reuse `_check_not_gitignored` and `normalize_path` (already imported in `server.py`). Do not use `read_file_util`
  (it folds CRLF to LF).
- In `github_issue_create`, first line inside `try`:
  `body = cast(str, _resolve_body(body, body_file, conflict=bool(body)))` (or an equivalent that keeps mypy happy),
  before `_check_base_branch(body)`. All errors flow through the existing `except Exception → _tool_error(e)`.
- Docstring: document `body_file` (project-relative; same rules as `read_file`, so gitignored paths are refused;
  sent byte for byte, leading UTF-8 BOM dropped; mutually exclusive with a non-empty `body`; the title is never
  read from the file; the Base Branch check applies to the file text).

## ALGORITHM

```
if body_file is None: return body
if conflict: raise ValueError("pass either body or body_file, not both")
if _project_dir is None: raise ValueError("Project directory has not been set")
_check_not_gitignored(body_file); abs_path, _ = normalize_path(body_file, _project_dir)
if not abs_path.is_file(): raise ValueError(f"body_file '{body_file}' not found or not a file")
try: open(abs_path, encoding="utf-8-sig", newline="").read()
except UnicodeDecodeError: raise ValueError(f"body_file '{body_file}' is not valid UTF-8")
```

`body_file=""` needs no special case: it normalizes to the project directory and fails `is_file()`.

## DATA
- `_resolve_body` returns `str` (file text) or the passed `body`.
- Tool output strings unchanged; errors render as `"Error: <message>"`.

## Tests (new file)

Fixtures mirror `test_github_write_tools_issues.py`: autouse `set_project_dir(project_dir)`; patch
`mcp_workspace.server._issue_manager` to return a `MagicMock` whose `create_issue` returns an `IssueData`
(number 42) and whose `get_available_labels` returns `[]`. Write files with `Path.write_bytes` so CRLF is exact.

1. 20 KB body (non-ASCII e.g. `äöü → ✓`, backticks, CRLF line endings) → `create_issue.call_args.kwargs["body"]`
   equals `content.decode("utf-8")` exactly (assert `"\r\n"` present).
2. File starting with `b"\xef\xbb\xbf"` → body sent without the BOM.
3. `body="x"` + `body_file=...` → error mentioning both; `_issue_manager` not called.
4. Parametrized bad paths, each returns a string starting `"Error:"` and `_issue_manager` is not called:
   missing file; `"../outside.md"`; gitignored (write `.gitignore` containing `*.log`, create `draft.log`);
   non-UTF-8 file (`b"\xff\xfe\x00bad"`); a directory.
5. File with a malformed `### Base Branch` section (two lines under the heading) → Base Branch error;
   `create_issue` not called.
6. Regression: inline `body` without `body_file` is passed through unchanged.
