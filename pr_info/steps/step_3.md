# Step 3 — `resolve_review_thread` + `github_review_thread_resolve`

Read `pr_info/steps/summary.md` first for overall context. Depends on step 2
(`_pr_manager` helper must already exist).

## Goal

Add the resolve tool: `github_review_thread_resolve(pr_number, thread_id,
reference_name=None)`. `thread_id` is a GraphQL node ID (opaque base64 string), so its
type is `str`, not `int`.

## WHERE

- `src/mcp_workspace/github_operations/pr_manager.py` — new `resolve_review_thread`
  method
- `src/mcp_workspace/server.py` — new `github_review_thread_resolve` tool (near
  `github_review_comment_reply`)
- `.claude/CLAUDE.md` — tool-mapping table
- Tests: `tests/github_operations/test_pr_manager.py` (new method tests),
  `tests/github_operations/test_github_write_tools_labels_pr.py` (new tool test class)

## WHAT

```python
# pr_manager.py
def resolve_review_thread(self, pr_number: int, thread_id: str) -> bool: ...
```

```python
# server.py
@mcp.tool()
def github_review_thread_resolve(
    pr_number: int,
    thread_id: str,
    reference_name: Optional[str] = None,
) -> str: ...
```

## HOW

- `resolve_review_thread` is decorated `@log_function_call` +
  `@_handle_github_errors(default_return=False)`.
- Validation is required here (unlike step 2's reply tool): the `resolveReviewThread`
  mutation only takes `threadId` — GitHub does not check it against a PR — so a
  copy-paste mistake (right thread, wrong PR) would otherwise succeed silently. Confirm
  ownership with a single targeted GraphQL lookup, `node(id: $threadId) { ... on
  PullRequestReviewThread { isResolved pullRequest { number } } }`, instead of listing
  the PR's full `reviewThreads` collection and searching — it returns exactly the three
  facts needed (not-found / wrong-PR / already-resolved) in one request.
- Use the raw `Requester.graphql_query()` call (same as `get_closing_issue_numbers`:
  `self._github_client._Github__requester.graphql_query(query=..., variables=...)`) —
  **not** `_pr_feedback_sources.fetch_review_data`'s retry-wrapped
  `requestJsonAndCheck`. That retry exists only for a read-after-write flake on a newly
  created PR node; it does not apply to a lookup immediately followed by a one-shot
  write mutation.
- Each of "not found" / "wrong PR" / "already resolved" raises a distinct `ValueError`
  message — `_handle_github_errors` re-raises `ValueError` unconditionally, so it
  reaches the tool's `except Exception as e: return f"Error: {e}"` verbatim. This
  mirrors `_validate_pr_number`'s swallow-on-bad-input style for the pr_number check,
  but raises for the ownership/state checks since those need a message distinguishing
  the three failure modes, not a silent `False`.
- The mutation itself (`resolveReviewThread(input: {threadId: $threadId}) { thread {
  isResolved } }`) is a second `graphql_query()` call, issued only after the lookup
  passes.

## ALGORITHM

```
if not self._validate_pr_number(pr_number): return False
if not isinstance(thread_id, str) or not thread_id.strip():
    raise ValueError("thread_id must be a non-empty string")
repo = self._get_repository(); if None: return False

_, lookup = requester.graphql_query(
    query="query($id: ID!) { node(id: $id) { ... on PullRequestReviewThread "
          "{ isResolved pullRequest { number } } } }",
    variables={"id": thread_id})
node = (lookup.get("data") or {}).get("node")
if node is None:
    raise ValueError(f"Review thread {thread_id} not found")
if (node.get("pullRequest") or {}).get("number") != pr_number:
    raise ValueError(f"Review thread {thread_id} does not belong to PR #{pr_number}")
if node.get("isResolved"):
    raise ValueError(f"Review thread {thread_id} is already resolved")

requester.graphql_query(
    query="mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) "
          "{ thread { isResolved } } }",
    variables={"id": thread_id})
return True
```

```
# github_review_thread_resolve
try:
    manager = _pr_manager(reference_name)
    resolved = manager.resolve_review_thread(pr_number, thread_id)
    if not resolved:
        return f"Error: failed to resolve review thread {thread_id} on PR #{pr_number}{_ref_suffix(reference_name)}"
    return f"Resolved review thread {thread_id} on PR #{pr_number}{_ref_suffix(reference_name)}"
except Exception as e:
    return f"Error: {e}"
```

## DATA

`resolve_review_thread` returns `bool` — `True` on success, `False` only for the
"invalid pr_number" / "repository unavailable" swallow cases (no exception info to
surface). All other failures raise `ValueError` with a message identifying which of
not-found / wrong-PR / already-resolved occurred.

## Tests (write first)

`tests/github_operations/test_pr_manager.py` — new tests for `resolve_review_thread`,
mocking `manager._github_client._Github__requester.graphql_query` with
`side_effect=[(headers, lookup_response), (headers, mutation_response)]` (mirrors
`test_pr_manager_closing_issues.py`'s mocking style):
- happy path: lookup returns `isResolved=False`, `pullRequest.number == pr_number` →
  mutation is called once, returns `True`
- `node` is `None` → raises `ValueError` matching "not found"; mutation never called
- `pullRequest.number != pr_number` → raises `ValueError` matching "does not belong";
  mutation never called
- `isResolved=True` → raises `ValueError` matching "already resolved"; mutation never
  called
- invalid `pr_number` (`<= 0`) → returns `False`, no GraphQL call at all
- invalid `thread_id` (empty string) → raises `ValueError`, no GraphQL call at all

`tests/github_operations/test_github_write_tools_labels_pr.py` — new
`TestGithubReviewThreadResolve` class, patching
`mcp_workspace.github_operations.pr_manager.PullRequestManager`:
- success message
- `ValueError` from the manager (any of the three reasons) → `"Error: {message}"`
- unknown `reference_name` → `"Error: Reference project 'nope' not found"`, manager
  class never constructed

## Commit

One commit covering `resolve_review_thread`, `github_review_thread_resolve`, the
CLAUDE.md row, and all tests above. Run pylint, pytest (`-n auto`), mypy — all must
pass.

Add to `.claude/CLAUDE.md`'s tool-mapping table, next to the reply-tool row added in
step 2:
`| Resolve inline PR review thread | mcp__mcp-workspace__github_review_thread_resolve |`

Commit message: `feat(server): add github_review_thread_resolve tool`

## LLM prompt for this step

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`. Implement step 3
> only: `resolve_review_thread` in `pr_manager.py` and `github_review_thread_resolve`
> in `server.py`, following the WHERE/WHAT/HOW/ALGORITHM/DATA in step_3.md exactly —
> in particular, the targeted `node(id:)` GraphQL lookup for ownership/state
> validation, and the raw `graphql_query()` call pattern (no retry). Write tests
> first, then the implementation. Update the `.claude/CLAUDE.md` tool table. Run
> pylint, pytest (`-n auto`), and mypy; all must pass. Make exactly one commit for
> this step.
