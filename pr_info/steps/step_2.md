# Step 2 — `_permission_probes.py` module + `verify_github` integration

**Goal:** Add the 6 per-permission read probes to `verify_github`. New module owns probe logic + classifier + orchestrator; `verification.py` integration is one call.

This step depends on Step 1 (`web_host` property must exist).

## WHERE

**Create:**
- `src/mcp_workspace/github_operations/_permission_probes.py`
- `tests/github_operations/test_permission_probes.py`

**Modify:**
- `src/mcp_workspace/github_operations/verification.py` — call `run_permission_probes(manager, repo)` once, before `overall_ok` calculation.
- `tests/github_operations/test_verification.py` — integration tests (key ordering, `overall_ok` unaffected, skip-when-unreachable shape).

## WHAT

### Module-level constants

```python
_PROBE_KEYS: tuple[str, ...] = (
    "perm_contents_read",
    "perm_administration_read",
    "perm_pull_requests_read",
    "perm_issues_read",
    "perm_workflows_read",
    "perm_statuses_read",
)
```

### Public function

```python
def run_permission_probes(
    manager: BaseGitHubManager,
    repo: Repository | None,
) -> dict[str, CheckResult]:
    """Run 6 per-permission read probes; return one CheckResult per probe key.

    When `repo` is None (repo_accessible.ok=False), returns 6 placeholder rows
    with value="not checked", error="repository not accessible" and issues NO
    PyGithub calls.
    """
```

### Private helpers

```python
def _classify_permission_response(
    name: str,            # e.g. "Contents: Read"
    status: int,          # 200 / 401 / 403 / 404 / other
    url: str,             # full probed URL incl. query string
    web_host: str | None, # from RepoIdentifier.web_host
    *,
    admin_404: bool = False,  # True only for perm_administration_read
) -> CheckResult: ...

def _run_probe(
    *,
    call: Callable[[], object],  # the PyGithub call; for lazy probes, the lambda reads .totalCount
    name: str,
    url: str,
    web_host: str | None,
    admin_404: bool = False,
) -> CheckResult: ...

def _probe_statuses(
    repo: Repository,
    default_branch: str,
    base: str,            # f"{api_base_url}/repos/{full_name}"
    web_host: str | None,
) -> CheckResult: ...
```

## HOW

### Circular-import handling

`_permission_probes.py` imports `CheckResult` from `verification.py`; `verification.py` imports `run_permission_probes` from `_permission_probes.py`. To resolve:

- In `verification.py`, the `class CheckResult` definition stays where it is (early in the file). The import of `run_permission_probes` must be placed **after** the `CheckResult` class definition.
- Module-level top-to-bottom execution then resolves cleanly: when `_permission_probes` is loaded, `CheckResult` is already defined on the partially-loaded `verification` module.

### Integration in `verify_github`

After the existing `auto_delete_branches` block and before the `overall_ok` calculation, insert:

```python
result.update(run_permission_probes(manager, repo if repo_is_ok else None))
```

(Pass `manager` even when `repo` is None — orchestrator handles the placeholder branch and never dereferences `manager` in that case. Or pass `manager=None` too; pick one shape and keep it consistent.)

> **Decision:** pass `repo=None` when unreachable; `manager` is still passed but unused on that path. This keeps the orchestrator signature stable.

### Probe data table

Inside `run_permission_probes`, after the `repo is None` early return:

```python
identifier = manager._repo_identifier
base = f"{identifier.api_base_url}/repos/{identifier.full_name}"
web_host = identifier.web_host
default = repo.default_branch
```

Then run the 5 simple probes via `_run_probe(...)` with these tuples:

| key | name | url | call (lambda) | admin_404 |
|---|---|---|---|---|
| `perm_contents_read` | `Contents: Read` | `f"{base}/contents/"` | `lambda: repo.get_contents("")` | False |
| `perm_administration_read` | `Administration: Read` | `f"{base}/branches/{default}/protection"` | `lambda: repo.get_branch(default).get_protection()` | **True** |
| `perm_pull_requests_read` | `Pull requests: Read` | `f"{base}/pulls?state=all"` | `lambda: repo.get_pulls(state="all").totalCount` | False |
| `perm_issues_read` | `Issues: Read` | `f"{base}/issues?state=all"` | `lambda: repo.get_issues(state="all").totalCount` | False |
| `perm_workflows_read` | `Actions: Read` | `f"{base}/actions/workflows"` | `lambda: repo.get_workflows().totalCount` | False |

Then `out["perm_statuses_read"] = _probe_statuses(repo, default, base, web_host)`.

## ALGORITHM

### `_classify_permission_response` (pure function)

```text
if status == 200:
    return CheckResult(ok=True, value="OK", severity="warning")

suffix = f" (GET {url})"
if status == 401:
    err = f"token rejected (401) — needs {name}{suffix}"
elif status == 403:
    err = f"blocked by org policy (403) — needs {name}{suffix}"
elif status == 404:
    if admin_404:
        err = f"missing permission {name} OR no branch protection configured (404){suffix}"
    elif web_host is not None:  # github.com or *.ghe.com
        err = (
            f"missing permission {name} OR awaiting org approval "
            f"(404 — fine-grained PATs return 404 for ungranted resources; "
            f"check token at {web_host}/settings/personal-access-tokens){suffix}"
        )
    else:  # GHES
        err = f"missing permission {name} OR resource not found (404){suffix}"
else:
    err = f"unexpected status {status} — needs {name}{suffix}"
return CheckResult(ok=False, value="failed", severity="warning", error=err)
```

### `_run_probe`

```text
try:
    call()
    return _classify_permission_response(name, 200, url, web_host, admin_404=admin_404)
except GithubException as e:
    return _classify_permission_response(name, e.status, url, web_host, admin_404=admin_404)
except Exception as e:  # noqa: BLE001
    return CheckResult(ok=False, value="failed", severity="warning",
                       error=f"network error: {e} — needs {name}")
```

### `_probe_statuses` (two-call attribution)

```text
url = f"{base}/commits/{default_branch}/status"
try:
    commit = repo.get_commit(default_branch)
except Exception:
    return CheckResult(ok=False, value="not checked", severity="warning",
                       error="commit lookup failed (covered by perm_contents_read)")
return _run_probe(
    call=commit.get_combined_status,
    name="Commit statuses: Read",
    url=url,
    web_host=web_host,
)
```

### `run_permission_probes` (orchestrator)

```text
if repo is None:
    return {k: CheckResult(ok=False, value="not checked", severity="warning",
                            error="repository not accessible") for k in _PROBE_KEYS}
identifier = manager._repo_identifier
base = f"{identifier.api_base_url}/repos/{identifier.full_name}"
web_host = identifier.web_host
default = repo.default_branch
out: dict[str, CheckResult] = {}
for key, name, url, call, admin_404 in _PROBE_TABLE(repo, base, default):
    out[key] = _run_probe(call=call, name=name, url=url, web_host=web_host, admin_404=admin_404)
out["perm_statuses_read"] = _probe_statuses(repo, default, base, web_host)
return out
```

## DATA

- **`CheckResult` shape unchanged.** `severity="warning"` for all 6.
- **Result dict keys** (in order) appended into `verify_github` result between `auto_delete_branches` and `overall_ok`:
  - `perm_contents_read`, `perm_administration_read`, `perm_pull_requests_read`, `perm_issues_read`, `perm_workflows_read`, `perm_statuses_read`.
- **Success row:** `{ok: True, value: "OK", severity: "warning"}` — no `error` field, no URL.
- **Failure row:** `{ok: False, value: "failed", severity: "warning", error: "<msg> (GET <url>)"}`.
- **Skip row:** `{ok: False, value: "not checked", severity: "warning", error: "repository not accessible"}` (or `"commit lookup failed (covered by perm_contents_read)"` for statuses).

## Tests (TDD — write before the implementation)

### `tests/github_operations/test_permission_probes.py` (new file)

1. **Classifier — pure-function tests** (no mocks):
   - 200 → `ok=True, value="OK"`, no `error` key, no URL anywhere.
   - 401 / 403 / 404 / 500 produce the expected hint strings; assert presence of permission name, status, and `(GET <url>)`.
   - 404 host-branching: `web_host="https://github.com"` includes `settings/personal-access-tokens` URL and "fine-grained PATs return 404" phrase; `web_host="https://tenant.ghe.com"` includes the tenant URL; `web_host=None` (GHES) MUST NOT contain `settings` or `fine-grained PAT`.
   - `admin_404=True` produces `missing permission Administration: Read OR no branch protection configured (404)`.

2. **Per-probe success path** (parametrized over the 5 simple probes): mock the corresponding `repo` method, assert `ok=True, value="OK"`, no URL in any field.

3. **Per-probe failure paths** (parametrized over probe × status in {401, 403, 404, 500}): make the mock raise `GithubException(status=...)`, assert HTTP method (`GET`), full URL, and permission name all appear in `error`.

4. **`PaginatedList.totalCount` is read** — for `perm_pull_requests_read`, `perm_issues_read`, `perm_workflows_read`: configure `Mock().totalCount` as a property (e.g. via `PropertyMock`) and assert it was accessed exactly once. Without this read, the test would falsely pass.

5. **`perm_statuses_read` two-call attribution:**
   - `repo.get_commit` raises → result is `value="not checked", error="commit lookup failed (covered by perm_contents_read)"`. Assert the classifier was NOT invoked (e.g. patch `_classify_permission_response` with a sentinel that fails the test if called).
   - `repo.get_commit` succeeds, `get_combined_status` raises 404 → classifier invoked once with `name="Commit statuses: Read"`.

6. **Network error path** — call raises `ConnectionError("boom")`; result error matches `network error: boom — needs <Name>`.

7. **Skip-when-unreachable** — `run_permission_probes(manager=Mock(), repo=None)` returns 6 rows, all with `value="not checked", error="repository not accessible"`. Manager is NOT dereferenced (assert `manager._repo_identifier` was never accessed via `MagicMock` call tracking).

8. **URL templates** — assert URLs are built from `api_base_url` + `full_name` + path; never include credentials, never reach into `Github._Github__requester`.

### `tests/github_operations/test_verification.py` (additions)

9. **Result key ordering** — assert the 6 probe keys appear in `verify_github` result in the order `perm_contents_read, perm_administration_read, perm_pull_requests_read, perm_issues_read, perm_workflows_read, perm_statuses_read`, between `auto_delete_branches` and `overall_ok`.

10. **`overall_ok` unaffected** — extend the all-probes-fail scenario: when `run_permission_probes` returns 6 failed warnings but the 4 error-severity checks pass, `overall_ok=True`.

11. **Skip rows in `verify_github`** — when `repo_accessible.ok=False`, all 6 probe rows present with the placeholder shape; verify no PyGithub calls were issued by the probes (patch `run_permission_probes` and assert it was called with `repo=None`).

## Quality checks (mandatory after each edit)

```text
mcp__tools-py__run_pylint_check
mcp__tools-py__run_pytest_check  (extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])
mcp__tools-py__run_mypy_check
```

All three must pass before commit.

## Commit

Single commit with message such as:

```
verify_github: probe per-permission REST endpoints (#188)

Add six per-permission read probes (Contents, Administration, Pull requests,
Issues, Actions, Commit statuses) to verify_github. Probes reuse the existing
GitHub client and the cached Repository, build URLs statically from the API
base, and classify GithubException status into hints that name the permission,
HTTP status, and probed URL. 404 hints branch by host: github.com and
*.ghe.com show the fine-grained-PAT settings URL; GHES gets a plain
"missing permission OR resource not found" message.
```

## LLM Prompt

> Implement Step 2 as described in `pr_info/steps/step_2.md`, using `pr_info/steps/summary.md` for the overall design context. Step 1 (`RepoIdentifier.web_host`) must be merged before this step.
>
> Follow strict TDD:
>
> 1. Create `tests/github_operations/test_permission_probes.py` with the unit tests for the classifier (pure function) — start with the 200 path, then 401/403/404/500, then host-branching, then `admin_404` special case. Confirm they fail (module does not yet exist).
> 2. Create `src/mcp_workspace/github_operations/_permission_probes.py` with `_classify_permission_response` only. Confirm classifier tests pass.
> 3. Add the per-probe success/failure parametrized tests + `.totalCount` access tests + statuses two-call attribution + network error + skip-when-unreachable to `test_permission_probes.py`. Confirm they fail.
> 4. Implement `_run_probe`, `_probe_statuses`, and `run_permission_probes` in `_permission_probes.py`. Confirm probe-module tests pass.
> 5. Add the integration tests (key ordering, `overall_ok` unaffected, skip-when-unreachable shape) to `tests/github_operations/test_verification.py`. Confirm they fail.
> 6. Modify `src/mcp_workspace/github_operations/verification.py` to call `run_permission_probes(manager, repo if repo_is_ok else None)` after the `auto_delete_branches` block and before the `overall_ok` calculation. Be careful with import ordering — place `from mcp_workspace.github_operations._permission_probes import run_permission_probes` after the `class CheckResult` definition to avoid the circular-import deadlock described in step_2.md. Confirm integration tests pass.
> 7. Run the three mandatory MCP quality checks (pylint, pytest with the recommended marker exclusions, mypy) and fix any issues. Run `./tools/format_all.sh` before committing.
>
> Do NOT add the `perm_metadata_read` probe (dropped per the issue's Decision #6). Do NOT introduce a new field on `CheckResult`. Do NOT call into PyGithub internals (`Github._Github__requester`); URLs are built statically. Do NOT construct a new `Github()` client; reuse `manager._github_client` indirectly via the existing `repo` object.
