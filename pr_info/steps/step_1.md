# Step 1 — `check_body_trust`: module, manager method, re-exports, tests

Read [summary.md](./summary.md) first. It has the decision order and design.

## LLM prompt

> Implement Step 1 of `pr_info/steps/summary.md` as described in `pr_info/steps/step_1.md`.
> Use TDD. First write `tests/github_operations/issues/test_body_trust.py` with every case
> listed below. Then add `issues/body_trust.py`, the `IssueManager.check_body_trust` method
> and the re-exports. Do not change `base_branch_trust.py` behaviour. Run pylint, pytest
> (`-n auto`), mypy, lint-imports and vulture. All must pass. Run format_code, then make
> one commit.

## Precondition

`src/mcp_workspace/github_operations/issues/base_branch_trust.py` defines
`_BODY_EDITOR_QUERY`, and `caching/errors.py` defines `to_rate_limit_error`,
`graphql_rate_limit_error`, `rate_limit_guard` and `GitHubRateLimitError`. If any of these is
missing, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- new `src/mcp_workspace/github_operations/issues/body_trust.py`
- `src/mcp_workspace/github_operations/issues/manager.py`: add one method
- `src/mcp_workspace/github_operations/issues/__init__.py`: add the import and `__all__` entries
- new `tests/github_operations/issues/test_body_trust.py`

## WHAT

`body_trust.py`:

```python
__all__ = ["BodyTrust", "BodyTrustResult", "check_body_trust"]

class BodyTrust(str, Enum):
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"
    LOOKUP_FAILED = "lookup_failed"

class BodyTrustResult(NamedTuple):
    status: BodyTrust
    reason: str

class _LookupFailed(Exception):          # carries a fixed, log-safe reason
    def __init__(self, reason: str) -> None: ...

def _call(fn: Callable[[], T]) -> T: ...
def _editor_login(result: Any) -> Optional[str]: ...
def check_body_trust(
    manager: BaseGitHubManager, issue: IssueData, allowlist: frozenset[str]
) -> BodyTrustResult: ...
```

Reason constants are module-level strings: `"author trusted"`, `"last editor trusted"`,
`"author and last editor untrusted"`, `"repository not detected"`,
`"repository unavailable"`, `"issue number missing"`, `"GraphQL error"`,
`"issue not found"`, `"editor login missing"`.

`manager.py`, method on `IssueManager`, decorated with `@log_function_call` only:

```python
def check_body_trust(self, issue: IssueData) -> BodyTrustResult:
    return body_trust.check_body_trust(self, issue, config.get_trusted_commenters())
```

Look up the allowlist through the `config` module, as `get_issue` does, so that a test patch
on `mcp_workspace.config.get_trusted_commenters` takes effect. The docstring must state that
it raises `GitHubRateLimitError` and never returns `TRUSTED` after a failed lookup.

`__init__.py`: `from .body_trust import BodyTrust, BodyTrustResult`. Add both names to
`__all__`.

## HOW

- Imports in `body_trust.py`:
  - `from ..base_manager import BaseGitHubManager, _cached_login`
  - `from ..caching.errors import graphql_rate_limit_error, rate_limit_guard, to_rate_limit_error`
  - `from ..trust import is_trusted_author, normalize_author_association`
  - `from .base_branch_trust import _BODY_EDITOR_QUERY`
  - `from .types import IssueData`
- GraphQL call, the same as `fetch_body_editor`:
  `manager._github_client._Github__requester.graphql_query(query=_BODY_EDITOR_QUERY, variables={"owner": repo.owner.login, "repo": repo.name, "number": number})`.
  Copy its `type: ignore` / pylint disable comment. Use only the second tuple element.
- Token user: `_cached_login(manager.github_token, manager.repo_identifier.api_base_url, manager._github_client)`.
- Read the author with `issue.get("user")` and
  `normalize_author_association(issue.get("author_association"))`, so missing keys on old
  cache entries never raise.
- Log a `_LookupFailed` at DEBUG with the issue number and the reason only.

## ALGORITHM

```
_call(fn):  try fn() / except Exception as exc:
            rl = to_rate_limit_error(exc); if rl: raise rl from exc
            raise _LookupFailed(type(exc).__name__) from exc

_editor_login(result):
  if dict and "errors" in result: raise graphql_rate_limit_error(result) or _LookupFailed("GraphQL error")
  walk data -> repository -> issue; each must be a dict, else _LookupFailed("issue not found")
  if "editor" not in issue: _LookupFailed("editor login missing"); if editor is None: return None
  editor must be dict with non-blank str login, else _LookupFailed("editor login missing")
  return f"{login}[bot]" if editor.get("__typename") == "Bot" else login

check_body_trust(manager, issue, allowlist):
  if is_trusted_author(login, association, allowlist): return TRUSTED "author trusted"
  try: manager.repo_identifier  except ValueError: return LOOKUP_FAILED "repository not detected"
  with rate_limit_guard(): repo = manager._get_repository()     -> None: "repository unavailable"
  if issue["number"] == 0: return LOOKUP_FAILED "issue number missing"
  try: editor = _editor_login(_call(graphql)); None -> UNTRUSTED
       if editor.lower() in allowlist -> TRUSTED "last editor trusted"
       token = _call(_cached_login) ; equal (lower) -> TRUSTED else UNTRUSTED
  except _LookupFailed as f: return LOOKUP_FAILED f.reason
```

## DATA

- Returns `BodyTrustResult(status: BodyTrust, reason: str)`. The reason is a fixed constant
  or an exception type name, never exception text.
- Raises `GitHubRateLimitError` for every rate-limit shape on the repository, editor and
  token-user paths.
- Caches nothing. Each call makes a fresh editor query. The token login stays cached
  process-wide in `_cached_login`.

## Tests — `tests/github_operations/issues/test_body_trust.py`

### Harness

- Use a real `IssueManager(repo_url="https://github.com/test/repo", github_token="t")` with
  `manager._cached_github_client = client`, where `client` is a `MagicMock`. This is the
  same pattern as `tests/github_operations/test_github_write_tools_issues.py`.
- `client.get_repo.return_value` is a repository mock with `owner.login="owner"` and
  `name="repo"`.
- `graphql = client._Github__requester.graphql_query`, with `return_value = ({}, body)` or
  a `side_effect`.
- `client.get_user.return_value.login = "tokenbot"`. The autouse fixture in
  `tests/github_operations/conftest.py` clears the login and repository caches.
- Patch the allowlist with `mcp_workspace.config.get_trusted_commenters`.
- Build issues as `IssueData` dicts (helper `_issue(user="stranger", association="NONE", number=7)`).
  For the "missing keys" case, delete the keys.
- Repository not detected: set `manager._cached_repo_identifier = None` and
  `manager.project_dir = tmp_path`, and patch
  `mcp_workspace.github_operations.base_manager.git_operations.get_repository_identifier`
  to return `None`.
- Exception builders:
  - `GithubException(status, data, headers)`
  - `RateLimitExceededException(403, {}, {})`
  - headers `{"X-RateLimit-Remaining": "0"}`
  - `RetryError(MaxRetryError(None, "u", ResponseError("too many 503 error responses")))`,
    with status 403 / 429 / 503 and a variant without status text for "unknown"
  - `UnknownObjectException(404, ...)`

### Parametrized tables (one row per acceptance bullet in issue #369)

1. **Author and editor outcomes**:
   - Trusted role, each of OWNER / MEMBER / COLLABORATOR → `TRUSTED` "author trusted", and
     `get_repo`, `graphql` and `get_user` are not called.
   - Trusted author via the allowlist (mixed-case login) → `TRUSTED`.
   - Editor on the allowlist (a user, and a `Bot` as `name[bot]`, mixed case) with
     `get_user` raising → `TRUSTED` "last editor trusted", and `get_user` is not called.
   - Editor equal to the token user, case-insensitive → `TRUSTED`.
   - Editor that is neither the token user nor on the allowlist (the "untrusted author
     re-edited" case) → `UNTRUSTED` "author and last editor untrusted".
   - `dependabot[bot]` editor with allowlist `dependabot` → `UNTRUSTED`.
   - Editor key present and `null` → `UNTRUSTED`, and `get_user` is not called.
   - `user` / `author_association` keys missing → `UNTRUSTED`, or `TRUSTED` when the
     editor is trusted.
2. **Order and short-circuits**:
   - Trusted author with a broken repository identity, `get_repo` returning `None`,
     `get_repo` raising a rate limit, or `number == 0` → `TRUSTED`, and `get_repo` is not
     called.
   - Repository identity missing, with `number` 7 or 0 → "repository not detected", and
     neither `get_repo` nor `graphql` is called.
   - `number == 0` with a repository failure → "repository unavailable".
   - `number == 0` → "issue number missing", and `graphql` is not called.
3. **Response bodies** (body → status and reason):
   - Editor missing, a string, or a list → "editor login missing".
   - Login absent, `""`, `"  "`, `42` or `None` → "editor login missing".
   - Non-raising `errors` values `[]`, `None`, `[{"type":"FORBIDDEN"}]`, `["oops"]`,
     `"boom"`, a single `NOT_FOUND` entry, or an error entry with a null issue (each with a
     usable editor where applicable) → "GraphQL error".
   - `errors` containing a `RATE_LIMITED` entry → raises `GitHubRateLimitError`.
   - `data` missing, `{"data": None}`, `{"data": {}}`, `repository` null, `issue` key
     missing, `issue` null, `data` / `repository` / `issue` given as a string, or a
     non-dict body → "issue not found".
4. **Exceptions by path** (path ∈ repository / editor / token user, exception → expected):
   - **Repository path:**
     - `ConnectionError`, `GithubException` 404 / 401 / 403, a 5xx `RetryError`, or a
       400 with `RATE_LIMITED` in `data` → "repository unavailable".
     - A rate-limit header, `RateLimitExceededException`, a 429, or a `RetryError` with
       status 403 / 429 / unknown → `GitHubRateLimitError`.
   - **Editor path:**
     - `UnknownObjectException` → "UnknownObjectException".
     - A 400 with several errors, a 400 with NOT_FOUND plus another error, or a 400 with
       `errors: []` → "GithubException".
     - `GithubException` 401 / 403 or 500 → "GithubException".
     - `TypeError` → "TypeError".
     - `ConnectionError` → "ConnectionError", and the reason contains no message text.
     - A 5xx `RetryError` → "RetryError".
     - `RATE_LIMITED` in `data` (400, and also 502), a rate-limit header,
       `RateLimitExceededException`, a 429, or a `RetryError` with status 403 / 429 /
       unknown → `GitHubRateLimitError`.
   - **Token-user path:**
     - `GithubException` 500 → "GithubException".
     - A 5xx `RetryError` → "RetryError".
     - A rate-limit header, or a `RetryError` with status 403 / 429 / unknown →
       `GitHubRateLimitError`.

### Single tests

- No caching: two calls make two `graphql` calls.
- The enum values are `trusted` / `untrusted` / `lookup_failed`.
  `BodyTrustResult(BodyTrust.LOOKUP_FAILED, "x")` is constructible.
- `BodyTrust` and `BodyTrustResult` can be imported from
  `mcp_workspace.github_operations.issues`, and `IssueManager` has `check_body_trust`.
- Query variables are `{"owner": "owner", "repo": "repo", "number": 7}`.

Existing `test_base_branch_trust.py` must still pass unchanged.
