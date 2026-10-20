# Summary — carry the cause of a swallowed lookup failure on CIStatusData (#327)

## Problem

`get_latest_ci_status` swallows every non-401/403 `GithubException` and every generic
`Exception`, returning `CIStatusData(run={}, jobs=[], lookup_failed=True)` with the
exception discarded. Callers can see *that* the lookup failed but not *why* — a
swallowed 5xx, a swallowed 429, and a swallowed network error all look identical.

## Architectural / design changes

1. **`_handle_github_errors` gains a second, independent, optional parameter**
   `on_error: Optional[Callable[[BaseException, T], None]] = None`. It is called
   with the caught exception and the resolved value only when supplied, immediately
   after `resolved` is computed from `default_return`, in the non-auth
   `GithubException` branch and the generic `Exception` branch only (never on
   `ValueError` or 401/403, which re-raise before `default_return` is touched), so it
   can mutate the resolved value in place. `default_return`'s existing
   zero-arg-factory/plain-value calling convention is **unchanged** for every other
   caller — `on_error` is strictly additive.

2. **`BaseGitHubManager` gains a private instance attribute**
   `_last_repository_error: Optional[str]`, initialized to `None` in `__init__` and
   written by `_get_repository()` on failure (both the `GithubException` and the
   generic `Exception` branch), immediately before its existing `return None`.
   `_get_repository()`'s public `Optional[Repository]` signature is **unchanged** —
   other callers (`get_default_branch`, etc.) are unaffected. Not reset on success:
   it has exactly one consumer (`get_latest_ci_status`, reading it right after a
   `None` return within the same call), so a stale value is never surfaced later.

3. **`CIStatusData` gains `lookup_error: NotRequired[str]`**, set together with
   `lookup_failed=True` in `get_latest_ci_status`, via:
   - a new module-level helper `_set_lookup_error(e, data)` — delegating to
     `base_manager.py`'s `_format_error_message` for the message text — passed as
     `on_error` to the `@_handle_github_errors` decorator (covers the
     swallowed-exception path), and
   - a direct read of `self._last_repository_error` on the manual
     `_get_repository()`-returned-`None` branch (covers the repository-inaccessible
     path).

4. **Message format, no rate-limit special-casing, lives in one place:**
   a private helper `_format_error_message(e: BaseException) -> str` in
   `base_manager.py` (added in step 2), used by both `_get_repository()` and
   `ci_results_manager.py`'s `_set_lookup_error` — no second copy of this logic.
   - `GithubException`: `f"GitHub API error {e.status}: {message}"` where
     `message = e.data.get("message", "")`.
   - generic `Exception`: `f"network error: {type(e).__name__}"`.
   - Derived only from status code, the GitHub-supplied `message` field, and the
     exception type name — never from `e.headers` or the token.

## Out of scope (see issue Constraints/Decisions)

- No `rate_limited` field or reset-timestamp — the only swallowed rate-limit-*shaped*
  case (a generic 429) isn't PyGithub's classified rate-limit type, and
  `RateLimitExceededException` is unreachable in the swallowed path (always re-raised
  at status 403).
- `_get_repository()`'s return signature is not changed.
- `default_return`'s calling convention is not changed for any existing caller.
- mcp-coder's consumer-side poll (MarcusJellinghaus/mcp-coder#1183) is a separate repo.

## Folders / modules / files touched

Modified (no new modules):
- `src/mcp_workspace/github_operations/base_manager.py` — steps 1, 2
- `src/mcp_workspace/github_operations/ci_results_manager.py` — step 3
- `tests/github_operations/test_base_manager.py` — steps 1, 2
- `tests/github_operations/test_ci_results_manager_status.py` — step 3

Created (plan artifacts, not part of the shipped change):
- `pr_info/steps/summary.md` (this file)
- `pr_info/steps/step_1.md`
- `pr_info/steps/step_2.md`
- `pr_info/steps/step_3.md`

## Steps

1. `step_1.md` — `on_error` parameter on `_handle_github_errors`
2. `step_2.md` — `_last_repository_error` on `BaseGitHubManager._get_repository()`
3. `step_3.md` — wire `lookup_error` into `CIStatusData` / `get_latest_ci_status`

Each step is one commit: tests written first, then the implementation that makes
them pass, then quality checks, then format + commit.
