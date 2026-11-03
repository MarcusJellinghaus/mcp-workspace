# Step 3 — `PullRequestCache.alerts()` slot, tests and docs

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_3.md` exactly.
> TDD: write `test_pull_requests_alerts.py` first, then the code, then the docs.
> Run pylint, pytest (`-n auto`) and mypy; all must pass. Format, then make exactly one commit.

## Precondition

`alert_skip_status` exists in `_pr_feedback_sources.py` (step 1) and
`tests/github_operations/caching/_pr_cache_test_helpers.py` exists (step 2). If either is
missing, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/github_operations/pr_types.py`
- `src/mcp_workspace/github_operations/caching/pull_requests.py`
- Create `tests/github_operations/caching/test_pull_requests_alerts.py`
- `README.md`, `docs/release-notes.md`

## WHAT

`pr_types.py`, directly after `AlertData`:

```python
class AlertsResult(TypedDict):
    """Code-scanning alerts of a PR head, as returned by ``PullRequestCache.alerts()``."""

    alerts: list[AlertData]
    skipped: Optional[int]  # HTTP status (403/404) when alerts could not be checked
    final: bool  # every CI run on head_sha completed; always True on a stored hit
```

`pull_requests.py`:

```python
def alerts(self, pr: OpenPullRequest, issue: IssueData) -> AlertsResult:
    """Return the PR head's open code-scanning alerts; stored once CI on the head is final.

    Act only on ``final: True``. While any CI run on ``head_sha`` is not completed
    (or there are no runs, or a run is stuck in ``waiting`` / ``action_required``)
    no alerts request is made and ``{"alerts": [], "skipped": None, "final": False}``
    is returned — ``final`` never becomes True for such a head. A 403/404 that is
    not a rate limit is stored as ``skipped``.

    Raises:
        GitHubRateLimitError: If fetching hit a rate limit; ``save()``
            then becomes a no-op.
    """  # noqa: DOC502  # other fetch errors propagate unchanged
    return self._guarded(self._alerts, pr, issue)

def _alerts(self, pr: OpenPullRequest, issue: IssueData) -> AlertsResult: ...
```

Place `alerts()` after `ci_status()` and `_alerts` after `_ci_status`.

## HOW

- Imports in `pull_requests.py`: `from .. import _pr_feedback_sources` and
  `AlertsResult` from `..pr_types`. Call the fetcher and classifier through the module
  (`_pr_feedback_sources.fetch_code_scanning_alerts(...)`), as `pr_feedback_mixin.py` does,
  so one patch path works for both callers.
- `_repository()` is called **outside** the `try`: the fetcher returns `[]` for an
  unavailable repository, which must never be stored as "no alerts".
- `except Exception` needs `# pylint: disable=broad-exception-caught` with a short reason
  (classified, then re-raised).
- Module docstring: "four result slots" → five, add ``alerts``; change "fetch errors
  propagate without storing anything" to say a 403/404 alerts skip is stored.
- No `PRS_CACHE_VERSION` bump; `feedback()` unchanged.

## ALGORITHM

```
fp = [issue["updated_at"], pr["head_sha"]]
if alerts hit for fp: return it
self._ci_status(pr, issue); if no "ci" hit for fp: return {"alerts": [], "skipped": None, "final": False}
self._repository()
try: result = {alerts: fetch(self._pr_manager, pr["number"]), skipped: None, final: True}
except e: status = alert_skip_status(e); if None: raise; result = {alerts: [], skipped: status, final: True}
self._store(pr, "alerts", fp, result); return result
```

## DATA

`AlertsResult`; stored entry `{"fp": fp, "value": AlertsResult, "expires_at": ...}` under
`results[str(pr_number)]["alerts"]`.

## Tests (write first) — `test_pull_requests_alerts.py`

Use helpers from `._pr_cache_test_helpers`. Patch
`mcp_workspace.github_operations._pr_feedback_sources.fetch_code_scanning_alerts`
(`unittest.mock.patch` / `monkeypatch`) in every test that reaches the fetch. `_Env`'s
default runs are one completed `success` run, i.e. final CI. Not-stored assertions check
`"alerts" not in _read()["results"].get("5", {})` — the `"ci"` slot is stored in the same
run. Use `make_retry_error` from `tests/github_operations/conftest.py`.

1. **Fingerprint:** same fp → second run is a hit (fetcher called once, with
   `(env.manager, 5)`); new `head_sha` → refetch; new `issue.updated_at` → refetch.
2. **JSON round-trip** (parametrized): fetcher returns two alerts (`line=12` and
   `line=None`) / raises `GithubException(403, ...)`. Second run's hit `==` first run's
   result; skip case has `skipped == 403`, `final is True`.
3. **404 skip stored:** `UnknownObjectException(404, ...)` → `skipped == 404`, slot stored.
4. **Not final** (parametrized: `[_run("in_progress", None)]`,
   `[_run("completed", "failure"), _run("in_progress", None)]`, `[]`) → result
   `{"alerts": [], "skipped": None, "final": False}`, fetcher not called, alerts slot not
   stored; a second run calls `get_workflow_runs` again.
5. **Skipped/neutral run is final** (parametrized `"skipped"`, `"neutral"`):
   `[_run(), _run("completed", conclusion)]` → `final: True`, stored.
6. **CI hit from disk:** run 1 calls `ci_status()` only and saves; run 2 calls only
   `alerts()` → stored with `final: True`, `get_workflow_runs.call_count == 1`.
7. **Alerts hit while CI expired:** run 1 `alerts()`; `_expire_slot(5, "ci")`; run 2
   `alerts()` → `get_workflow_runs.call_count == 1`.
8. **Same run `ci_status()` then `alerts()`** → `get_workflow_runs.call_count == 1`.
9. **Rate limit** (parametrized: `_rate_limit()`, `make_retry_error(403)`,
   `RetryError()` with unknown status): `cache.find_pr("5-x")` first, then
   `alerts()` raises `GitHubRateLimitError`; after `save()`, `not _path().exists()`.
10. **Raises, not stored** (parametrized: `_server_error()`, `make_retry_error(500)`):
    `find_pr` first; `alerts()` raises the original type; after `save()` the alerts slot
    is not stored.
11. **Repository unavailable:** run 1 `ci_status()` + save (CI hit on disk); then
    `env.manager._get_repository.return_value = None`; run 2 `alerts()` raises
    `RuntimeError`; alerts slot not stored; fetcher not called.
12. **CI failure inside `alerts()`:** `env.repo.get_workflow_runs.side_effect = _server_error()`
    → raises `GithubException`; fetcher not called.
13. **Slot-only run:** `_one_run(env, "alerts", ...)` without `find_pr` →
    `"alerts" in _read()["results"]["5"]`.
14. **Steady state + pruning:** `_Env([1, 2, 3])`; full pass = `find_pr`, `ci_status`,
    `alerts` per PR, then `save()`. After `_age_snapshot()` and `reset_mock()`s, a second
    pass → `len(env.repo.method_calls) == 1` (only `get_pulls`, for the aged snapshot;
    no `base_tip` call because `mergeable_state` is not part of this pass),
    `get_workflow_runs` not called, fetcher not called. Then drop PR 3 from `env.repo.get_pulls.return_value`, `_age_snapshot()`,
    run a pass over PRs 1–2 → `"3" not in _read()["results"]`.

The existing `feedback()` tests (no code-scanning request, `include_alerts=False`) must
still pass.

## Docs

- `README.md` "GitHub caches":
  - "What is cached" — add after the CI status row:
    `| Code-scanning alerts | issue updated_at, PR head_sha | any CI run not completed, no runs (no alerts request is made) |`
  - Validity bullet "Not-final results are returned but never stored. Errors are never
    stored." → "... Errors are never stored, except a 403/404 on code-scanning alerts
    (alerts could not be checked), which is stored as a skip."
- `docs/release-notes.md`: in the `caching.pull_requests.PullRequestCache` line add
  `alerts(pr, issue) -> AlertsResult` after `ci_status(pr, issue)`; add a bullet:
  `pr_types.AlertsResult` — `TypedDict`: `alerts: list[AlertData]`, `skipped: int | None`,
  `final: bool`; act only on `final: True`.
