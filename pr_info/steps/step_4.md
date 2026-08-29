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
- `tests/github_operations/test_github_write_tools_issue_edit.py` — **new file**
  (its own module: 17 tests would push the create/comment module past the
  750-line limit — see summary, "Test module layout")

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
- **Never a bare error after a partial write — on any failure channel, not just
  the sentinel.** `edit_issue` has no transaction; a failure at the label step
  leaves the scalar edit in place. There are **two** ways that failure reaches
  the tool, and the sentinel is only one of them:

  | Channel | Cause | What `edit_issue` does |
  |---|---|---|
  | Empty `IssueData` (`number == 0`) | swallowed 404 / 422 / 5xx | returns the sentinel |
  | Raised exception | `_handle_github_errors` **re-raises** 401/403 `GithubException` and every `ValueError`, including the `IssueIdentityMismatchError` that `_get_issue_checked` throws on the *final* refetch | propagates |

  A 403 on `add_to_labels` after `issue.edit()` landed, or a transfer detected by
  the closing refetch after every write landed, both take the second channel. If
  that channel falls through to the outer `except Exception`, the caller gets a
  bare `Error:` after a write that succeeded — exactly what the issue forbids.
  So the `edit_issue` call gets **its own** `try/except (GithubException,
  ValueError)`, and both channels converge on the same refetch-and-warn path.

- **Pre-validate `number` and `state` in the tool** so the second channel cannot
  contain a *pre-write* failure. `edit_issue` validates both before its first
  API call, so a `ValueError` from them means nothing was written — but once the
  tool treats raised exceptions as possible partial writes it can no longer tell
  the two apart. Checking `number > 0` and `state in (None, "open", "closed")`
  up front, before any API call, keeps those two as plain `Error:` results and
  leaves the inner `except` to mean one thing only: *the write sequence started
  and something after it failed*. The library keeps its own identical checks —
  it has other callers and must not depend on this tool.

- **Report which requested changes landed.** The refetch already carries the
  resulting title, body, state, labels and assignees, so the tool compares each
  requested change against it and renders `Applied:` / `Not applied:` lines. No
  extra API call, and no guessing about where in the sequence the failure hit.

## ALGORITHM

```
lazy import IssueManager, GithubException

try:
    # pre-write validation — nothing has been written, so a plain error is honest
    if number <= 0: return f"Error: invalid issue number: {number}"
    if state not in (None, "open", "closed"): return "Error: state must be 'open' or 'closed'"

    manager = IssueManager(project_dir=_project_dir)
    err = _check_labels(manager, add_labels or [], remove_labels or []);  if err: return err
    resolved = _resolve_assignees(manager, add_assignees or [])

    reason = ""
    try:
        issue = manager.edit_issue(number, title=..., body=..., add_labels=...,
                                   remove_labels=..., add_assignees=resolved or None, state=state)
        if not issue["number"]: reason = "swallowed API error"      # channel 1: sentinel
    except (GithubException, ValueError) as e:                      # channel 2: re-raised
        issue, reason = create_empty_issue_data(), str(e)

    if reason:                       # the write sequence started and did not finish cleanly
        try:
            issue = manager.get_issue(number)
        except Exception as e: return f"Error: edit of issue #{number} failed ({reason}) and the issue could not be re-read: {e}"
        if not issue["number"]: return f"Error: edit of issue #{number} failed ({reason}) and the issue could not be re-read"

    return _render_edit_result(issue, reason, requested=...)
except Exception as e: return f"Error: {e}"
```

`_render_edit_result` (inline in the tool, or a small module-private helper if
it reads better):

```
lines = []
if reason:
    lines.append(f"Warning: edit partially failed ({reason}) — resulting state below")
    applied, not_applied = [], []
    for name, landed in (("title",       title  is None or issue["title"] == title),
                         ("body",        body   is None or issue["body"]  == body),
                         ("state",       state  is None or issue["state"] == state),
                         ("add_labels",     all(l in issue["labels"]    for l in add_labels or [])),
                         ("remove_labels",  all(l not in issue["labels"] for l in remove_labels or [])),
                         ("add_assignees",  all(a in issue["assignees"] for a in resolved))):
        if <that argument was requested>: (applied if landed else not_applied).append(name)
    lines.append(f"Applied: {', '.join(applied) or '(none)'}")
    lines.append(f"Not applied: {', '.join(not_applied) or '(none)'}")
lines.append(f"Updated issue #{issue['number']} — {issue['url']} (state: {issue['state']})")
lines.append(f"Labels: {', '.join(issue['labels']) or '(none)'}")
lines.append(f"Assignees: {', '.join(issue['assignees']) or '(none)'}")
return "\n".join(lines)
```

Only requested fields appear in `Applied:` / `Not applied:` — an argument left
at `None` or `[]` is not a change and is not reported either way.

**No path returns a bare error after a partial write.** The bare-error paths are
exactly four, and each one is provably before or beyond the reach of a write:

1. pre-write validation of `number` / `state` — no API call has been made;
2. `_check_labels` rejection, and a failed label lookup — the guard runs before
   `edit_issue`;
3. `IssueManager(...)` construction failure — no client exists yet;
4. the write failed **and** the refetch also failed — a partial write may exist,
   reporting it is impossible, and the message says exactly that instead of
   implying nothing happened.

Everything else, including a re-raised 403 mid-sequence and an
`IssueIdentityMismatchError` from `edit_issue`'s closing refetch, ends on the
warn-and-report path.

The resulting label set **and** assignee list both come from `edit_issue`'s own
refetch on the success path — no extra call; the extra `get_issue` is paid only
when something went wrong. Assignees are reported because a non-assignable login
succeeds silently with no effect, and unlike labels there is no cheap
pre-validation for them.

## DATA

Success:

```
Updated issue #42 — https://github.com/o/r/issues/42 (state: open)
Labels: bug, enhancement
Assignees: alice
```

Partial write (either failure channel):

```
Warning: edit partially failed (403 Resource not accessible by integration) — resulting state below
Applied: title, add_labels
Not applied: add_assignees
Updated issue #42 — https://github.com/o/r/issues/42 (state: open)
Labels: bug, enhancement
Assignees: (none)
```

`(none)` for an empty collection, and for an empty `Applied:` / `Not applied:`
list.

`state` maps to open/closed only — GitHub's `completed` / `not_planned` close
reason is out of scope.

## Tests (TDD)

New `tests/github_operations/test_github_write_tools_issue_edit.py`, same
patching pattern as step 3 and reusing the autouse fixtures step 3 put in
`tests/github_operations/conftest.py`:

1. Happy path — three lines; first is `Updated issue #42 — <url> (state: open)`;
   resulting labels and assignees rendered from the returned `IssueData`.
2. Empty collections render `(none)`.
3. Arguments forwarded — `edit_issue` receives every non-`None` argument.
4. Partial write, **sentinel channel** — `edit_issue` returns empty, `get_issue`
   returns real data → output starts with `Warning:` and still shows the
   resulting state; `get_issue` called exactly once.
5. Partial write, **exception channel** — `edit_issue` raises a 403
   `GithubException`, `get_issue` returns data showing the title change landed
   but the label add did not → output starts with `Warning:` carrying the 403
   text, `Applied: title`, `Not applied: add_labels`, then the resulting state.
   **This is the regression test for the bug the sentinel-only design had.**
6. Partial write, **`ValueError` channel** — `edit_issue` raises
   `IssueIdentityMismatchError` (a `ValueError`) → same warn-and-report shape,
   not a bare `Error:`.
7. `Applied:` / `Not applied:` only name requested arguments — a partial-write
   call passing `title` alone never mentions `add_labels` or `state`.
8. Total failure — `edit_issue` returns empty and `get_issue` returns empty →
   `Error:` naming both the reason and the failed re-read; no `Warning`.
9. Refetch itself raises → `Error:` naming both failures; no `Warning`.
10. Status label on the **add** side rejected; `edit_issue` never called.
11. Status label on the **remove** side rejected; `edit_issue` never called.
12. Unknown add-side label rejected; `edit_issue` never called.
13. Label lookup fails (`get_available_labels` raises) → `Error:` with the API
    text, not `unknown label`; `edit_issue` never called.
14. `remove_labels` alone → `get_available_labels` never called (add side is empty).
15. `add_assignees=["@me"]` resolved before reaching `edit_issue`.
16. Bad `state="bogus"` → `Error:` from the tool's own pre-check; `edit_issue`
    **never called**, and no `Warning` (nothing was written).
17. `number=0` → `Error:` from the tool's own pre-check; `edit_issue` never called.

## Checks

`run_pylint_check`, `run_mypy_check`, `run_pytest_check`, `run_vulture_check`.

## Commit

`Add github_issue_edit MCP tool`
