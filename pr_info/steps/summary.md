# Summary — PullRequestCache: `alerts()` slot for code-scanning alerts (#374)

## Goal

mcp_coder's `check_pr_health` (MarcusJellinghaus/mcp_coder#1342) needs a PR's open
code-scanning alerts and reads PR data only through `PullRequestCache`. Add a fifth
fingerprinted result slot, `"alerts"`, exposed as `PullRequestCache.alerts(pr, issue)`.
`feedback()` stays alerts-free.

## Architectural / design changes

- **New slot `"alerts"`** in `caching/pull_requests.py`, following the `ci_status()` /
  `_ci_status` pattern: public method wrapped in `_guarded`, private `_alerts` body,
  `_cached` / `_store` for storage.
- **Fingerprint** `[issue.updated_at, pr["head_sha"]]` — the same as the `"ci"` slot.
  Alerts change only when a new analysis runs, and an analysis runs per commit.
- **CI gate.** A result is stored only once every CI run on `head_sha` has completed
  (CodeQL runs count as CI runs). Until then GitHub still returns the previous commit's
  alerts, so `_alerts` makes **no alerts request** and returns
  `{"alerts": [], "skipped": None, "final": False}`. Finality is read from the `"ci"`
  slot after calling `_ci_status` (the slot is only stored when all runs completed) —
  `CIStatusData` cannot decide it.
- **Order inside `_alerts`:** alerts hit → `_ci_status` → CI-final check →
  `_repository()` → fetch → store. The alerts hit check comes first because the `"ci"`
  and `"alerts"` entries expire independently.
- **New return type** `AlertsResult` (TypedDict in `pr_types.py`):
  `{"alerts": list[AlertData], "skipped": int | None, "final": bool}`. JSON-safe; a
  cache hit equals the fresh fetch. Not exported from `github_operations/__init__.py`.
- **Shared pure classifier** `alert_skip_status(exc) -> int | None` in
  `_pr_feedback_sources.py`: the status (403/404) for a non-rate-limit skip, else `None`.
  - `_collect_pr_feedback` routes on it (skip → `skipped["alerts"]`, else
    `unavailable["alerts"]`) — behaviour unchanged.
  - `_alerts` stores a skip result, or re-raises; `_guarded` turns rate limits into
    `GitHubRateLimitError` (`save()` becomes a no-op).
- **A 403/404 skip is stored** — the one error-derived result the cache keeps.
- **No `PRS_CACHE_VERSION` bump:** `_valid_results` accepts any slot name, and older code
  keeps unknown slots on `save()`.

## Files

| Action | Path |
|---|---|
| Modify | `src/mcp_workspace/github_operations/_pr_feedback_sources.py` — `alert_skip_status`, module docstring |
| Modify | `src/mcp_workspace/github_operations/pr_feedback_mixin.py` — use classifier, drop `format_rate_limit_error` import |
| Modify | `src/mcp_workspace/github_operations/pr_types.py` — `AlertsResult` |
| Modify | `src/mcp_workspace/github_operations/caching/pull_requests.py` — `alerts()`, `_alerts`, module docstring |
| Modify | `tests/github_operations/test_pr_feedback_mixin.py` — `alert_skip_status` tests |
| Create | `tests/github_operations/caching/_pr_cache_test_helpers.py` — shared helpers moved out of the results tests |
| Modify | `tests/github_operations/caching/test_pull_requests_results.py` — import helpers |
| Create | `tests/github_operations/caching/test_pull_requests_alerts.py` — alerts slot tests |
| Modify | `README.md` — "GitHub caches" section |
| Modify | `docs/release-notes.md` — `PullRequestCache` API line |

## Steps

1. [step_1.md](./step_1.md) — `alert_skip_status` classifier; `_collect_pr_feedback` uses it.
2. [step_2.md](./step_2.md) — move PR-cache test helpers into `_pr_cache_test_helpers.py` (pure refactor).
3. [step_3.md](./step_3.md) — `AlertsResult`, `PullRequestCache.alerts()`, tests, docs.

Each step is one commit: tests + implementation + pylint / pytest (`-n auto`) / mypy passing.
