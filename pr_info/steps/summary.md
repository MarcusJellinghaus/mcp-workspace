# Summary — Issue #228: retry transient GraphQL 400/404 on freshly-created PRs

## Problem

`fetch_review_data()` in `src/mcp_workspace/github_operations/_pr_feedback_sources.py`
runs a single GraphQL `reviewThreads`/`reviews` query via
`manager._github_client._Github__requester.graphql_query(...)`. When a PR is polled
immediately after creation (`pr-creating` -> `pr-created`, CI pending), GitHub's
GraphQL layer is eventually-consistent on the brand-new PR node and intermittently
raises `GithubException 400`. This propagates to the `except Exception` at
`pr_manager.py:551`, which records it in `unavailable["threads"]`; the status report
then renders the misleading line:

    PR Reviews:
    [unavailable] threads: GithubException 400

The report still completes correctly (one failing section does not abort it), but the
line reads like a real failure when it is just eventual-consistency on a fresh PR.
The same call succeeds on the next poll.

## Goal

Add a short, bounded retry loop **inline in `fetch_review_data`**, scoped to just the
`graphql_query` call, so transient 400/404 on a fresh PR node is retried instead of
surfaced. Permanent errors fall through immediately to today's `[unavailable]`
behavior.

## Approach (KISS)

Wrap **only** the `graphql_query` call in a `try/except GithubException` loop:

- **Trigger:** the call raises `GithubException` with `status == 400` **or** `404`.
  Any other status re-raises immediately (no retry) — 400 is normally a genuine
  client error, so we do not blanket-retry it elsewhere.
- **Attempts:** 3 total, exponential backoff `base * 2**attempt` = 1s then 2s
  (~3s worst case).
- **On exhaustion:** re-raise the last exception; the caller keeps rendering
  `[unavailable]`. No `[pending]` softening.

Because our trigger is a *raised exception* (not a parsed-result inspection), the loop
collapses to a single `try/except-break` with one combined re-raise condition — no
`last_result` tracking, no `assert`, no nested attempt guard, no per-retry logging.
The existing parsing code after the call is unchanged.

## Why not the alternatives

- **Client-level retry does NOT cover this.** `build_github_client` (`_client.py`) sets
  `GithubRetry(total=2)`, but PyGithub's `GithubRetry` retries 403/5xx only — not
  400/404. Broadening the global policy to retry all 400s would be wrong (400 is
  normally a genuine client error). A targeted inline retry is required.
- **Age-based softening (classify 400 on a young PR as "pending") — rejected.** It
  masks the root cause, needs PR `createdAt` plumbing, and adds a new concept. Retry
  fixes the root cause.
- **Do not copy `branch_manager`'s trigger.** `issues/branch_manager.py` handles the
  same class of GraphQL eventual-consistency flake on `createLinkedBranch` with a
  3-attempt exponential-backoff loop. We reuse its **loop shape and backoff math only**.
  Its trigger is a *successful response missing `linkedBranch.ref`* (parse inspection);
  ours is a *raised* `GithubException(400/404)`. So the trigger is `try/except`, not
  parse-result inspection. Do not import its `_CREATE_LINKED_BRANCH_*` symbols — that
  name reads wrong in a PR-feedback module.

## Architectural / design changes

- **No new modules, classes, or public API.** This is a localized reliability fix
  inside one existing private helper function.
- **New module-local constants** in `_pr_feedback_sources.py`:
  `_REVIEW_DATA_MAX_ATTEMPTS = 3`, `_REVIEW_DATA_RETRY_BASE_DELAY_SECONDS = 1.0`.
- **New dependency** on `time.sleep` inside `_pr_feedback_sources.py` (`import time`
  added — not currently imported).
- **Behavioral contract at the call site (`pr_manager.py`) is unchanged**: on permanent
  or exhausted failure, `fetch_review_data` still raises `GithubException`, and the
  caller still records `unavailable["threads"]`. No signature or return-type change.
- **Trade-off accepted:** a genuinely-missing PR (e.g. wrong `pr_number` -> 404) now
  costs ~3s before falling through. 404 is defensive (only 400 was reproduced);
  low-cost, accepted.

## Files created / modified

Created:

- `pr_info/steps/summary.md` (this file)
- `pr_info/steps/step_1.md`

Modified:

- `src/mcp_workspace/github_operations/_pr_feedback_sources.py`
  - add `import time`
  - add constants `_REVIEW_DATA_MAX_ATTEMPTS`, `_REVIEW_DATA_RETRY_BASE_DELAY_SECONDS`
  - wrap the `graphql_query` call in `fetch_review_data` with the bounded retry loop
- `tests/github_operations/test_pr_manager_feedback.py`
  - add `test_review_data_retry_then_success`
  - add `test_review_data_retry_exhausted_unavailable`
  - extend existing `test_graphql_failure` (status 500) to assert `call_count == 1`
    and no `time.sleep` (proves non-400/404 is not retried)

Not modified (explicitly out of scope): `_client.py` (global retry policy),
`issues/branch_manager.py` (precedent only).

## Implementation plan

Single commit (the change is cohesive — constants, import, loop, and its tests move
together):

- **Step 1** — Inline bounded retry for the `reviewThreads` GraphQL query, TDD.
