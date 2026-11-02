# Step 2 — Editor response parsing and editor / allowlist / token decisions

Read [summary.md](./summary.md) first. It has the decision order and design.

## LLM prompt

> Implement Step 2 of `pr_info/steps/summary.md` as described in `pr_info/steps/step_2.md`.
> Use TDD. First add every case listed below to
> `tests/github_operations/issues/test_body_trust.py`. Then add `_LookupFailed`,
> `_editor_login` and decision steps 5–7 to `issues/body_trust.py`, replacing the Step 1
> placeholder. Do not change `base_branch_trust.py` behaviour. Run pylint, pytest
> (`-n auto`), mypy, lint-imports and vulture. All must pass. Run format_code, then make one
> commit.

## Precondition

`IssueManager.check_body_trust` exists and `body_trust.py` ends with the Step 1 placeholder.
`base_branch_trust.py` defines `_BODY_EDITOR_QUERY`, and `caching/errors.py` defines
`graphql_rate_limit_error`. If any of these is missing, write one line to
`pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/github_operations/issues/body_trust.py`
- `tests/github_operations/issues/test_body_trust.py`

## WHAT

```python
class _LookupFailed(Exception):          # carries a fixed, log-safe reason
    def __init__(self, reason: str) -> None: ...

def _editor_login(result: Any) -> Optional[str]: ...
```

Add the remaining reason constants: `"last editor trusted"`,
`"author and last editor untrusted"`, `"GraphQL error"`, `"issue not found"`.

## HOW

- Add imports:
  - `_cached_login` from `..base_manager`
  - `graphql_rate_limit_error` from `..caching.errors`
  - `from .base_branch_trust import _BODY_EDITOR_QUERY`
- GraphQL call, the same as `fetch_body_editor`:
  `manager._github_client._Github__requester.graphql_query(query=_BODY_EDITOR_QUERY, variables={"owner": repo.owner.login, "repo": repo.name, "number": number})`.
  Copy its `type: ignore` / pylint disable comment. Use only the second tuple element.
  In this step the call is not wrapped; Step 3 wraps it in `_call`.
- Token user: `_cached_login(manager.github_token, manager.repo_identifier.api_base_url, manager._github_client)`,
  also unwrapped until Step 3.
- Log a `_LookupFailed` at DEBUG with the issue number and the reason only.

## ALGORITHM

```
_editor_login(result):
  if dict and "errors" in result: raise graphql_rate_limit_error(result) or _LookupFailed("GraphQL error")
  walk data -> repository -> issue; each must be a dict, else _LookupFailed("issue not found")
  if "editor" not in issue: _LookupFailed("editor login missing"); if editor is None: return None
  editor must be dict with non-blank str login, else _LookupFailed("editor login missing")
  return f"{login}[bot]" if editor.get("__typename") == "Bot" else login

check_body_trust, after the number check (replaces the placeholder):
  try: editor = _editor_login(graphql()); None -> UNTRUSTED
       if editor.lower() in allowlist -> TRUSTED "last editor trusted"
       token = _cached_login(...) ; equal (lower) -> TRUSTED else UNTRUSTED
  except _LookupFailed as f: return LOOKUP_FAILED f.reason
```

## DATA

- Caches nothing. Each call makes a fresh editor query. The token login stays cached
  process-wide in `_cached_login`.

## Tests — `tests/github_operations/issues/test_body_trust.py`

Use the harness from [step_1.md](./step_1.md).

### Parametrized tables

1. **Editor outcomes**:
   - Editor on the allowlist (a user, and a `Bot` as `name[bot]`, mixed case) with
     `get_user` raising → `TRUSTED` "last editor trusted", and `get_user` is not called.
   - Editor equal to the token user, case-insensitive → `TRUSTED`.
   - Editor that is neither the token user nor on the allowlist (the "untrusted author
     re-edited" case) → `UNTRUSTED` "author and last editor untrusted".
   - `dependabot[bot]` editor with allowlist `dependabot` → `UNTRUSTED`.
   - Editor key present and `null` → `UNTRUSTED`, and `get_user` is not called.
   - `user` / `author_association` keys missing → `UNTRUSTED`, or `TRUSTED` when the
     editor is trusted.
2. **Response bodies** (body → status and reason):
   - Editor missing, a string, or a list → "editor login missing".
   - Login absent, `""`, `"  "`, `42` or `None` → "editor login missing".
   - Non-raising `errors` values `[]`, `None`, `[{"type":"FORBIDDEN"}]`, `["oops"]`,
     `"boom"`, a single `NOT_FOUND` entry, or an error entry with a null issue (each with a
     usable editor where applicable) → "GraphQL error".
   - `errors` containing a `RATE_LIMITED` entry → raises `GitHubRateLimitError`.
   - `data` missing, `{"data": None}`, `{"data": {}}`, `repository` null, `issue` key
     missing, `issue` null, `data` / `repository` / `issue` given as a string, or a
     non-dict body → "issue not found".

### Single tests

- No caching: two calls make two `graphql` calls.
- Query variables are `{"owner": "owner", "repo": "repo", "number": 7}`.

Existing `test_base_branch_trust.py` must still pass unchanged.
