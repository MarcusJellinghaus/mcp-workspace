# Step 2 — Move PR-cache test helpers (pure refactor)

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_2.md` exactly.
> This is a test-only refactor: no production code changes, no test logic changes.
> Run pylint, pytest (`-n auto`) and mypy; all must pass. Format, then make exactly one commit.

## Precondition

`tests/github_operations/caching/test_pull_requests_results.py` passes before you start.
If it does not, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- Create `tests/github_operations/caching/_pr_cache_test_helpers.py`
- Modify `tests/github_operations/caching/test_pull_requests_results.py`

## WHAT

Move, unchanged, every module-level helper and constant above `class TestMergeableState`
in `test_pull_requests_results.py`:

- constants `_REPO`, `_CREATED`, `_PR_UPDATED`, `_ISSUE_UPDATED`
- `_open_pr`, `_issue`, `_run`, `_feedback`, `_event`, `_rate_limit`, `_server_error`
- `class _Env`, `_pr_list_item`
- `_path`, `_read`, `_age_snapshot`, `_expire_slot`, `_one_run`

Move them as one block — `_Env` depends on `_run`, `_feedback`, `_event`, `_pr_list_item`.

## HOW

- Helper module docstring: `"""Shared helpers for the PullRequestCache tests."""`
- Move the imports the helpers need along with them; keep in the results test file only
  the imports its tests still use.
- In `test_pull_requests_results.py`:
  `from ._pr_cache_test_helpers import (_CREATED, _Env, _age_snapshot, ...)` — only
  the names it uses. Add `# pylint: disable=...` only if pylint flags the
  underscore-prefixed imports; follow how `tests/github_operations/_pr_test_helpers.py`
  is imported elsewhere.
- Leave the results file's module docstring unchanged.

## ALGORITHM

None (code move).

## DATA

No change.

## Tests

No new tests. The full suite must pass with the same test count as before.
