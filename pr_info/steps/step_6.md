# Step 6: `PullRequestCache` layer 2 — four fingerprinted result slots

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_6.md` exactly.
> TDD: write the tests first, then the code. Run pylint, pytest (`-n auto`) and mypy;
> all must pass. One commit.

## Precondition

Check with `mcp__mcp-tools-py__get_library_source` that PyGithub's
`Repository.get_workflow_runs` accepts `head_sha`. If it does not: write one line to
`pr_info/.blocked.txt` and stop.

## WHERE

- Modify `src/mcp_workspace/github_operations/caching/pull_requests.py`
- Modify `src/mcp_workspace/github_operations/pr_feedback_mixin.py` — extract undecorated
  `_collect_pr_feedback`; `get_pr_feedback` becomes a thin decorated wrapper
- Tests: `tests/github_operations/caching/test_pull_requests_results.py`

## WHAT

```python
class PullRequestCache:
    def mergeable_state(self, pr: OpenPullRequest, issue: IssueData) -> str | None: ...
    def ci_status(self, pr: OpenPullRequest, issue: IssueData) -> CIStatusData: ...
    def feedback(self, pr: OpenPullRequest, issue: IssueData) -> PRFeedback: ...
    def label_events(self, pr: OpenPullRequest, issue: IssueData) -> list[EventData]: ...

    def _cached(self, pr: OpenPullRequest, slot: str, fp: list[Any]) -> tuple[bool, Any]: ...
    def _store(self, pr: OpenPullRequest, slot: str, fp: list[Any], value: Any) -> None: ...

# pr_feedback_mixin.py
class PRFeedbackMixin:
    def _collect_pr_feedback(self, pr_number: int, include_alerts: bool = True) -> PRFeedback:
        """Today's get_pr_feedback body, undecorated: per-section failures go to
        `unavailable`; anything raised outside the sections propagates."""
    @log_function_call
    @_handle_github_errors(default_return=_empty_pr_feedback)
    def get_pr_feedback(self, pr_number: int, include_alerts: bool = True) -> PRFeedback:
        """Unchanged signature/behaviour; returns self._collect_pr_feedback(...)."""

def _fetch_ci_status(
    repo: Repository, head_sha: str, branch: str
) -> tuple[CIStatusData, bool]: ...  # undecorated; bool = final (every run completed)
```

## HOW

Common pattern for each method (all wrapped by step 5's `_guarded` helper, so rate limits
become `GitHubRateLimitError` and set `_rate_limited`):

```
fp = [issue["updated_at"], *slot_specific]
hit, value = self._cached(pr, slot, fp); if hit: return value
value = fetch()                      # exceptions propagate, nothing stored
if final(value): self._store(pr, slot, fp, value)
return value
```

`_cached` looks in `_fetched_results` then `_loaded_results`; hit iff `entry["fp"] == fp`
and `not is_expired(entry, now)`. `_store` writes
`{"fp", "value", "expires_at": new_expiry(now)}` into `_fetched_results[str(pr["number"])][slot]`.

| slot | extra fp | fetch | final when |
|---|---|---|---|
| `mergeable_state` | `pr["head_sha"]`, `self.base_tip(pr["base_branch"])` | `repo.get_pull(n).mergeable_state` | value not in `(None, "unknown")` |
| `ci` | `pr["head_sha"]` | `_fetch_ci_status(repo, pr["head_sha"], pr["head_branch"])` | runs non-empty and **every** run's `status == "completed"` (not the aggregate status) |
| `feedback` | `pr["updated_at"]` | `pr_manager._collect_pr_feedback(n, include_alerts=False)` (undecorated) | `unavailable` empty |
| `label_events` | — | `EventsMixin.get_issue_events(pr_manager, issue["number"], IssueEventType.LABELED)` | always |

- `_fetch_ci_status`: `runs = list(repo.get_workflow_runs(head_sha=head_sha)[:25])`; no runs →
  `(CIStatusData(run={}, jobs=[]), False)`; else `aggregate_conclusion(runs)` (reuse from
  `ci_results_manager`), build `RunData` from the first run like `get_latest_ci_status` does
  (`branch=branch`, `commit_sha=head_sha`, `run_ids` of all runs), `jobs=[]`.
  `final = all(r.status == "completed" for r in runs)` — `aggregate_conclusion` reports
  `("failure", "completed")` while other runs are still queued/in progress, so its status
  can't decide finality. **No** `run.jobs()` calls. Undecorated — errors propagate
  (so `lookup_failed` never occurs here).
- `feedback`: after the call, for each value in `feedback["unavailable"].values()`:
  `if (rl := to_rate_limit_error(v)) is not None: raise rl from v` (via `_guarded` → flag set).
  If `unavailable` is non-empty → return without storing. Store a JSON-safe copy with
  `unavailable={}` and `skipped={}` (both are empty when `include_alerts=False` and nothing failed).
  Why the undecorated `_collect_pr_feedback`: `_handle_github_errors` on `get_pr_feedback`
  returns `_empty_pr_feedback()` (empty `unavailable`) for an invalid PR number **and** for
  any non-rate-limit, non-auth exception raised outside the per-section `try` blocks. That
  default looks like "no feedback" and would be cached. Calling the undecorated body makes
  such an exception propagate, so nothing is stored (design rule 4). Existing
  `get_pr_feedback` tests must stay green unchanged.
- `label_events`: unbound call on `EventsMixin` with the `PullRequestManager` (it only needs
  `_get_repository` / `_get_issue_checked` from `BaseGitHubManager`); comment why — avoids a
  second manager.
- Pruning of closed PRs and expired slots is already done by step 5's `save()`.

## DATA

Stored slot values are plain JSON: `str`, `CIStatusData`, `PRFeedback` (with empty
`unavailable`/`skipped`), `list[EventData]`.

## Tests (`test_pull_requests_results.py`)

One test per fingerprint row — change it, assert re-fetch:
- `mergeable_state`: `head_sha` change; base tip change; issue `updated_at` change.
- `ci`: `head_sha` change; issue `updated_at` change.
- `feedback`: PR `updated_at` change; issue `updated_at` change (relabel invalidates feedback **and** CI).
- `label_events`: issue `updated_at` change.
- Expired slot → re-fetched.

Not final → re-fetched next run (new `load` from the saved file):
- mergeable `"unknown"` and `None`; CI `in_progress`; CI no runs; feedback with `unavailable["threads"]` = 500 error.
- CI with one run `completed`/`failure` and another `in_progress` on the same SHA → returned
  aggregate is `("failure", "completed")`, but the slot is **not** stored; next run re-fetches.

Errors / rate limits:
- `get_pull` raises 500 → propagates, slot not stored.
- `get_workflow_runs` raises rate limit → `GitHubRateLimitError`, `save()` writes nothing.
- `_collect_pr_feedback` returns `unavailable={"comments": rate-limit exc}` → `GitHubRateLimitError`, no file written.
- An exception raised outside the per-section `try` blocks (e.g. patch `_validate_pr_number`
  or the result assembly to raise a 500 `GithubException`): `get_pr_feedback` still returns
  `_empty_pr_feedback()` (decorator default, unchanged), but `cache.feedback(...)` propagates
  the exception and nothing is stored — after `save()`, a fresh `load` re-fetches feedback.
- `_fetch_ci_status` never calls `run.jobs()`.

Steady state (acceptance): save a fully populated cache for 3 PRs; age the snapshot past
60 s; new `load` + full `check_pr_health`-like pass (`find_pr`, `mergeable_state`,
`ci_status`, `feedback`, `label_events` per PR) with unchanged fingerprints → exactly
**2** repo calls (`get_pulls` + one `get_branch`) and no `get_pull` / `get_workflow_runs` /
`_collect_pr_feedback` / events calls. Count via Mock call counts.
