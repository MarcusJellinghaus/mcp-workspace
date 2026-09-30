# Step 4 — Branch-protection outcome table

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_4.md`. Use TDD: update the tests first, then the code. Run pylint, pytest (`-n auto`) and mypy until all three pass, then produce one commit.

## WHERE

- `src/mcp_workspace/github_operations/verification.py`
- `tests/github_operations/test_verification.py`

## WHAT

```python
def _short_reason(exc: Exception) -> str: ...
def _classify_protection_failure(outcome: ProtectionOutcome) -> tuple[bool | None, str, str]:
    """Return (ok, value, error) shared by all five branch-protection rows."""
```

## HOW

- When `outcome.exception is not None`, the branch-protection block calls `result.update(_protection_rows(*_classify_protection_failure(outcome)))`.
- The 200 path is unchanged.
- Import `_is_branch_not_protected` from `_permission_probes`. `verification.py` already imports from that module.
- Update the docstring of `verify_github` to mention `ok=None`.

## ALGORITHM

```
_short_reason(exc):
    if GithubException: msg = exc.data.get("message") if dict else None
        return f"HTTP {status}: {msg}" if str and len(msg) <= 100 else f"HTTP {status}"
    return type(exc).__name__

_classify_protection_failure(o):
    if _is_branch_not_protected(o.exception): return False, "not configured", "no branch protection"
    reason = _short_reason(o.exception); error = f"{o.stage} failed: {reason}"
    if o.stage == "get_protection" and GithubException and status == 401: return None, "not verifiable — token rejected (401)", error
    if o.stage == "get_protection" and GithubException and status == 403: return None, "not verifiable — token lacks Administration: Read", error
    return None, f"not verifiable — {reason}", error
```

## DATA

The branch-protection rows follow the table in `summary.md`. No `{` or raw JSON body appears in `value` or `error`. The body is only in the step 3 debug log.

## Tests (write first)

`test_verification.py`:
- Add a helper `_run_with_protection_error(tmp_path, exc, *, on="get_protection" | "get_branch")`. It is based on `TestNoBranchProtection404._run`.
- Add a parametrized `TestProtectionOutcomeTable`, asserting all five keys for each case:

  | case | expected `ok` | expected value |
  |---|---|---|
  | 404 `{"message": "Branch not protected"}` | `False` | `"not configured"` |
  | 404 `{"message": "Not Found"}` | `None` | starts `"not verifiable"` |
  | 401 | `None` | contains `"token rejected (401)"` |
  | 403 `{"message": "Resource not accessible by personal access token", "documentation_url": ...}` | `None` | contains `"token lacks Administration: Read"` |
  | 500 | `None` | contains `"HTTP 500"` |
  | `ConnectionError("boom")` | `None` | contains `"ConnectionError"` |
  | `get_branch` raises 404 | `None` | starts `"not verifiable"` |

- In every case, assert `"not configured"` is absent unless it is the verified 404. Assert `"{"` and `"documentation_url"` are absent from `value` and `error`. Assert `overall_ok is True`.
- Add a test for a 500 whose `message` is longer than 100 characters: the reason is exactly `HTTP 500`.
- Fold `TestNoBranchProtection404` into the table's first case, or keep it with the value asserted.
- `TestAutoDeleteBranches.test_present_when_no_branch_protection` is unchanged.
