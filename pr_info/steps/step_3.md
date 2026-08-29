# Step 3 — `github_issue_create` tool (+ shared helpers)

## Prompt for LLM

> Read `pr_info/steps/summary.md` (especially "§2 Lazy imports", "§3 Write
> failures", "§5 Two guards in the tool layer"), then implement this step
> (`pr_info/steps/step_3.md`) only. Follow TDD: write the tests first, watch them
> fail, then implement. Use MCP tools for all file and check operations.
> One commit at the end.

Depends on step 1 (`create_issue` must accept `assignees`).

---

## WHERE

- `src/mcp_workspace/server.py` — two module-private helpers placed next to
  `_check_not_gitignored` (line ~60), and the tool placed after `github_search`
  (line ~838), keeping the `github_*` tools contiguous
- `vulture_whitelist.py` — new "GitHub write tools" section
- `tests/github_operations/test_github_write_tools.py` — **new file**

## WHAT

```python
_STATUS_LABEL_PREFIX = "status-"
_login_cache: Dict[str, str] = {}


def _check_labels(manager: Any, add: List[str], remove: List[str]) -> Optional[str]:
    """Reject status-* labels on both sides, then unknown add-side names.

    Returns an error string, or None when the labels are acceptable.
    """


def _resolve_assignees(manager: Any, logins: List[str]) -> List[str]:
    """Resolve '@me' to the authenticated login, cached per process."""


@mcp.tool()
@log_function_call
def github_issue_create(
    title: str,
    body: str = "",
    labels: Optional[List[str]] = None,
    assignees: Optional[List[str]] = None,
) -> str:
```

## HOW

- **`manager: Any`, not `IssueManager`.** A real annotation would force a
  top-level `github_operations` import and break
  `tests/test_startup_performance.py`. The `IssueManager` import stays inside the
  tool body, like every existing `github_*` tool.
- `_check_labels` runs the status guard **before** the existence check, so a
  status label never costs an API call. `get_available_labels()` is called only
  when `add` is non-empty, and its result is **not cached** — the server can run
  for days and a label created meanwhile must not be wrongly rejected.
- `_resolve_assignees` resolves through `manager._github_client.get_user().login`
  (needs `# pylint: disable=protected-access`, precedent at `server.py:695,778,799`).
  Not `base_manager.get_authenticated_username()`, which re-reads the token via
  `get_github_token()` and would ignore a token passed explicitly to the manager.
- The cache is a module-level **dict**, not a global rebound with `global` —
  avoids pylint's `global-statement` and makes `_login_cache.clear()` the whole
  test reset.
- The tool docstring must state plainly that it **creates a real GitHub issue**.
- `vulture_whitelist.py`: add `_.github_issue_create` under a new
  `# GitHub write tools registered in server.py` heading, below the existing
  read-tool block. The two helpers are called, so they need no entry.

## ALGORITHM

`_check_labels`:

```
offenders = [n for n in (*add, *remove) if n.startswith(_STATUS_LABEL_PREFIX)]
if offenders: return "Error: these tools do not modify status-* labels (<names>). Use: mcp-coder gh-tool set-status <label>"
if not add: return None
known = {label["name"] for label in manager.get_available_labels()}
unknown = [n for n in add if n not in known]
return f"Error: unknown label(s): {', '.join(unknown)}" if unknown else None
```

`_resolve_assignees`:

```
if "@me" in logins and "login" not in _login_cache:
    _login_cache["login"] = manager._github_client.get_user().login
return [_login_cache["login"] if x == "@me" else x for x in logins]
```

`github_issue_create`:

```
lazy import IssueManager
try:
    manager = IssueManager(project_dir=_project_dir)
    err = _check_labels(manager, labels or [], []);  if err: return err
    resolved = _resolve_assignees(manager, assignees or [])
    issue = manager.create_issue(title=title, body=body, labels=labels, assignees=resolved or None)
    if not issue["number"]: return "Error: issue creation failed - no issue was created"
    return f"Created issue #{issue['number']} — {issue['url']}"
except Exception as e: return f"Error: {e}"
```

## DATA

- Success: `Created issue #42 — https://github.com/o/r/issues/42`
- Failure: `Error: <reason>`
- `_check_labels` → `Optional[str]`; `_resolve_assignees` → `List[str]`

`body` is taken **inline** — no `--body-file`, no tempfile.

## Tests (TDD)

New `tests/github_operations/test_github_write_tools.py`. Mirror
`test_github_read_tools_issues.py`: an autouse `setup_server` fixture calling
`set_project_dir(project_dir)`, and `@patch("mcp_workspace.github_operations.issues.IssueManager")`.
Add an autouse fixture clearing `server_module._login_cache`.

1. Happy path — first line is `Created issue #42 — <url>`; `create_issue`
   received `title`/`body`.
2. Sentinel — `create_issue` returns `create_empty_issue_data()` → result starts
   with `Error:` and does **not** contain `Created`.
3. Exception → `Error: <msg>`.
4. Status label rejected — `labels=["status-01:created"]` returns an error
   naming the label and `set-status`; `create_issue` never called; and
   `get_available_labels` never called (guard runs first).
5. Unknown label rejected — `get_available_labels` returns `bug` only,
   `labels=["bugg"]` → error naming `bugg`; `create_issue` never called.
6. Known label accepted — passes through to `create_issue`.
7. No labels → `get_available_labels` never called.
8. `assignees=["@me"]` → resolved to the mocked login before reaching
   `create_issue`.
9. `@me` cache — two calls, `get_user` invoked once.
10. `assignees=["alice"]` → `get_user` never called.

## Checks

`run_pylint_check`, `run_mypy_check`, `run_pytest_check`, `run_vulture_check`.

## Commit

`Add github_issue_create MCP tool`
