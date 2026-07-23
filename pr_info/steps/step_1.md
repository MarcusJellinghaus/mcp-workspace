# Step 1 — Extract `_pr_to_data`, add `assignees` field, update `create_mock_pr`

> Read `pr_info/steps/summary.md` first. This step is the refactor that makes the
> `assignees` addition a one-line change and keeps all existing PR-manager tests
> green. It contains **no** new public API — that is Step 2. One commit.

## WHERE

- Modify: `src/mcp_workspace/github_operations/pr_manager.py`
- Modify: `tests/github_operations/test_pr_manager.py` (the shared `create_mock_pr` helper)

## WHAT

1. **`PullRequestData`** — add one field:
   ```python
   assignees: list[str]
   ```

2. **New module-level helper** (place near `_empty_pr_feedback`, after the TypedDicts):
   ```python
   def _pr_to_data(pr: PullRequest) -> PullRequestData:
       """Flatten a live PyGithub PullRequest into a plain PullRequestData dict."""
   ```

3. **`create_mock_pr`** (test helper) — add an overridable `assignees=[]` default that
   produces `.login`-bearing mock users.

4. **`create_pull_request` docstring** (Boy-Scout, A3) — the "Success response includes"
   list in the docstring is missing fields that `_pr_to_data` returns. Add
   `- assignees: GitHub usernames assigned to the PR (list[str])` and, since it is
   likewise absent, `- mergeable_state: Mergeability state string (str)`. (Verified
   against source: the current list omits both `assignees` and `mergeable_state`.)
   Keep it minimal — one line each.

## HOW (integration points)

- Add import at top of `pr_manager.py`:
  ```python
  from github.PullRequest import PullRequest
  ```
- Route **all 5** existing serialization sites through `_pr_to_data`:
  - `create_pull_request` — `return _pr_to_data(pr)`
  - `get_pull_request` — `return _pr_to_data(pr)`
  - `list_pull_requests` — `pr_list.append(_pr_to_data(pr))` (drop the `cast(...)` wrapper)
  - `find_pull_request_by_head` — `return [_pr_to_data(pr) for pr in prs]` (drop the `cast(...)` wrapper)
  - `close_pull_request` — `return _pr_to_data(updated_pr)` (keep the existing re-fetch; just serialize the re-fetched object)
- Do **not** change the empty/error returns — they stay `cast(PullRequestData, {})` / `[]`.
- `create_mock_pr` keeps returning a bare `MagicMock`; only add the `.assignees` wiring.

### Inner `try/except GithubException` in the 3 dict-returning methods (A1)

`create_pull_request`, `get_pull_request`, and `close_pull_request` currently wrap
their serialization + preceding API calls in an inner `try/except GithubException`
that logs and `return cast(PullRequestData, {})`, **on top of** the
`@_handle_github_errors(lambda: cast(PullRequestData, {}))` decorator.

**Verified against source:** the inner handler returns exactly `cast(PullRequestData, {})`
— the *same* value the decorator produces as its `default_return` for a non-auth
`GithubException`. The inner block is therefore redundant. (It is also *inconsistent*
with the codebase: the mirrored `issues/manager.py` methods — `create_issue`,
`get_issue`, `close_issue` — have **no** inner `try/except` and let the decorator own
error handling. The inner block additionally masks 401/403 by returning `{}` where the
decorator would re-raise; removing it aligns PR-manager with the intended
`@_handle_github_errors` contract.)

**Instruction — redundant-remove:** In `create_pull_request`, `get_pull_request`,
and `close_pull_request`, **delete** the now-redundant inner `try/except GithubException`
(including its `logger.error(...)` and `return cast(PullRequestData, {})`), de-indent
the body, and `return _pr_to_data(pr)` (respectively `_pr_to_data(updated_pr)`) directly
— letting `@_handle_github_errors` own error handling (DRY / clean deletion, no dead
structure). Keep the early `return cast(PullRequestData, {})` guards for validation and
`repo is None`. If the `GithubException` import becomes unused after this, drop it too.

## ALGORITHM (`_pr_to_data`)

```
return {
    number, title, body, state,
    head_branch=pr.head.ref, base_branch=pr.base.ref, url=pr.html_url,
    created_at=pr.created_at.isoformat() if pr.created_at else None,
    updated_at=pr.updated_at.isoformat() if pr.updated_at else None,
    user=pr.user.login if pr.user else None,
    mergeable, mergeable_state, merged, draft,
    assignees=[a.login for a in pr.assignees],   # NEW: NamedUser -> login
}
```

## `create_mock_pr` change (test helper)

```python
# after the existing user handling, before `return mock_pr`
mock_pr.assignees = overrides.get("assignees", [])
```
Callers that want assignees pass `assignees=[MagicMock(login="alice")]`. Default `[]`
keeps every existing test green (an unconfigured `.assignees` would be a non-iterable
`MagicMock` → `TypeError` in `[a.login for a in pr.assignees]`).

## DATA

- `_pr_to_data` returns a `PullRequestData` (now including `assignees: list[str]`).
- Existing method return types are unchanged (`PullRequestData` / `List[PullRequestData]`).

## TDD order

1. Update `create_mock_pr` with the `assignees=[]` default.
2. Add `assignees` to `PullRequestData` and the `_pr_to_data` helper; route the 5 sites.
3. Assert the `assignees` field is present/correct on **more than one** routed method's
   return, so the contract is covered across the serialization sites — not just one
   method (A2). Use a parameterized test, or assert on **both** `get_pull_request` and
   `list_pull_requests`, e.g.:
   - for a PR mocked with `assignees=[MagicMock(login="alice")]` →
     `result["assignees"] == ["alice"]` (verified on `get_pull_request` and on an item
     from `list_pull_requests`);
   - default (no assignees) → `result["assignees"] == []`.
4. Run all three checks; the full existing PR-manager suite must stay green.

## Checks (MCP tools, after each edit)

- `mcp__tools-py__run_pylint_check`
- `mcp__tools-py__run_pytest_check` with
  `extra_args=["-n", "auto"]`, `markers=["git_integration"]` (PR-manager tests are marked `git_integration`)
- `mcp__tools-py__run_mypy_check`

## Commit

One commit: field + helper + 5 routed sites + `create_mock_pr` default + assertions, all checks passing.

## LLM Prompt

> Implement Step 1 from `pr_info/steps/step_1.md` (context: `pr_info/steps/summary.md`).
> In `src/mcp_workspace/github_operations/pr_manager.py`: import
> `from github.PullRequest import PullRequest`, add `assignees: list[str]` to
> `PullRequestData`, add a module-level `_pr_to_data(pr: PullRequest) -> PullRequestData`
> helper that flattens a live PR (including `assignees=[a.login for a in pr.assignees]`),
> and route all 5 existing serialization sites (`create_pull_request`,
> `get_pull_request`, `list_pull_requests`, `find_pull_request_by_head`,
> `close_pull_request`) through it, dropping the now-redundant `cast(...)` wrappers.
> In `create_pull_request`, `get_pull_request`, and `close_pull_request`, also delete
> the now-redundant inner `try/except GithubException` (it returned the same `{}` the
> `@_handle_github_errors` decorator already produces) and `return _pr_to_data(...)`
> directly; drop the `GithubException` import if it becomes unused. Keep the validation /
> `repo is None` early `return cast(PullRequestData, {})` guards and leave empty/error
> returns as-is. Also update `create_pull_request`'s "Success response includes" docstring
> list to add `assignees` and `mergeable_state`. In
> `tests/github_operations/test_pr_manager.py`, give `create_mock_pr` an overridable
> `assignees=[]` default and assert returned data carries `assignees` on more than one
> routed method (e.g. `get_pull_request` and `list_pull_requests`). Use only MCP file
> tools. After the edit run
> pylint, pytest (`-n auto`, marker `git_integration`), and mypy; fix everything until
> green. Do not add `add_assignees` yet — that is Step 2.
