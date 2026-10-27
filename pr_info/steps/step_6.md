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

def _fetch_ci_status(repo: Repository, head_sha: str) -> CIStatusData: ...  # undecorated
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
| `ci` | `pr["head_sha"]` | `_fetch_ci_status(repo, head_sha)` | `run` non-empty and `run["status"] == "completed"` |
| `feedback` | `pr["updated_at"]` | `pr_manager.get_pr_feedback(n, include_alerts=False)` | `unavailable` empty |
| `label_events` | — | `EventsMixin.get_issue_events(pr_manager, issue["number"], IssueEventType.LABELED)` | always |

- `_fetch_ci_status`: `runs = list(repo.get_workflow_runs(head_sha=head_sha)[:25])`; no runs →
  `CIStatusData(run={}, jobs=[])` (not final); else `aggregate_conclusion(runs)` (reuse from
  `ci_results_manager`), build `RunData` from the first run like `get_latest_ci_status` does
  (`branch=pr head_branch` passed in, `commit_sha=head_sha`, `run_ids` of all runs), `jobs=[]`.
  **No** `run.jobs()` calls. Undecorated — errors propagate (so `lookup_failed` never occurs here).
- `feedback`: after the call, for each value in `feedback["unavailable"].values()`:
  `if (rl := to_rate_limit_error(v)) is not None: raise rl from v` (via `_guarded` → flag set).
  If `unavailable` is non-empty → return without storing. Store a JSON-safe copy with
  `unavailable={}` and `skipped={}` (both are empty when `include_alerts=False` and nothing failed).
  Note in a comment: the decorator default of `get_pr_feedback` only fires for an invalid PR
  number, which cannot come from the snapshot.
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

Errors / rate limits:
- `get_pull` raises 500 → propagates, slot not stored.
- `get_workflow_runs` raises rate limit → `GitHubRateLimitError`, `save()` writes nothing.
- `get_pr_feedback` returns `unavailable={"comments": rate-limit exc}` → `GitHubRateLimitError`, no file written.
- `_fetch_ci_status` never calls `run.jobs()`.

Steady state (acceptance): save a fully populated cache for 3 PRs; age the snapshot past
60 s; new `load` + full `check_pr_health`-like pass (`find_pr`, `mergeable_state`,
`ci_status`, `feedback`, `label_events` per PR) with unchanged fingerprints → exactly
**2** repo calls (`get_pulls` + one `get_branch`) and no `get_pull` / `get_workflow_runs` /
`get_pr_feedback` / events calls. Count via Mock call counts.
