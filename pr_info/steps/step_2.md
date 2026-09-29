# Step 2 — the three MCP tools in `server.py`

Read [summary.md](./summary.md) first, then this file. Depends on Step 1.

## WHERE

Created:

- `tests/github_operations/test_github_write_tools_subissues.py`

Modified:

- `src/mcp_workspace/server.py` — two private helpers plus three tools, placed
  immediately after `github_issue_edit`
- `vulture_whitelist.py` — three names under "GitHub write tools registered in
  server.py" (line ~54)
- `tests/github_operations/test_github_write_tools_reference.py` — the three
  tools added to the existing `_TOOL_CASES` / `_TOOL_IDS` routing table

## WHAT

Private helpers in `server.py`:

```python
def _api_error(exc: Exception, reference_name: Optional[str]) -> str
def _subissue_write(
    parent_number: int,
    child_number: int,
    unlink: bool,
    reference_name: Optional[str],
) -> str
```

Tools, signatures exactly as the issue specifies:

```python
def github_subissue_add(
    parent_number: int, child_number: int, reference_name: Optional[str] = None
) -> str:
    """Link an existing issue as a sub-issue of another. This writes to GitHub."""

def github_subissue_list(
    parent_number: int, max_results: int = 30, reference_name: Optional[str] = None
) -> str:
    """List an issue's sub-issues. This only reads from GitHub."""

def github_subissue_remove(
    parent_number: int, child_number: int, reference_name: Optional[str] = None
) -> str:
    """Unlink a sub-issue from its parent. This writes to GitHub."""
```

The two write tools are one-liners delegating to `_subissue_write` with
`unlink=False` / `unlink=True`.

## HOW

- `@mcp.tool()` then `@log_function_call` on each tool, in that order, on a
  module-level function. That is the whole registration — no tool list, no
  export.
- Docstrings follow `github_issue_edit` (`server.py:1203-1245`): one-line
  summary, a short paragraph, then `Args:` with every parameter and `Returns:`
  describing the success line and "or error message string". State in each
  docstring that both numbers live in the **same** repository and that
  `reference_name` scopes both.
- **Lazy imports inside the function bodies only** — PyGithub must stay off the
  server startup path:
  `from mcp_workspace.github_operations.issues.sub_issues_mixin import sub_issue_total`
  inside `_subissue_write`. `_api_error` needs no import (it duck-types `.data`).
- Every returned error string appends `_ref_suffix(reference_name)`
  (`server.py:84`) — **except** the reference-resolution failure. Build the
  manager *before* the main `try`, in its own `except ValueError` that returns a
  bare `f"Error: {exc}"`. An unknown reference name must return exactly
  `Error: Reference project 'nope' not found`, byte-identical to every other
  issue tool; routing that message through `_api_error` would append
  `_ref_suffix` and double the project name.
- Repository inaccessible: the mixin returns `None`, and the tool returns the
  existing `_repo_access_error(manager)` (`server.py:833`), as `github_search`
  does at `server.py:1094-1095`.
- `except (GithubException, ValueError) as exc: return _api_error(exc, reference_name)`
  — Decision 16 exactly. `IssueIdentityMismatchError` and the PR guard are
  `ValueError`s, so both are covered; a programming error (`AttributeError`,
  `TypeError`) still raises instead of being rendered as a caller-facing
  `Error: ...`. Import `GithubException` lazily inside the function body, as
  `github_issue_edit` does (`server.py:1247`).
- `vulture_whitelist.py`: add `_.github_subissue_add`, `_.github_subissue_list`,
  `_.github_subissue_remove` to the existing write-tools block.

## ALGORITHM

```
_api_error(exc, reference_name):
    data = getattr(exc, "data", None)
    message = data.get("message") if isinstance(data, dict) else None
    return f"Error: {message or exc}{_ref_suffix(reference_name)}"

_subissue_write(parent_number, child_number, unlink, reference_name):
    suffix = _ref_suffix(reference_name)
    for n in (parent_number, child_number):
        if n <= 0: return f"Error: invalid issue number: {n}{suffix}"
    if parent_number == child_number:
        return f"Error: an issue cannot be its own sub-issue{suffix}"
    try:                                    # no _ref_suffix here: the message
        manager = _issue_manager(reference_name)   # already names the project
    except ValueError as exc:
        return f"Error: {exc}"
    try:
        call = manager.remove_sub_issue if unlink else manager.add_sub_issue
        parent = call(parent_number, child_number)
        if parent is None: return _repo_access_error(manager)
        total = sub_issue_total(parent)
        count = "" if total is None else f" ({total} sub-issues)"
        verb = "Unlinked" if unlink else "Linked"
        relation = "from" if unlink else "as a sub-issue of"
        return (f"{verb} #{child_number} {relation} #{parent_number} "
                f"— {parent.html_url}{count}")
    except (GithubException, ValueError) as exc:
        return _api_error(exc, reference_name)

github_subissue_list(parent_number, max_results, reference_name):
    if parent_number <= 0:
        return f"Error: invalid issue number: {parent_number}{_ref_suffix(reference_name)}"
    try:
        manager = _issue_manager(reference_name)
    except ValueError as exc:
        return f"Error: {exc}"
    try:
        children = manager.list_sub_issues(parent_number, max_results=max_results)
        if children is None: return _repo_access_error(manager)
        if not children: return "No sub-issues."
        return "\n".join(f"#{c.number}  {c.state}  {c.title}" for c in children)
    except (GithubException, ValueError) as exc:
        return _api_error(exc, reference_name)
```

Note the em dash and the two spaces in the list line — the formats in summary.md
are exact.

## DATA

Every tool returns a single `str`, success or error; nothing raises out of a
tool. Success and error formats are listed under "Output formats" in summary.md.
`max_results` is clamped inside the mixin (`max(0, ...)` before `islice`), so the
tool passes it through untouched.

## Tests (write first)

`tests/github_operations/test_github_write_tools_subissues.py`, modelled on
`tests/github_operations/test_github_write_tools_issue_edit.py`: reuse its
`setup_server` autouse fixture (`set_project_dir(project_dir)`), patch
`mcp_workspace.github_operations.issues.IssueManager` with a `MagicMock`, and
add a local `_make_parent(total=...)` helper returning a mock parent with
`html_url` set and `sub_issues_summary` either a stub with `total` or a real
`None`. Three classes, one per tool.

`github_subissue_add`:

1. Success with a summary → exact string
   `Linked #7 as a sub-issue of #3 — <url> (2 sub-issues)`.
2. Success with `sub_issues_summary` set to a real `None` → the same line with
   **no** parenthetical, and assert `(0 sub-issues)` is absent.
3. `parent_number=0` and `child_number=-1` → `Error: invalid issue number: ...`,
   and assert the manager's write method was never called.
4. `parent_number == child_number` → `Error: an issue cannot be its own sub-issue`.
5. Mixin returns `None` → the `Could not access repository` text.
6. `GithubException(422, {"message": "Issue may not contain duplicate sub-issues and Sub issue may only have one parent"})`
   → `Error: Issue may not contain duplicate sub-issues and Sub issue may only have one parent`.
7. `GithubException(404, {"message": "Not Found"})` → `Error: Not Found`.
8. `GithubException` whose `data` is a **string**, and one whose dict has no
   `message` key → falls back to `str(exc)`, no `TypeError`/`KeyError`.
9. `ValueError("#7 is a pull request, not an issue")` from the mixin →
   `Error: #7 is a pull request, not an issue`.
10. `IssueIdentityMismatchError` (import from
    `mcp_workspace.github_operations.base_manager`) → rendered as `Error: ...`,
    never a traceback.
11. An error with `reference_name="sibling"` → the message ends with
    `in reference project 'sibling'`. First configure `sibling` with
    `set_reference_projects({"sibling": ReferenceProject(name="sibling",
    path=Path("/does/not/exist"), url="https://github.com/owner/sibling")})`
    and reset it with `set_reference_projects({})` afterwards, as the
    `reference_projects` fixture in `test_github_write_tools_reference.py`
    does. Without that, `_issue_manager` returns the "not found" error and the
    call never reaches the `_api_error` suffix.
12. `reference_name="nope"` (not a configured project) → exactly
    `Error: Reference project 'nope' not found`, with **no** ref suffix
    appended, and the manager class never constructed.

`github_subissue_remove`: success line
`Unlinked #7 from #3 — <url> (1 sub-issues)`, the real-`None` summary case, the
self-link and invalid-number guards, and a 404 on an unlinked child surfacing as
`Error: <message>` rather than a success (Decision 9 — no silent no-op).

`github_subissue_list`: two children → two `#<n>  <state>  <title>` lines in
order; `[]` → `No sub-issues.`; `None` → repository error; `parent_number=0` →
invalid-number error; `max_results` is forwarded to the mixin
(`assert_called_once_with(3, max_results=5)`).

**`reference_name` routing**, in the existing
`tests/github_operations/test_github_write_tools_reference.py`: import the three
tools and extend the parametrised table around line 100:

```python
_TOOL_CASES = [
    (github_label_list, {}),
    (github_issue_comment, {"number": 42, "body": "hi"}),
    (github_issue_create, {"title": "T"}),
    (github_issue_edit, {"number": 42, "title": "T"}),
    (github_subissue_add, {"parent_number": 42, "child_number": 43}),
    (github_subissue_list, {"parent_number": 42}),
    (github_subissue_remove, {"parent_number": 42, "child_number": 43}),
]
_TOOL_IDS = [
    "label_list", "issue_comment", "issue_create", "issue_edit",
    "subissue_add", "subissue_list", "subissue_remove",
]
```

- **Three** parametrised tests consume that table, not two:
  `test_reference_name_uses_repo_url`, `test_no_reference_name_uses_project_dir`
  and `test_unknown_reference_name_returns_error`
  (`test_github_write_tools_reference.py:143`). The last one asserts the exact
  string `Error: Reference project 'nope' not found` and
  `mock_manager_cls.assert_not_called()` — which is why `_issue_manager` is
  resolved outside the `_api_error` path above. If that test fails for the new
  cases, the fix belongs in `server.py`, not in the assertion.
- Use distinct parent and child numbers (42/43): equal numbers would hit the
  self-link guard and return before `IssueManager` is constructed, so the
  routing assertion would fail for the wrong reason.
- The file's local `_make_manager()` returns a `MagicMock`, so
  `add_sub_issue`/`list_sub_issues` auto-return Mocks and the tools render a
  harmless Mock repr. The first two tests assert only how `IssueManager` was
  constructed, so no new fixture or stub return value is needed.

## Checks

`run_format_code`, then pylint, pytest `-n auto`, mypy, vulture, ruff,
lint-imports. Vulture fails without the three whitelist entries.

## Commit

`feat(server): add github_subissue_add/_list/_remove tools (#294)`

## LLM prompt

> Implement Step 2 of the sub-issue tools feature for issue #294. Step 1 is
> already committed.
> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md` in full first.
> Work test-first: write `tests/github_operations/test_github_write_tools_subissues.py`
> covering every case listed in step_2, add the three tools to `_TOOL_CASES` /
> `_TOOL_IDS` in `tests/github_operations/test_github_write_tools_reference.py`,
> then add `_api_error`, `_subissue_write` and the three `@mcp.tool()` functions
> to `src/mcp_workspace/server.py` immediately after `github_issue_edit`, and add
> the three tool names to `vulture_whitelist.py`.
> Match the success and error formats in summary.md exactly, including the em
> dashes, the two spaces in the list line, and the `_ref_suffix` on every error
> except the reference-resolution failure, which must stay byte-identical to the
> other issue tools (`Error: Reference project 'nope' not found`).
> Catch `(GithubException, ValueError)`, not bare `Exception`.
> Keep PyGithub imports lazy (inside function bodies).
> Then run `run_format_code` followed by pylint, pytest (`extra_args=["-n","auto"]`),
> mypy, vulture, ruff and lint-imports, fix anything they report, and make one
> commit.
