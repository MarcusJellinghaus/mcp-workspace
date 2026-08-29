# Step 5 — `github_issue_comment` tool

## Prompt for LLM

> Read `pr_info/steps/summary.md` (especially "§3 Write failures must not read as
> success" — note this tool's sentinel differs from the issue tools'), then
> implement this step (`pr_info/steps/step_5.md`) only. Follow TDD: write the
> tests first, watch them fail, then implement. Use MCP tools for all file and
> check operations. One commit at the end.

Independent of steps 4, 6 and 7.

---

## WHERE

- `src/mcp_workspace/server.py` — after `github_issue_edit`
- `vulture_whitelist.py` — `_.github_issue_comment`
- `tests/github_operations/test_github_write_tools_issues.py` — new test class,
  alongside the `github_issue_create` tests from step 3

## WHAT

```python
@mcp.tool()
@log_function_call
def github_issue_comment(number: int, body: str) -> str:
```

Backed by the existing `CommentsMixin.add_comment` — no library change.

## HOW

- Lazy `IssueManager` import inside the body, as in steps 3–4.
- **Sentinel differs:** `add_comment` returns a `CommentData` whose failure form
  is `id == 0`, not `number == 0`. Check `comment["id"]`.
- `add_comment` already raises `ValueError` on an empty body; the tool does not
  re-validate, it lets the `except Exception` render it.
- Docstring must state plainly that it **posts a real comment to GitHub**, and
  that `body` is taken inline.
- `vulture_whitelist.py`: `_.github_issue_comment`.

## ALGORITHM

```
lazy import IssueManager
try:
    manager = IssueManager(project_dir=_project_dir)
    comment = manager.add_comment(number, body)
    if not comment["id"]: return f"Error: failed to add comment to issue #{number}"
    return f"Added comment to issue #{number} — {comment['url']}"
except Exception as e: return f"Error: {e}"
```

## DATA

- Success: `Added comment to issue #42 — https://github.com/o/r/issues/42#issuecomment-1`
- Failure: `Error: <reason>`

## Tests (TDD)

New class in `tests/github_operations/test_github_write_tools_issues.py`:

1. Happy path — first line is `Added comment to issue #42 — <url>`;
   `add_comment` called once with `(42, body)`.
2. Sentinel — `add_comment` returns a `CommentData` with `id=0` → result starts
   with `Error:` and does not contain `Added comment`.
3. `ValueError` from an empty body surfaces as `Error: Comment body cannot be empty`.
4. Arbitrary exception → `Error: <msg>`.
5. Multi-line body passes through unchanged — the point of accepting it inline
   is to kill the `cat > /tmp/... <<EOF` heredoc.

## Checks

`run_pylint_check`, `run_mypy_check`, `run_pytest_check`, `run_vulture_check`.

## Commit

`Add github_issue_comment MCP tool`
