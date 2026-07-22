# Step 1 — Inline bounded retry for the reviewThreads GraphQL query (TDD)

Single commit: tests + implementation + all quality checks passing.

Read `pr_info/steps/summary.md` first for the full problem, approach, and rationale.

## WHERE

- Implementation: `src/mcp_workspace/github_operations/_pr_feedback_sources.py`
  - function `fetch_review_data(manager, pr_number)`
- Tests: `tests/github_operations/test_pr_manager_feedback.py`
  - class `TestGetPRFeedback`
- Do NOT touch: `pr_manager.py` (call-site contract unchanged),
  `_client.py` (global retry policy), `issues/branch_manager.py` (precedent only).

## WHAT

No signature changes. `fetch_review_data` keeps its signature and return type:

```python
def fetch_review_data(
    manager: "PullRequestManager", pr_number: int
) -> Tuple[list[dict[str, Any]], int, list[dict[str, Any]]]:
```

New module-local constants near the top of `_pr_feedback_sources.py`:

```python
# reviewThreads GraphQL retry config — handles GitHub's eventual-consistency
# flake where querying a brand-new PR node raises GithubException 400/404.
# Note: a genuinely-missing PR (404) now costs ~3s (1s + 2s backoff) before
# falling through to [unavailable]; 404 is included defensively — only 400 was
# reproduced.
_REVIEW_DATA_MAX_ATTEMPTS = 3
_REVIEW_DATA_RETRY_BASE_DELAY_SECONDS = 1.0
```

## HOW (integration points)

- Add `import time` to `_pr_feedback_sources.py` (alongside `import logging`).
  `GithubException` is already imported (`from github.GithubException import GithubException`).
- The loop wraps ONLY the existing `graphql_query` call. Everything after it
  (the `pr_data = result.get(...)` parsing and the thread/review loops) is unchanged.
- Call-site in `pr_manager.py:551` is unchanged: on permanent or exhausted failure the
  function still raises `GithubException`, and the caller still records
  `unavailable["threads"]` and renders `[unavailable]`.

## ALGORITHM (core logic — replaces only the `graphql_query` call)

```
result: dict[str, Any] = {}            # init before the loop (retry-loop shape statically triggers possibly-unbound)
for attempt in range(_REVIEW_DATA_MAX_ATTEMPTS):
    try:
        _, result = manager..._Github__requester.graphql_query(query, variables)
        break                          # success -> leave loop, parse result below
    except GithubException as e:
        # permanent error, or retries exhausted -> give up (caller renders unavailable)
        if e.status not in (400, 404) or attempt == _REVIEW_DATA_MAX_ATTEMPTS - 1:
            raise
        time.sleep(_REVIEW_DATA_RETRY_BASE_DELAY_SECONDS * 2 ** attempt)
# ...existing parsing of `result` unchanged...
```

Notes:
- One combined `if` covers both "non-retryable status" and "last attempt exhausted" —
  no `last_result`, no `assert`, no nested `attempt < MAX-1` guard, no per-retry logging
  (KISS; the caller already logs on final failure).
- Add the `result: dict[str, Any] = {}` initializer before the retry loop (expected/default):
  the retry-loop shape statically triggers a possibly-unbound warning. Do not add
  branch_manager's `Optional` + `assert` ceremony.

## DATA

- Success path: `result` is the `(headers, data)` tuple's data dict; parsing is unchanged
  and returns `Tuple[list[dict], int, list[dict]]` = (unresolved_threads,
  resolved_count, changes_requested).
- Failure path (permanent or exhausted): raises `GithubException`; caller catches it.

## TESTS (write first — TDD)

Patch `time.sleep` at the module where the loop lives:
`mcp_workspace.github_operations._pr_feedback_sources.time.sleep` (NOT branch_manager's).
Drive per-attempt behavior via `graphql_query`'s `side_effect` — the existing
`_setup_mocks(..., graphql_raises=...)` param already routes its argument to
`Mock(side_effect=...)`, so a list works there unchanged (no helper change needed).
Assert `graphql_query.call_count` to prove retry behavior.

1. **`test_review_data_retry_then_success`** — retry then succeed.
   - `valid_response`: a GraphQL response dict with one unresolved thread (reuse the
     shape from `test_happy_path`).
   - `graphql_raises=[GithubException(400, {"message": "..."}, None), ({}, valid_response)]`
     (mixed list: first raises, second is the `(headers, data)` success tuple).
   - `comments=[]`, `alerts_response=[]`.
   - `with patch("mcp_workspace.github_operations._pr_feedback_sources.time.sleep") as sleep:`
   - Assert: `requester.graphql_query.call_count == 2`; unresolved threads populated;
     `"threads" not in result["unavailable"]`; `sleep.call_count == 1`.

2. **`test_review_data_retry_exhausted_unavailable`** — always 400 -> exhausted.
   - `graphql_raises=GithubException(400, {"message": "..."}, None)` (raises every call).
   - `comments=[]`, `alerts_response=[]`; patch `time.sleep`.
   - Assert: `graphql_query.call_count == 3`; `"threads" in result["unavailable"]`;
     `isinstance(result["unavailable"]["threads"], GithubException)`;
     `sleep.call_count == 2` (sleeps after attempts 1 and 2, not after the last).

3. **Extend existing `test_graphql_failure`** (already uses status `500`) — prove no retry.
   - Wrap the call in `patch(".._pr_feedback_sources.time.sleep") as sleep`.
   - Add asserts: `graphql_query.call_count == 1`; `sleep.assert_not_called()`.
   - Keep its existing assertions green (500 is not retried, falls straight through).

## CHECKS (run via MCP tools; all must pass before commit)

- `mcp__tools-py__run_pylint_check`
- `mcp__tools-py__run_pytest_check` with
  `extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"]`
  - Note: `TestGetPRFeedback` is marked `@pytest.mark.git_integration`. To exercise these
    tests during development, additionally run
    `mcp__tools-py__run_pytest_check(extra_args=["-n","auto"], markers=["git_integration"])`.
- `mcp__tools-py__run_mypy_check`
- Before commit: run `./tools/format_all.sh`, review the diff is formatting-only, stage.

## COMMIT

One commit containing: constants + `import time` + retry loop in `_pr_feedback_sources.py`,
plus the two new tests and the extended `test_graphql_failure`.

Suggested message:

    check_branch_status: retry transient GraphQL 400/404 on fresh PRs

    Wrap the reviewThreads graphql_query call in fetch_review_data with a
    bounded 3-attempt exponential-backoff retry (1s/2s) triggered only by
    GithubException 400/404, so eventual-consistency flake on a brand-new PR
    node is retried instead of surfaced as [unavailable] threads. Other
    statuses re-raise immediately; on exhaustion the caller keeps rendering
    [unavailable]. Fixes #228.

## LLM PROMPT

> Implement Step 1 from `pr_info/steps/step_1.md`, using `pr_info/steps/summary.md` for
> context. Use MCP tools exclusively (`mcp__workspace__*` for files,
> `mcp__tools-py__*` for checks) per CLAUDE.md — no `Read`/`Write`/`Edit`/`Bash` for
> these. Work TDD: first add the three tests described under TESTS to
> `tests/github_operations/test_pr_manager_feedback.py` (two new, one extension of
> `test_graphql_failure`), confirm they fail; then add `import time`, the two
> `_REVIEW_DATA_*` constants, and the bounded retry loop around ONLY the `graphql_query`
> call in `fetch_review_data` in
> `src/mcp_workspace/github_operations/_pr_feedback_sources.py`, per WHERE/WHAT/HOW/
> ALGORITHM. Keep it minimal (KISS): single `try/except-break`, one combined re-raise
> condition, no per-retry logging, no `last_result`/`assert`. Do NOT modify
> `pr_manager.py`, `_client.py`, or `branch_manager.py`. Then run pylint, pytest
> (fast-unit exclusions AND the `git_integration` marker for these tests), and mypy via
> the MCP tools until all pass; run `./tools/format_all.sh` and confirm the diff is
> formatting-only. Produce exactly one commit.
