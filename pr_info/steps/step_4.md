# Step 4 — `github_issue_edit` tool

## Prompt for LLM

> Read `pr_info/steps/summary.md` (especially "§4 `edit_issue`" and the partial
> write rule), then implement this step (`pr_info/steps/step_4.md`) only.
> Follow TDD: write the tests first, watch them fail, then implement.
> Use MCP tools for all file and check operations. One commit at the end.

Depends on step 2 (`edit_issue`) and step 3 (`_check_labels`, `_resolve_assignees`).

---

## WHERE

- `src/mcp_workspace/server.py` — after `github_issue_create`
- `vulture_whitelist.py` — `_.github_issue_edit`
- `tests/github_operations/test_github_write_tools.py` — new test class

## WHAT

```python
@mcp.tool()
@log_function_call
def github_issue_edit(
    number: int,
    title: Optional[str] = None,
    body: Optional[str] = None,
    add_labels: Optional[List[str]] = None,
    remove_labels: Optional[List[str]] = None,
    add_assignees: Optional[List[str]] = None,
    state: Optional[str] = None,
) -> str:
```

## HOW

- Reuses `_check_labels` and `_resolve_assignees` from step 3 unchanged. The
  status guard is passed **both** `add_labels` and `remove_labels` — removing a
  status label leaves zero, which makes `_collect_github_label` fall back to
  `DEFAULT_LABEL`.
- Docstring must state plainly that it **modifies a real GitHub issue**, and
  that `state` accepts only `"open"` / `"closed"`.
- **Never a bare error after a partial write.** `edit_issue` has no transaction;
  a failure at the label step leaves the scalar edit in place. On the empty
  sentinel the tool refetches with `get_issue` and reports the resulting state
  behind a warning line, so the caller can always see what landed. A bare error
  is returned only when the refetch *also* comes back empty.

## ALGORITHM

```
lazy import IssueManager
try:
    manager = IssueManager(project_dir=_project_dir)
    err = _check_labels(manager, add_labels or [], remove_labels or []);  if err: return err
    resolved = _resolve_assignees(manager, add_assignees or [])
    issue = manager.edit_issue(number, title=..., body=..., add_labels=...,
                               remove_labels=..., add_assignees=resolved or None, state=state)
    warning = ""
    if not issue["number"]:                                  # mid-sequence failure
        issue = manager.get_issue(number)
        if not issue["number"]: return f"Error: edit of issue #{number} failed and the issue could not be re-read"
        warning = "Warning: edit partially failed — resulting state below\n"
    return warning + f"Updated issue #{issue['number']} — {issue['url']} (state: {issue['state']})\n" \
                     f"Labels: {', '.join(issue['labels']) or '(none)'}\n" \
                     f"Assignees: {', '.join(issue['assignees']) or '(none)'}"
except Exception as e: return f"Error: {e}"
```

The resulting label set **and** assignee list both come from `edit_issue`'s own
refetch — no extra call. Assignees are reported because a non-assignable login
succeeds silently with no effect, and unlike labels there is no cheap
pre-validation for them.

## DATA

```
Updated issue #42 — https://github.com/o/r/issues/42 (state: open)
Labels: bug, enhancement
Assignees: alice
```

`(none)` for an empty collection. Partial-write path prepends
`Warning: edit partially failed — resulting state below`.

`state` maps to open/closed only — GitHub's `completed` / `not_planned` close
reason is out of scope.

## Tests (TDD)

New class in `tests/github_operations/test_github_write_tools.py`, same patching
pattern as step 3:

1. Happy path — three lines; first is `Updated issue #42 — <url> (state: open)`;
   resulting labels and assignees rendered from the returned `IssueData`.
2. Empty collections render `(none)`.
3. Arguments forwarded — `edit_issue` receives every non-`None` argument.
4. Partial write — `edit_issue` returns empty, `get_issue` returns real data →
   output starts with `Warning:` and still shows the resulting state; `get_issue`
   called exactly once.
5. Total failure — both return empty → `Error:`, no `Warning`.
6. Status label on the **add** side rejected; `edit_issue` never called.
7. Status label on the **remove** side rejected; `edit_issue` never called.
8. Unknown add-side label rejected; `edit_issue` never called.
9. `remove_labels` alone → `get_available_labels` never called (add side is empty).
10. `add_assignees=["@me"]` resolved before reaching `edit_issue`.
11. `ValueError` from a bad `state` surfaces as `Error: ...`.

## Checks

`run_pylint_check`, `run_mypy_check`, `run_pytest_check`, `run_vulture_check`.

## Commit

`Add github_issue_edit MCP tool`
