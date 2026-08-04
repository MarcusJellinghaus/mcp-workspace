# Summary — Add `PullRequestManager.merge_pull_request()` (#247)

## Goal

Give `PullRequestManager` (`src/mcp_workspace/github_operations/pr_manager.py`)
the ability to **merge** a pull request. Today it can create / get / list /
find / close / assign PRs but not merge one. This unblocks mcp-coder #1101
(`auto_merge`), which verifies CI on a specific pushed commit and then merges the
PR from `src/` without ever shelling out to `gh`.

The method wraps PyGithub's `PullRequest.merge(...)` and returns a `MergeResult`
whose **`outcome` field reliably distinguishes three cases** that the consumer
routes differently:

| `outcome`  | consumer action                                   |
|------------|---------------------------------------------------|
| `merged`   | done — proceed to post-merge steps                |
| `refused`  | re-fetch PR, classify `mergeable_state`, maybe rebase + retry once (`status == 409` ⇒ head moved, re-verify CI on new HEAD) |
| `error`    | retry a few times, then terminal — **do not** rebase |
| *raises*   | 401/403 config error — bubbles up, not an outcome |

## Why this needs care (the non-obvious constraints)

1. **PyGithub raises on refusal; it never returns `merged=False`.**
   `PullRequest.merge()` ends in `requestJsonAndCheck`, which raises
   `GithubException` on any non-2xx. A populated `MergeResult` for 405/409 can
   therefore **only** be built inside an `except GithubException` block — the
   decorator's default value has no status and no message.
2. **`status is not None` is not a valid discriminator.** A 500 has a status but
   is not a refusal; a socket timeout has no status at all. Hence an explicit
   `Literal["merged", "refused", "error"]`, with the 4xx/5xx classification owned
   by this library, not re-derived by every consumer.
3. **The HTTP layer retries the merge PUT** (`GithubRetry(total=2)` in
   `_client.py`; urllib3's default allowed-methods set already includes PUT). If
   GitHub merges and the response is then lost, the retry re-issues the PUT and
   gets **405 "not mergeable" because it is already merged**. So on 405 we
   **re-fetch the PR once**: if `pr.merged is True` ⇒ `merged`
   (`sha = pr.merge_commit_sha`), else `refused`; if the re-fetch itself fails ⇒
   `refused`. The docstring must say *"`merged=True` reports the PR is merged as
   of that read — not that this call performed the merge"* (no causation claim).
4. **`sha` / `commit_title` / `commit_message` must be omitted, not passed as
   `None`** — PyGithub asserts `is_optional(v, str)`, and `None` surfaces as an
   `AssertionError`. Omitting also yields GitHub's default squash title
   (`PR title (#NNN)`), the repo convention.
5. **`_handle_github_errors` currently never calls a callable default**
   (`return cast(T, default_return)`), so a factory default returns the *function
   object*. We fold in a `callable(default_return)` guard so this method can use a
   `_failed_merge_result()` factory (fresh dict per failure). This also repairs two
   latent sites (`list_pull_requests`, `get_pr_feedback`) currently shadowed by
   inner `try/except` blocks.

## Architectural / design changes

- **New public data type `MergeResult` (TypedDict).** Fields: `merged: bool`,
  `outcome: Literal["merged","refused","error"]`, `sha: Optional[str]`,
  `message: str`, `status: Optional[int]`. `outcome` is the sole cross-process
  contract; `status` is diagnostic-only for 405 but **actionable for 409**.
- **New factory `_failed_merge_result()`** → fresh `MergeResult` with
  `outcome="error"`. Used as the decorator's `default_return` so every non-Github
  failure (network, `AssertionError`) becomes `error` with no shared-mutable-dict
  hazard.
- **New method `merge_pull_request()`** follows the exact shape of the sibling
  methods (`@log_function_call`, `@_handle_github_errors`, `_validate_pr_number`,
  `_get_repository`). It performs **one logical attempt** — retry ownership stays
  with the consumer (every other method is single-attempt; a hidden retry inside a
  *write* is surprising).
- **Decorator behaviour change (`_handle_github_errors`)**: when
  `default_return` is callable, call it; otherwise return it as-is. Purely
  additive — the ~34 dict/list/`False`/`None` sites are non-callable and
  unaffected; the two callable sites become correct-by-construction instead of
  relying on inner shadowing.
- **Export surface**: add **both** `MergeResult` and `PullRequestData` to
  `github_operations/__init__.py` `__all__`. `PullRequestData` was a prior
  omission (siblings already export `CIStatusData`, `LabelData`, `CheckResult`).
  Purely additive.
- **Out of scope (intentional):** no `github_pr_merge` MCP tool (all `github_*`
  tools are read-only; an agent-invokable merge would bypass the CI gate); no
  head-branch deletion (relies on the repo's "auto-delete head branches"); no
  pre-flight `pr.merged` check (closes no race); no retry loop.

## KISS design decisions

- **The decorator owns "anything that is not a `GithubException`."** The method
  contains a single, narrowly-scoped `except GithubException` classifier; network
  errors / `AssertionError` fall through to the decorator → `error`. No bare
  `except Exception` in the method.
- **Flat guard-clause classifier** (early returns), matching the sibling methods:
  `401/403 → raise`, `405 → re-fetch`, `(409, 422) → refused`, else `→ error`.
- **Explicit `(409, 422)` whitelist** for `refused`, not an "any 4xx except 404"
  range — simpler and spec-exact (404 → `error`).
- **Inline `MergeResult` literals** at each return site (no result-builder
  abstraction); only the mandated `_failed_merge_result()` factory exists.
- **Tests use one local `manager` fixture** to remove the repeated
  `git.Repo.init` + token-patch boilerplate copied into every sibling test.

## `outcome` mapping (authoritative)

| HTTP / condition                              | `outcome` | `merged` | `status` |
|-----------------------------------------------|-----------|----------|----------|
| 200                                           | `merged`  | `True`   | 200      |
| 405 **and** re-fetched `pr.merged is True`    | `merged`  | `True`   | 405      |
| 405 (not merged / re-fetch failed), 409, 422  | `refused` | `False`  | status   |
| 404, 5xx, network, validation                 | `error`   | `False`  | status/None |
| 401 / 403                                     | *raises*  | —        | —        |

## Files created / modified

| Action   | Path                                                              | Purpose                                             |
|----------|-------------------------------------------------------------------|-----------------------------------------------------|
| Modified | `src/mcp_workspace/github_operations/base_manager.py`             | `callable(default_return)` guard in `_handle_github_errors` |
| Modified | `tests/github_operations/test_base_manager.py`                    | Test: callable default is invoked                   |
| Modified | `src/mcp_workspace/github_operations/pr_manager.py`               | `MergeResult`, `_failed_merge_result()`, `merge_pull_request()` |
| Created  | `tests/github_operations/test_pr_manager_merge.py`                | Unit tests for `merge_pull_request()`               |
| Modified | `src/mcp_workspace/github_operations/__init__.py`                 | Export `MergeResult` + `PullRequestData`            |
| Modified | `tests/github_operations/test_pr_manager.py` *(or a small new test)* | Assert both names importable from the package     |

## Implementation steps (one commit each, TDD)

1. **Step 1 — Decorator callable fix.** Add the `callable(default_return)` guard
   to `_handle_github_errors` + a dedicated test. Prerequisite for Step 2's
   factory default. (`base_manager.py`, `test_base_manager.py`)
2. **Step 2 — `merge_pull_request()`.** Add `MergeResult`,
   `_failed_merge_result()`, and the method, driven by the new test file covering
   every acceptance case. (`pr_manager.py`, `test_pr_manager_merge.py`)
3. **Step 3 — Export surface.** Add `MergeResult` + `PullRequestData` to
   `__all__` + an importability test. (`__init__.py`, package test)

## Verification (every step)

- `mcp__tools-py__run_pylint_check`
- `mcp__tools-py__run_pytest_check` — fast unit run:
  `extra_args=["-n","auto","-m","not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"]`
- The new merge tests are marked `@pytest.mark.git_integration`; run them with
  `markers=["git_integration"]`.
- `mcp__tools-py__run_mypy_check`
