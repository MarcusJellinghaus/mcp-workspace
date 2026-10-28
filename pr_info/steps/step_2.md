# Step 2 — `github_issue_edit(body_file=...)`

## LLM prompt

> Read `pr_info/steps/summary.md` (section 1) and this file, `pr_info/steps/step_2.md`.
> `_resolve_body` from step 1 must exist in `src/mcp_workspace/server.py`; if it does not, write one line to
> `pr_info/.blocked.txt` and stop.
> Implement exactly this step with TDD: write the tests first, then the code.
> Run pylint, pytest (`-n auto`) and mypy; all must pass. Run format_code, then make one commit.

## WHERE
- `src/mcp_workspace/server.py` — `github_issue_edit`
- `tests/github_operations/test_github_write_tools_body_file.py` — append tests

## WHAT

```python
def github_issue_edit(
    number: int,
    title: Optional[str] = None,
    body: Optional[str] = None,
    add_labels: Optional[List[str]] = None,
    remove_labels: Optional[List[str]] = None,
    add_assignees: Optional[List[str]] = None,
    state: Optional[str] = None,
    reference_name: Optional[str] = None,
    body_file: Optional[str] = None,
) -> str:
```

## HOW
- First line inside the outer `try` (before the `number <= 0` check):
  `body = _resolve_body(body, body_file, conflict=body is not None)`.
- Nothing else changes: `_check_base_branch(body)`, `manager.edit_issue(body=body)` and
  `_edit_change_lines(issue, title, body, ...)` already use `body`, so the file text is validated, sent, and
  reported as `body` in Applied / Not applied.
- Docstring: add `body_file`; note conflict means any `body` value including `""`; the Base Branch sentence
  ("When `body` is passed…") becomes "When `body` or `body_file` is passed…".

## ALGORITHM
None beyond the one call.

## DATA
Output strings unchanged.

## Tests (append)

Patch `_issue_manager` with a `MagicMock`: `get_available_labels → []`, `edit_issue` returns an `IssueData`.

1. CRLF file → `edit_issue.call_args.kwargs["body"]` equals the file text exactly, and the output starts with
   `"Updated issue #"` with no `"Error"`/`"Warning"` line. Note: on success `github_issue_edit` does not call
   `_edit_change_lines` (it runs only on partial failure, `server.py` ≈1526–1534), so the success output has no
   `Applied:` line; the "lists `body` in its change report" criterion is covered by test 4.
2. `body=""` + `body_file` → conflict error; `_issue_manager` not called.
3. File with malformed `### Base Branch` → Base Branch error; `edit_issue` not called.
4. Partial failure: `edit_issue` raises `GithubException(500, {"message": "boom"}, None)` after appending
   `"body"` to `attempted_writes` (use a `side_effect` function); `get_issue` returns an issue whose body
   equals the file text → output contains `"Applied: body"`.
5. Regression: `body=""` without `body_file` still reaches `edit_issue` as `""`.
