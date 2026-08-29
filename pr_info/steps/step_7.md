# Step 7 — `github_pr_create` tool

## Prompt for LLM

> Read `pr_info/steps/summary.md` (especially "§6 `create_pull_request`'s
> contract is left alone"), then implement this step (`pr_info/steps/step_7.md`)
> only. Follow TDD: write the tests first, watch them fail, then implement.
> Use MCP tools for all file and check operations. One commit at the end.

Independent of steps 3–6.

---

## WHERE

- `src/mcp_workspace/server.py` — after `github_label_list`
- `vulture_whitelist.py` — `_.github_pr_create`
- `tests/github_operations/test_github_write_tools_labels_pr.py` — new test
  class, shared with step 6 (create the file if step 6 has not landed yet)

## WHAT

```python
@mcp.tool()
@log_function_call
def github_pr_create(
    title: str,
    body: str = "",
    head: Optional[str] = None,
    base: Optional[str] = None,
) -> str:
```

## HOW

- **`pr_manager.py` is not modified.** `create_pull_request` returns `{}` for
  empty title, bad branch name and unresolvable default branch, with the reason
  only logged. Changing that contract would flip ~8 existing tests and widen this
  issue's scope. The tool pre-validates instead.
- Branch-name rules are **not restated** — call
  `PullRequestManager._validate_branch_name` (`# pylint: disable=protected-access`;
  `server.py:695` already reaches for a protected manager member).
- `head` defaults to `git_operations.get_current_branch_name(_project_dir)`:
  `create_pull_request` takes `head_branch` as a required positional, so the tool
  must supply it.
- `base` defaults to `git_operations.get_default_branch_name(_project_dir)` —
  the same function `create_pull_request` calls internally, so resolving it here
  changes nothing but makes `head != base` always checkable and leaves one code
  path instead of two. Issues carry a `### Base Branch` section, so `main` is not
  always right, and making the caller restate two facts the server already holds
  is where mistakes get introduced.
- `head != base` is checked because neither the library nor GitHub gives a clear
  message for that one.
- **Sentinel differs again:** `create_pull_request` returns `{}`, so the check is
  `not pr.get("number")`, not `pr["number"] == 0`.
- Docstring must state plainly that it **opens a real pull request**.
- `vulture_whitelist.py`: `_.github_pr_create`.

## ALGORITHM

```
lazy import PullRequestManager, get_current_branch_name, get_default_branch_name
try:
    if not title.strip(): return "Error: PR title cannot be empty"
    manager = PullRequestManager(project_dir=_project_dir)
    head = head or get_current_branch_name(_project_dir)
    base = base or get_default_branch_name(_project_dir)
    if not head: return "Error: could not determine the current branch for head"
    if not base: return "Error: could not determine the repository default branch for base"
    if head == base: return f"Error: head and base are the same branch ({head})"
    for name in (head, base):
        if not manager._validate_branch_name(name): return f"Error: invalid branch name: {name}"
    pr = manager.create_pull_request(title=title, head_branch=head, base_branch=base, body=body)
    if not pr.get("number"): return "Error: PR creation failed - no pull request was created"
    return f"Created PR #{pr['number']} — {pr['url']}"
except Exception as e: return f"Error: {e}"
```

`PullRequestManager(project_dir=None)` raises `ValueError`, caught by the
`except`, so no separate `_project_dir` guard is needed.

## DATA

- Success: `Created PR #7 — https://github.com/o/r/pull/7`
- Failure: `Error: <reason>`

`milestone` and `draft` are deliberately not exposed — no usage evidence for
either.

## Tests (TDD)

New class in `tests/github_operations/test_github_write_tools_labels_pr.py`,
patching
`mcp_workspace.github_operations.pr_manager.PullRequestManager` and the two
`git_operations` branch helpers at their `mcp_workspace.git_operations` import
site:

1. Happy path — `Created PR #7 — <url>`; `create_pull_request` received the
   resolved `head_branch` and `base_branch`.
2. `head` omitted → current branch used.
3. `base` omitted → default branch used.
4. Both supplied → neither resolver called.
5. Empty / whitespace title → `Error:`; `create_pull_request` never called.
6. `head == base` → `Error:` naming the branch; `create_pull_request` never called.
7. Invalid branch name (e.g. `feat~1`) → `Error:`; `create_pull_request` never
   called, and the rejection demonstrably came from `_validate_branch_name`.

   **The manager is patched, so `manager._validate_branch_name(...)` returns a
   truthy `MagicMock` and the rejection is unreachable unless the test wires it
   up.** Give the mock the real implementation:

   ```python
   from mcp_workspace.github_operations.pr_manager import PullRequestManager
   mock_manager_cls.return_value._validate_branch_name.side_effect = (
       lambda name: PullRequestManager._validate_branch_name(None, name)  # pylint: disable=protected-access
   )
   ```

   The real method touches no instance state, so passing `None` as `self` is
   safe — and it keeps the branch-name rules in one place, which is the whole
   reason the tool calls the library validator instead of restating them. Assert
   both that the result is an `Error:` naming the branch and that
   `_validate_branch_name` was called with it.

7b. Valid branch names pass the same wired validator — the happy-path test uses
   the same `side_effect` so a rule change in the library cannot leave these
   tests green against a tool that rejects everything.
8. `get_current_branch_name` returns `None` → `Error:`.
9. `get_default_branch_name` returns `None` → `Error:`.
10. Sentinel — `create_pull_request` returns `{}` → `Error:`, not `Created PR`.
11. `ValueError` from the manager constructor → `Error: <msg>`.

## Checks

`run_pylint_check`, `run_mypy_check`, `run_pytest_check`, `run_vulture_check`.

## Commit

`Add github_pr_create MCP tool`
