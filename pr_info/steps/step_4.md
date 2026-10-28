# Step 4 — `github_pr_create(body_file=...)`

## LLM prompt

> Read `pr_info/steps/summary.md` (section 1) and this file, `pr_info/steps/step_4.md`.
> `_resolve_body` from step 1 must exist in `src/mcp_workspace/server.py`; if it does not, write one line to
> `pr_info/.blocked.txt` and stop.
> Implement exactly this step with TDD: write the tests first, then the code.
> Run pylint, pytest (`-n auto`) and mypy; all must pass. Run format_code, then make one commit.

## WHERE
- `src/mcp_workspace/server.py` — `github_pr_create`
- `tests/github_operations/test_github_write_tools_body_file.py` — append tests

## WHAT

```python
def github_pr_create(
    title: str,
    body: str = "",
    head: Optional[str] = None,
    base: Optional[str] = None,
    body_file: Optional[str] = None,
) -> str:
```

## HOW
- First line inside `try` (before the empty-title check and before `PullRequestManager(...)`):
  `body = cast(str, _resolve_body(body, body_file, conflict=bool(body)))`.
- No Base Branch body check is added (the issue says PR create gains none).
- Docstring: add `body_file`; add the `body_file` errors to the "returned without creating anything" list
  in general terms (conflict, unreadable/refused path).

## ALGORITHM
None beyond the one call.

## DATA
Output strings unchanged.

## Tests (append)

Follow the mocking pattern in `tests/github_operations/test_github_pr_create_base.py`
(patch `PullRequestManager`, `get_current_branch_name`, and pass explicit `head` and `base` so no base
resolution or origin probe runs).

1. CRLF file → `create_pull_request.call_args.kwargs["body"]` equals the file text exactly.
2. `body="x"` + `body_file` → conflict error; `PullRequestManager` not instantiated.
3. Missing file → error; `PullRequestManager` not instantiated.
