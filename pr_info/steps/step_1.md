# Step 1 — Types, manager method, re-exports, author short-circuit, repository/number order

Read [summary.md](./summary.md) first. It has the decision order and design.

## LLM prompt

> Implement Step 1 of `pr_info/steps/summary.md` as described in `pr_info/steps/step_1.md`.
> Use TDD. First write `tests/github_operations/issues/test_body_trust.py` with every case
> listed below. Then add `issues/body_trust.py` (decision steps 1–4 only), the
> `IssueManager.check_body_trust` method and the re-exports. Do not change
> `base_branch_trust.py` behaviour. Run pylint, pytest (`-n auto`), mypy, lint-imports and
> vulture. All must pass. Run format_code, then make one commit.

## Precondition

`caching/errors.py` defines `rate_limit_guard` and `GitHubRateLimitError`. If either is
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

def check_body_trust(
    manager: BaseGitHubManager, issue: IssueData, allowlist: frozenset[str]
) -> BodyTrustResult: ...
```

Reason constants are module-level strings. Add the ones this step uses: `"author trusted"`,
`"repository not detected"`, `"repository unavailable"`, `"issue number missing"`, and
`"editor login missing"` (used by the placeholder below). Step 2 adds the rest.

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

- Imports in `body_trust.py` (later steps add more):
  - `from ..base_manager import BaseGitHubManager`
  - `from ..caching.errors import rate_limit_guard`
  - `from ..trust import is_trusted_author, normalize_author_association`
  - `from .types import IssueData`
- Read the author with `issue.get("user")` and
  `normalize_author_association(issue.get("author_association"))`, so missing keys on old
  cache entries never raise.

## ALGORITHM

```
check_body_trust(manager, issue, allowlist):
  if is_trusted_author(login, association, allowlist): return TRUSTED "author trusted"
  try: manager.repo_identifier  except ValueError: return LOOKUP_FAILED "repository not detected"
  with rate_limit_guard(): repo = manager._get_repository()     -> None: "repository unavailable"
  if issue["number"] == 0: return LOOKUP_FAILED "issue number missing"
  # placeholder until Step 2, fail-closed:
  return LOOKUP_FAILED "editor login missing"
```

The placeholder is not tested; Step 2 replaces it with the editor lookup.

## DATA

- Returns `BodyTrustResult(status: BodyTrust, reason: str)`. The reason is a fixed constant.
- Raises `GitHubRateLimitError` for every rate-limit shape on the repository path.

## Tests — `tests/github_operations/issues/test_body_trust.py`

### Harness (shared by Steps 1–3)

- Use a real `IssueManager(repo_url="https://github.com/test/repo", github_token="t")` with
  `manager._cached_github_client = client`, where `client` is a `MagicMock`. This is the
  same pattern as `tests/github_operations/test_github_write_tools_issues.py`.
- `client.get_repo.return_value` is a repository mock with `owner.login="owner"` and
  `name="repo"`.
- `graphql = client._Github__requester.graphql_query`, with `return_value = ({}, body)` or
  a `side_effect`.
- `client.get_user.return_value.login = "tokenbot"`.
- Cache isolation is already in place, so no new fixture is needed. The autouse
  `_reset_repository_cache` in `tests/conftest.py` clears the repository cache, and the
  autouse `reset_login_cache` in `tests/github_operations/conftest.py` clears the login cache.
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
  - `RetryError`: reuse `make_retry_error(status)` from `tests/github_operations/conftest.py`
    for 403 / 429 / 503. Build a `RetryError` without a reason
    (`RetryError(MaxRetryError(None, "u"))`) only for the unknown-status case.
  - `UnknownObjectException(404, ...)`

### Parametrized tables (one row per acceptance bullet in issue #369)

1. **Author outcomes**:
   - Trusted role, each of OWNER / MEMBER / COLLABORATOR → `TRUSTED` "author trusted", and
     `get_repo`, `graphql` and `get_user` are not called.
   - Trusted author via the allowlist (mixed-case login) → `TRUSTED` "author trusted", and
     `get_repo`, `graphql` and `get_user` are not called.
2. **Order and short-circuits**:
   - Trusted author with a broken repository identity, `get_repo` returning `None`,
     `get_repo` raising a rate limit, or `number == 0` → `TRUSTED`, and `get_repo` is not
     called.
   - Repository identity missing, with `number` 7 or 0 → "repository not detected", and
     neither `get_repo` nor `graphql` is called.
   - Untrusted author, `number` 7, `client.get_repo.return_value = None` (the repository
     lookup returns `None` and no exception reaches `check_body_trust`) →
     `LOOKUP_FAILED` "repository unavailable", and `graphql` is not called.
   - `number == 0` with a repository failure → "repository unavailable", and `graphql` is
     not called.
   - `number == 0` → "issue number missing", and `graphql` is not called.
3. **Repository-path exceptions** (`get_repo` side effect → expected):
   - `ConnectionError`, `GithubException` 404 / 401 / 403, a 5xx `RetryError`, or a
     400 with `RATE_LIMITED` in `data` → "repository unavailable", and `graphql` is not
     called.
   - A rate-limit header, `RateLimitExceededException`, a 429, or a `RetryError` with
     status 403 / 429 / unknown → `GitHubRateLimitError`.

### Single tests

- The enum values are `trusted` / `untrusted` / `lookup_failed`.
  `BodyTrustResult(BodyTrust.LOOKUP_FAILED, "x")` is constructible.
- `BodyTrust` and `BodyTrustResult` can be imported from
  `mcp_workspace.github_operations.issues`, and `IssueManager` has `check_body_trust`.

Existing `test_base_branch_trust.py` must still pass unchanged.
