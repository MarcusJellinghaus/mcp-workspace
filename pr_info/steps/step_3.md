# Step 3 — `github_issue_comment(body_file=...)`

## LLM prompt

> Read `pr_info/steps/summary.md` (section 1) and this file, `pr_info/steps/step_3.md`.
> `_resolve_body` from step 1 must exist in `src/mcp_workspace/server.py`; if it does not, write one line to
> `pr_info/.blocked.txt` and stop.
> Implement exactly this step with TDD: write the tests first, then the code.
> Run pylint, pytest (`-n auto`) and mypy; all must pass. Run format_code, then make one commit.

## WHERE
- `src/mcp_workspace/server.py` — `github_issue_comment`
- `tests/github_operations/test_github_write_tools_body_file.py` — append tests

## WHAT

```python
def github_issue_comment(
    number: int,
    body: str = "",
    reference_name: Optional[str] = None,
    body_file: Optional[str] = None,
) -> str:
```

## HOW
- First line inside `try`: `body = cast(str, _resolve_body(body, body_file, conflict=bool(body)))`
  (or equivalent satisfying mypy).
- Second line inside `try`, before `_issue_manager(reference_name)`:
  `if not body: raise ValueError("pass body or body_file")`. This makes the "neither given" error come before
  any `reference_name` or token error; `_tool_error` renders it as `Error: pass body or body_file`.
  `add_comment`'s own empty/whitespace check stays as the library-level guard.
- Docstring: drop "no temporary file is needed"; keep "multi-line Markdown is sent through unchanged" but note
  leading/trailing whitespace is stripped; `body` is now optional — pass `body` or `body_file`, exactly one.

## ALGORITHM
None beyond the one call.

## DATA
Output strings unchanged.

## Tests (append)

Patch `_issue_manager` with a `MagicMock` whose `add_comment` returns a `CommentData` (id 1).

1. CRLF + non-ASCII file → `add_comment` called with `(number, file_text)`.
2. `body="x"` + `body_file` → conflict error; `_issue_manager` not called.
3. Neither `body` nor `body_file` → result is `"Error: pass body or body_file"` and `_issue_manager` is not
   called (so the error wins even with an invalid `reference_name`, e.g. `reference_name="no-such-ref"`).
   No mock `side_effect` test for `add_comment`: its own empty-body rejection is already covered by
   `test_add_comment_empty_body` in `tests/github_operations/issues/test_comments_mixin.py`.
