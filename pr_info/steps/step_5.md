# Step 5 — Server helper `_resolve_base_branch` + `get_base_branch`

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_5.md`). Implement
> step 5 only: tests first, then add `_resolve_base_branch` to `server.py` and rewrite
> `get_base_branch` on top of it. Run pylint, pytest (`-n auto`) and mypy until green, run
> `run_format_code`, then make one commit.

## WHERE

- `src/mcp_workspace/server.py`
- `tests/test_server_get_base_branch.py` (new)

## WHAT

```python
def _resolve_base_branch(
    project_dir: Path, branch: str, pr_manager: Any
) -> tuple[Optional[str], Optional[str]]:
    """Resolve the base branch for ``branch`` from its issue, PR, merge-base or default.

    Returns:
        (base, None) — base may be None when detection found nothing — or
        (None, "Error: issue #N: <sentence>") when the issue's Base Branch section
        is malformed. Never falls back past a malformed section.
    """

@mcp.tool()
@log_function_call
def get_base_branch() -> str: ...   # signature unchanged
```

## HOW

- Lazy imports inside `_resolve_base_branch` (keep PyGithub/GitPython off startup):
  ```python
  from mcp_workspace.git_operations.base_branch import detect_base_branch
  from mcp_workspace.git_operations.branch_queries import extract_issue_number_from_branch
  from mcp_workspace.github_operations import IssueIdentityMismatchError
  from mcp_workspace.github_operations.issues import IssueManager
  ```
  Tests patch these at their source modules.
- `detect_base_branch` is called **without** `issue_manager` (it defaults to `None`; step 6
  removes the parameter), so it cannot re-fetch the issue.
- `IssueIdentityMismatchError` is caught **before** the broad `except Exception` (it is a
  `ValueError` subclass), logged at WARNING; everything else at DEBUG.
- `get_base_branch`:
  - builds only `PullRequestManager(_project_dir)` in its existing try (failure → `None`);
  - `branch = get_current_branch_name(_project_dir)`; `None` → `"main"` (as today);
  - `base, error = _resolve_base_branch(...)`; `error` → return it; `base is None` → `"main"`;
  - keeps the outer `except Exception` → `"main"` for unexpected failures.
- Docstring of `get_base_branch`:
  `Returns: Branch name string; "Error: issue #N: …" when the linked issue's Base Branch section is malformed (no fallback); "main" when nothing could be detected.`

## ALGORITHM (`_resolve_base_branch`)

```
issue_data = None; number = extract_issue_number_from_branch(branch)
if number is not None:
    try: fetched = IssueManager(project_dir=project_dir).get_issue(number)
         issue_data = fetched if fetched.get("number", 0) > 0 else None
    except IssueIdentityMismatchError as e: logger.warning("%s", e)
    except Exception: logger.debug("Issue fetch for base branch failed", exc_info=True)
if issue_data and issue_data.get("base_branch_error"):
    return None, f"Error: issue #{number}: {issue_data['base_branch_error']}"
return detect_base_branch(project_dir, current_branch=branch,
                          issue_data=issue_data, pr_manager=pr_manager), None
```

## DATA

`tuple[Optional[str], Optional[str]]` = `(base, error)`; exactly one of the two is meaningful.

## Tests (new file, write first)

`_resolve_base_branch`:
- malformed issue → `(None, "Error: issue #42: <sentence>")`; `detect_base_branch` not called.
- valid issue → `detect_base_branch` called once with `issue_data=<fetched>`; result returned.
- branch without issue number → no `IssueManager` call; `issue_data=None` passed.
- `IssueManager(...)` raises → falls through with `issue_data=None`.
- `get_issue` raises `IssueIdentityMismatchError` → WARNING logged, falls through.
- `get_issue` returns `number == 0` → falls through with `issue_data=None`.
- `get_issue` called exactly once in every path.

`get_base_branch`:
- malformed → returns the `Error: issue #N: …` string.
- valid → returns the detected branch.
- detection `None` → `"main"`.
