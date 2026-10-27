# Step 1 — `github_pr_create` uses `probe_origin_branch`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_1.md` exactly.
> Tests first, then code. Run format, pylint, pytest (`-n auto`), mypy and lint-imports;
> all must pass. Make one commit: `refactor(server): verify PR base via probe_origin_branch (#355)`.

## WHERE

- `src/mcp_workspace/server.py` — `github_pr_create` (~line 1931–1957)
- `tests/github_operations/test_github_pr_create_base.py`
- `tests/github_operations/test_github_write_tools_labels_pr.py` (~line 226–233, autouse fixture)

## WHAT

No signature changes. `github_pr_create(...) -> str` replaces its use of
`origin_has_branch` with `probe_origin_branch(project_dir, base) -> BranchProbe`.

## HOW

- Replace the lazy import
  `from mcp_workspace.git_operations.base_branch import origin_has_branch`
  with `from mcp_workspace.git_operations import probe_origin_branch`. It goes next to the
  existing `get_current_branch_name` import. Do **not** import via `base_branch`: that trips
  mypy `no_implicit_reexport`.
- Keep the existing `try: ... except Exception as e:` around the single call, with the same
  pylint disable. `server.py` may not import `git.exc` (`gitpython_isolation`).
- `origin_has_branch` itself stays until step 2. Do not touch `base_branch.py`.

## ALGORITHM

```
try:
    probe = probe_origin_branch(project_dir, base)
except Exception as e:                      # existing broad catch, scoped to the call
    return f"Error: could not verify base branch '{base}' on origin: {e}"
if probe["exists"] is None:
    return f"Error: could not verify base branch '{base}' on origin: {probe['stderr'] or probe['error']}"
if not probe["exists"]:
    return f"Error: base branch '{base}' not found on origin"
```

## DATA

`BranchProbe` (from `git_operations.core`): `success`, `error`, `returncode`, `stderr`,
`exists: Optional[bool]`. Test helper (in each test file, or inline):

```python
def _probe(exists, stderr=None, error=None):
    return {"success": exists is not None, "error": error, "returncode": 0 if exists is not None else 128,
            "stderr": stderr, "exists": exists}
```

## Tests (write first)

`test_github_pr_create_base.py`:
- Replace `ORIGIN_HAS_BRANCH` with `PROBE_ORIGIN = "mcp_workspace.git_operations.probe_origin_branch"`.
- `return_value=True` → `return_value=_probe(True)`; `return_value=False` → `_probe(False)`.
  `test_base_missing_on_origin_returns_error` keeps `assert_called_once_with(project_dir, "epic/x")`.
- `test_origin_check_failure_returns_error`: replace the `exc` parametrization with two cases:
  - returned probe `_probe(None, stderr="boom", error="git ls-remote failed (exit 128)")`
    (`return_value=`)
  - `side_effect=OSError("boom")`

  Both assert the `"Error: could not verify base branch 'epic/x' on origin: "` prefix,
  `"boom"` in the result, and no PR created. Drop the now-unused `GitCommandError` import if
  nothing else uses it.

`test_github_write_tools_labels_pr.py`:
- In the autouse fixture `origin_has_base`, change the patch target to
  `"mcp_workspace.git_operations.probe_origin_branch"` and the return value to a probe dict
  with `exists=True`. Keep the fixture name; only the target and value change.
