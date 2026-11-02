# Step 1 — Add the `code_scanning_alerts` probe to `verify_github_security`

Read `pr_info/steps/summary.md` first. This is the only step and produces one commit.

## LLM prompt

> Implement Step 1 of `pr_info/steps/step_1.md`, using `pr_info/steps/summary.md` for
> context (issue #370). Follow TDD: update and add the tests in
> `tests/github_operations/test_security_probes.py` first, confirm the new ones fail, then
> implement the change in `src/mcp_workspace/github_operations/_security_probes.py`.
> Keep it minimal: no new modules, no helper beyond `_classify_code_scanning_alerts`.
> Run pylint, pytest (`extra_args: ["-n", "auto"]`), mypy and ruff via the MCP tools.
> All must pass. Then run format_code and commit.

## WHERE

- `src/mcp_workspace/github_operations/_security_probes.py`
- `tests/github_operations/test_security_probes.py`

## Precondition

`format_rate_limit_error` exists in `src/mcp_workspace/github_operations/_diagnostics.py`,
and `make_retry_error` exists in `tests/github_operations/conftest.py`. If either is
missing, write one line to `pr_info/.blocked.txt` and stop.

## Tests first (`test_security_probes.py`)

1. **`test_security_keys_order`**: add `"code_scanning_alerts"` as the fifth tuple element.
2. **`TestVerifyGithubSecurity._make_repo`**: add
   `repo.requester.requestJsonAndCheck.return_value = ({}, [])`. A default 200 keeps the
   four existing tests green, including `test_all_enabled`, which asserts `ok is True` for
   every key. Do not add a new parameter.
3. **New parametrized test** in `TestVerifyGithubSecurity`, e.g.
   `test_code_scanning_alerts_probe(self, tmp_path, side_effect, ok, value, error_part)`.
   Build the repo with `_make_repo(security_and_analysis=None, dependabot_status=204)`. Set
   `repo.requester.requestJsonAndCheck.side_effect = side_effect` when `side_effect` is not
   None. Patch `BaseGitHubManager` the same way the existing tests do. Assert `ok`, `value`,
   and either `error_part in result["error"]` or `"error" not in result` when `error_part`
   is None.

   | id | side_effect | ok | value | error_part |
   |---|---|---|---|---|
   | `200` | `None` (default return) | True | `scope present` | None |
   | `403_scope` | `GithubException(403, {"message": "Forbidden"}, {})` | False | `scope missing or Advanced Security not enabled` | None |
   | `403_rate_limit` | `GithubException(403, {"message": "x"}, {"X-RateLimit-Remaining": "0"})` | None | `not accessible` | `rate limit` |
   | `retry_error` | `make_retry_error(403)` | None | `not accessible` | `rate limit` |
   | `404` | `GithubException(404, {"message": "Not Found"}, {})` | False | `scope missing or not configured` | None |
   | `other_status` | `GithubException(500, {"message": "x"}, {})` | None | `not accessible` | `HTTP 500` |
   | `network` | `ConnectionError("boom")` | None | `not accessible` | `network error: boom` |

   Imports: `from github.GithubException import GithubException` and
   `from tests.github_operations.conftest import make_retry_error` (same import as
   `test_diagnostics.py`).
4. **New `test_code_scanning_alerts_request_shape`**: with the default 200 repo, call
   `verify_github_security`, then check `args, kwargs = repo.requester.requestJsonAndCheck.call_args`:
   `args[0] == "GET"`, `args[1].endswith("/code-scanning/alerts")`,
   `kwargs["parameters"] == {"per_page": 1}`.

## Implementation (`_security_probes.py`)

### WHAT

```python
_SECURITY_KEYS: tuple[str, ...] = (..., "secret_scanning_push_protection", "code_scanning_alerts")

def _classify_code_scanning_alerts(status: int) -> CheckResult:
    """Classify the HTTP status of the code-scanning alerts endpoint."""
```

### HOW

- Imports: `from github.GithubException import GithubException` and
  `from mcp_workspace.github_operations._diagnostics import format_rate_limit_error`.
- Place `_classify_code_scanning_alerts` directly after `_classify_vulnerability_alerts`.
- In `verify_github_security`, after `security_and_analysis = repo.security_and_analysis`
  and before the `return`, compute `code_scanning` inline (the issue's placement decision),
  then add `"code_scanning_alerts": code_scanning` as the last entry of the returned dict.
- Broad catch, same suppressions as `_probe_dependabot_alerts`:
  `# noqa: BLE001  # pylint: disable=broad-exception-caught`.

### ALGORITHM

```
try: repo.requester.requestJsonAndCheck("GET", f"{repo.url}/code-scanning/alerts", parameters={"per_page": 1})
     code_scanning = _classify_code_scanning_alerts(200)
except Exception as exc:
     if (msg := format_rate_limit_error(exc)) is not None: code_scanning = ok=None, "not accessible", error=msg
     elif isinstance(exc, GithubException):               code_scanning = _classify_code_scanning_alerts(exc.status)
     else:                                                 code_scanning = ok=None, "not accessible", error=f"network error: {exc}"
```

Classifier: 200 → ok=True `scope present`. 403 → ok=False
`scope missing or Advanced Security not enabled`. 404 → ok=False
`scope missing or not configured`. Anything else → ok=None `not accessible`,
`error=f"HTTP {status}"`. All results have `severity="warning"`.

### DATA

`verify_github_security` returns `dict[str, CheckResult]` with exactly the five keys of
`_SECURITY_KEYS`, in order. The unresolved-repository path is unchanged and now covers
five keys automatically.

### Docstring edits

- Module docstring: "these four checks have an unambiguous three-way split" → "these five
  checks have a three-way split". "two GitHub API shapes" → "three GitHub API shapes".
- `verify_github_security`: "four read-only" → "five read-only". "each of the four security
  settings" → "each of the five security settings". "exactly the 4 keys" → "exactly the 5 keys".

## Checks and commit

- `run_pylint_check`, `run_pytest_check` (`extra_args: ["-n", "auto"]`), `run_mypy_check`,
  `run_ruff_check`. All must pass.
- `run_format_code`, then commit, e.g.
  `feat(verify): probe the code-scanning alerts token scope in verify_github_security`.
