# Step 1 — GitHub client factory (Part A) + PyGithub floor bump

> Read `pr_info/steps/summary.md` first. This step centralizes the three bare
> `Github()` constructions behind one factory so they cannot drift, and bumps the
> PyGithub floor so the `retry=`/`GithubRetry` API exists at install time.

## WHERE
- **Create** `src/mcp_workspace/github_operations/_client.py`
- **Create** `tests/github_operations/test_client.py`
- **Modify** `src/mcp_workspace/github_operations/base_manager.py`
  - `_github_client` property (bare `Github(...)`)
  - `get_authenticated_username()` (bare `Github(...)`)
- **Modify** `src/mcp_workspace/github_operations/verification.py`
  - the auth-probe `Github(...)` construction
- **Modify** `pyproject.toml` — `"PyGithub>=1.59.0"` → `"PyGithub>=2.1.0"`

## WHAT
```python
# _client.py
from github import Auth, Github, GithubRetry

GITHUB_REQUEST_TIMEOUT = 10
GITHUB_RETRY_TOTAL = 2

def build_github_client(token: str, base_url: str) -> Github:
    """Create a PyGithub client with bounded timeout/retry.

    timeout=10 with GithubRetry(total=2) gives ~30s worst case on an
    unreachable host (1 initial + 2 retries). total=2 also caps 403
    secondary-rate-limit backoff to 2 attempts — deliberate, do NOT raise back.
    """
```

## HOW (integration points)
- Replace each of the three constructions with
  `build_github_client(self.github_token, base_url)` /
  `build_github_client(raw_token, base_url)` /
  `build_github_client(token, api_base_url)`.
- Add `from mcp_workspace.github_operations._client import build_github_client`
  to `base_manager.py` and `verification.py`.
- `base_manager.py`: change `from github import Auth, Github` →
  `from github import Github` (Auth no longer used there; `Github` still used as
  the `_cached_github_client` type annotation).
- `verification.py`: drop `Auth, Github` from `from github import ...`
  (keep `GithubException`).
- `verification.py`: in `verify_github`, `token` from
  `get_github_token_with_source()` is `Optional[str]`, but
  `build_github_client(token: str, base_url: str)` types its param non-optional
  `str`. The verify-site call `build_github_client(token, api_base_url)` must
  keep a `# type: ignore[arg-type]` (the same suppression the old
  `Auth.Token(token)` carried) to satisfy mypy. (The two `base_manager.py` sites
  pass non-optional `str` and need no ignore.)
- **Do not** add a module-top `github` import anywhere new on the `server.py`
  import path — `_client.py` is a dedicated module, which is fine.

## ALGORITHM
```
build_github_client(token, base_url):
    return Github(auth=Auth.Token(token),
                  base_url=base_url,
                  timeout=GITHUB_REQUEST_TIMEOUT,
                  retry=GithubRetry(total=GITHUB_RETRY_TOTAL))
```

## DATA
- Returns a configured `github.Github` instance.
- Module constants `GITHUB_REQUEST_TIMEOUT = 10`, `GITHUB_RETRY_TOTAL = 2`.

## TDD — tests first (`test_client.py`)
- Patch `mcp_workspace.github_operations._client.Github` and call
  `build_github_client("tok", "https://api.github.com")`; assert it was called
  once with `timeout=10` and a `retry` whose `total == 2`, and `base_url` passed
  through. (Patching the constructor avoids brittle PyGithub-internal introspection.)
- Assert `GITHUB_REQUEST_TIMEOUT == 10` and `GITHUB_RETRY_TOTAL == 2`
  (guards the load-bearing 30s math).

## Checks before commit
- `run_pylint_check`, `run_mypy_check`, and
  `run_pytest_check(extra_args=["-n","auto","-m","not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])`
  all pass. Run `./tools/format_all.sh` before committing.

## Commit
One commit: factory module + three call-site repoints + pyproject bump + tests.
