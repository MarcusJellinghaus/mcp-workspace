# Step 3 — Single protection fetch; Administration probe classifies the shared outcome

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_3.md`. Use TDD: update the tests first, then the code. Run pylint, pytest (`-n auto`) and mypy until all three pass, then produce one commit.

## WHERE

- `src/mcp_workspace/github_operations/_types.py`
- `src/mcp_workspace/github_operations/_permission_probes.py`
- `src/mcp_workspace/github_operations/verification.py`
- `tests/github_operations/test_permission_probes.py`
- `tests/github_operations/test_verification.py`

## WHAT

`_types.py`:

```python
class ProtectionOutcome(NamedTuple):
    """Result of the single branch-protection fetch in verify_github."""
    branch: str | None                                 # None if get_default_branch failed
    stage: Literal["get_branch", "get_protection"]     # step that ran last
    protection: BranchProtection | None                # set on success
    exception: Exception | None                        # None on success
```

`_permission_probes.py`:

```python
def _is_branch_not_protected(exc: Exception | None) -> bool: ...
def _classify_exception(exc: Exception, name: str, url: str, web_host: str | None) -> CheckResult: ...
def _probe_administration(outcome: ProtectionOutcome, base: str, web_host: str | None) -> CheckResult: ...
def run_permission_probes(
    manager: BaseGitHubManager,
    repo: Repository | None,
    *,
    protection_outcome: ProtectionOutcome | None,
) -> dict[str, CheckResult]: ...
```

`verification.py`:

```python
def _fetch_protection(manager: BaseGitHubManager, repo: Repository) -> ProtectionOutcome: ...
```

## HOW

- `_run_probe`'s two `except` bodies become one call: `except Exception as e: return _classify_exception(e, name, url, web_host)`.
- `verify_github`:
  - When the repo is accessible, it calls `outcome = _fetch_protection(manager, repo)`. Otherwise `outcome = None`.
  - The branch-protection block reads `outcome`. On success it uses today's 200 path, with `outcome.branch` and `outcome.protection`. On failure it keeps today's `ok=False, "not configured"` rows until step 4.
  - It passes `protection_outcome=outcome` to `run_permission_probes`.
- `run_permission_probes` still uses `repo.default_branch` for the statuses probe. It passes the outcome to `_probe_administration`.
- `verification.py` imports `ProtectionOutcome` from `_types`.

## ALGORITHM

```
_fetch_protection:
    branch_name = None
    try: branch_name = manager.get_default_branch(); branch = repo.get_branch(branch_name)
    except Exception as exc: log debug; return Outcome(branch_name, "get_branch", None, exc)
    try: return Outcome(branch_name, "get_protection", branch.get_protection(), None)
    except Exception as exc: log debug (status, data, extract_diagnostic_headers); return Outcome(branch_name, "get_protection", None, exc)

_probe_administration:
    if outcome.stage == "get_branch": return not-checked row (ok=None, existing error text)
    if outcome.exception is None or _is_branch_not_protected(outcome.exception): return ok=True, "OK"
    return _classify_exception(outcome.exception, "Administration: Read", url, web_host)

_is_branch_not_protected:
    isinstance(exc, GithubException) and exc.status == 404
        and isinstance(exc.data, dict) and exc.data.get("message") == "Branch not protected"
```

The URL is `f"{base}/branches/{outcome.branch}/protection"`.

## DATA

The result dict's keys and row shapes are unchanged. `get_protection()` is called exactly once per `verify_github` run.

## Tests (write first)

`test_permission_probes.py`:
- Add a helper `_outcome(exc=None, *, stage="get_protection", branch="main")`.
  - Pass `protection_outcome=_outcome()` to every `run_permission_probes(manager, repo)` call.
  - Pass `protection_outcome=None` to the calls where `repo is None`.
- Rewrite `TestAdministrationTwoCallAttribution` against `_probe_administration(outcome, base, host)`, parametrized:
  - stage `get_branch`: `ok is None`, `not checked`, existing error text, no `GET`
  - success: `ok is True`
  - `Branch not protected` 404: `ok is True`
  - 403: `ok is False`, new 403 wording
  - a 404 with a different message: `ok is False`, generic 404 text
- `TestUrlTemplates`: the Administration row comes from `_outcome(exc_404, branch="trunk")`. Remove the `get_branch` / `get_protection` mocks.
- Add a test asserting that `run_permission_probes` never calls `repo.get_branch`.

`test_verification.py`:
- New `TestSingleProtectionFetch`: `_patch_all_ok`, then `mock_branch.get_protection.call_count == 1`. Return the mocks, or make a variant of the helper that does. Add a second case where `get_protection` raises 403.
- `TestPermissionProbeOverallOkUnaffected`: unchanged. The Administration probe still reports `ok=False` on a 403.
