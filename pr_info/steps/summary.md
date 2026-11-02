# Summary — #369 IssueManager: public `check_body_trust` returning `BodyTrustResult`

## Goal

mcp_coder (#1311) must skip issues whose body is untrusted, but it cannot import PyGithub.
Add a public `IssueManager.check_body_trust(issue: IssueData) -> BodyTrustResult` that
applies the existing body-trust rule and returns a three-way outcome. A failed lookup is
reported as such and never treated as trusted. Rate limits propagate as `GitHubRateLimitError`.

Rule (unchanged): trusted if the author is trusted (`OWNER` / `MEMBER` / `COLLABORATOR` or
in `trusted_commenters`), **or** the last body editor is the token user or in
`trusted_commenters`. Compares are case-insensitive.

## Architectural / design changes

- **New module `issues/body_trust.py`.** It holds the enum, the result type, the reason
  strings and the decision logic. The module has no state and caches nothing.
  - `BodyTrust(str, Enum)` has the values `trusted` / `untrusted` / `lookup_failed`.
  - `BodyTrustResult(NamedTuple)` has `status: BodyTrust` and `reason: str`. Callers can
    construct it themselves.
  - `check_body_trust(manager, issue, allowlist: frozenset[str]) -> BodyTrustResult` is the
    decision function.
  - Private `_LookupFailed(Exception)` carries a fixed reason. It is raised by the two
    helpers below and caught in exactly one place in `check_body_trust`.
  - Private `_call(fn)` runs one network call (editor GraphQL query or token-user lookup).
    A rate-limit shape becomes `GitHubRateLimitError` via `to_rate_limit_error`. Any other
    exception becomes `_LookupFailed(type(exc).__name__)`. The reason is never the
    exception text.
  - Private `_editor_login(result) -> Optional[str]` is a pure parser of the GraphQL body.
    It returns `None` only when the `editor` key is present and null ("never edited").
    It maps a `Bot` editor to `name[bot]`. In every other case it raises `_LookupFailed`
    or `GitHubRateLimitError`.
- **`IssueManager.check_body_trust`** is a thin public method with no
  `_handle_github_errors`, because that decorator would default the return value. It reads
  `config.get_trusted_commenters()` once and delegates to the module function. The
  repository lookup (`_get_repository()`) and the allowlist stay inside the manager.
- **Repository-lookup rate limits:** `_get_repository()` is called inside
  `rate_limit_guard()`, which converts the raw rate-limit exceptions it re-raises. Every
  other failure is already swallowed by `_get_repository()`, which returns `None`; that
  becomes "repository unavailable".
- **Unchanged:** `fetch_body_editor` and `is_body_trusted` (the Base Branch path).
  `body_trust.py` only reuses `_BODY_EDITOR_QUERY` from `base_branch_trust.py`.
- **Layering:** `issues/` already imports `caching.errors` (`issues/cache.py`), so no new
  import-linter dependency is introduced.

## Decision order (implemented in `check_body_trust`)

1. Author trusted (`is_trusted_author(login, association, allowlist)`) → `TRUSTED`
   "author trusted". No GitHub calls.
2. `manager.repo_identifier` raises `ValueError` → `LOOKUP_FAILED` "repository not detected".
3. `with rate_limit_guard(): repo = manager._get_repository()`. `None` → `LOOKUP_FAILED`
   "repository unavailable".
4. `issue["number"] == 0` → `LOOKUP_FAILED` "issue number missing". No GraphQL request.
5. `_editor_login(_call(graphql_query))`. A never-edited body → `UNTRUSTED`
   "author and last editor untrusted".
6. `editor.lower() in allowlist` → `TRUSTED` "last editor trusted". No token-user lookup.
7. `_call(_cached_login)`. If it equals the editor (case-insensitive) → `TRUSTED`
   "last editor trusted", else `UNTRUSTED` "author and last editor untrusted".

Any `_LookupFailed(reason)` → `BodyTrustResult(BodyTrust.LOOKUP_FAILED, reason)`.

## Files

| Path | Change |
|---|---|
| `src/mcp_workspace/github_operations/issues/body_trust.py` | **new**: enum, result type, reasons, decision logic |
| `src/mcp_workspace/github_operations/issues/manager.py` | modified: add `check_body_trust` method |
| `src/mcp_workspace/github_operations/issues/__init__.py` | modified: re-export `BodyTrust`, `BodyTrustResult` |
| `tests/github_operations/issues/test_body_trust.py` | **new**: table-driven tests via `IssueManager.check_body_trust` |
| `README.md` | modified: `trusted_commenters` bullet, new body-trust bullet under "Commenter trust" |
| `docs/release-notes.md` | modified: entry under the top `## Next minor release`, `### New API` |

## Steps

1. [step_1.md](./step_1.md): `body_trust.py`, the manager method, the re-exports and tests (one commit).
2. [step_2.md](./step_2.md): README and release notes (one commit).

## Out of scope / gates

- No version bump.
- Merge is gated on the title-edit live check (option B) described in issue #369. That is a
  manual check by the maintainer and not part of these steps.
