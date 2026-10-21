# Step 3 — Shared login cache in `base_manager`

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_3.md`), and issue #329
> (sections "Shared login cache" and "Constraints & Rationale") for context. Implement **only**
> this step with TDD: write the tests below first, then the implementation. Run pylint,
> pytest (`extra_args: ["-n", "auto"]`), mypy and vulture; all must pass. Run
> `run_format_code`, then make exactly one commit.

## WHERE

- `src/mcp_workspace/github_operations/base_manager.py`
- `src/mcp_workspace/github_operations/__init__.py`
- `src/mcp_workspace/github_operations/_diagnostics.py` (docstring only)
- `tests/github_operations/conftest.py`
- `tests/github_operations/test_base_manager.py`

## WHAT

```python
# base_manager.py
import hashlib

# (api_base_url, sha256(token) hexdigest) -> login. Never key by format_token_fingerprint.
_login_cache: dict[tuple[str, str], str] = {}

def _cached_login(token: str, base_url: str, client: Optional[Github] = None) -> str:
    """Return the login for token on base_url, calling GET /user at most once per key."""

def clear_login_cache() -> None:
    """Forget every cached login (used by tests)."""
```

`__all__` of `base_manager` gains `"clear_login_cache"`.

`github_operations/__init__.py`:

- `from .base_manager import (..., clear_login_cache, ...)` and add to `__all__`.
- `from ._diagnostics import RetryError, format_rate_limit_error`, both added to `__all__`
  (used by `server.py` in step 6; re-exporting here keeps `requests` out of `server.py`).
  Extend the existing `GithubException` re-export comment to cover them.

`_diagnostics.py`: change the "not re-exported" docstring sentence to say only
`format_rate_limit_error` and `RetryError` are re-exported.

## HOW

- `get_authenticated_username` keeps signature, token check, `base_url =
  hostname_to_api_base_url(hostname or "github.com")`, and its `try`/`except` blocks. Only the
  body of the `try` changes to `return _cached_login(raw_token, base_url)`.
- No lock. Never log the hash.

## ALGORITHM

```
key = (base_url, hashlib.sha256(token.encode()).hexdigest())
if key not in _login_cache:
    github = client if client is not None else build_github_client(token, base_url)
    _login_cache[key] = github.get_user().login   # exceptions propagate, nothing stored
return _login_cache[key]
```

## DATA

- `_login_cache: dict[tuple[str, str], str]`; `_cached_login -> str`; `clear_login_cache -> None`.

## Tests (write first)

- `tests/github_operations/conftest.py`: autouse fixture **named `reset_login_cache`**
  calling `clear_login_cache()` before and after `yield` (the name keeps
  `vulture_whitelist.py`'s `_.reset_login_cache` entry valid). The three per-file fixtures of
  the same name in `test_github_write_tools_issue*.py` still exist and shadow it in those files
  until step 5 — leave them.
- `test_base_manager.py`, new class `TestLoginCache` (patch
  `base_manager.get_github_token` and `mcp_workspace.github_operations._client.Github` as the
  existing `TestGetAuthenticatedUsername` tests do):
  - Two `get_authenticated_username()` calls → `Github` constructed once, `get_user` once.
  - `hostname=None`, `"github.com"` and `_cached_login(token, "https://api.github.com", client)`
    share one entry (the explicit `client.get_user` is not called).
  - Different token (`get_github_token` `side_effect=["a", "b"]`) → two lookups.
  - Different hostname (`"ghe.corp.com"`) → two lookups.
  - First `get_user` raises `GithubException(500, ...)` → `ValueError`; second call succeeds
    with a lookup (failure not cached).
  - `clear_login_cache()` forces a fresh lookup.
- Run vulture; if it flags `clear_login_cache`, add an entry to `vulture_whitelist.py`.
