# Summary: `caching/` subpackage — fingerprint-based PR cache and branch-lookup cache (#361)

## Goal

Cut the per-minute GitHub traffic of mcp_coder's `vscodeclaude status` / `launch`:

- `check_pr_health` makes ~9 `core` + 2 GraphQL calls **per open PR** on every run.
- `get_branch_with_pr_fallback` costs up to ~30 calls per **miss** (no branch), every minute.

Every command is a new process, so only a **disk** cache helps. A cached result stays
valid while the **fingerprint** of what it depends on is unchanged; a per-entry maximum
age is only a safety net. Steady state target: ≈ 2 `core` calls per repo per run
(open-PR list + base-branch tip), plus #360's one `get_repo` per process.

## Precondition

#360 must be merged into `main` (and this branch rebased onto it). #361 moves #360's
`_save_cache_file` (now in `issues/_cache_io.py`) and uses
`get_pr_feedback(include_alerts=False)`. Step 1 checks this and writes
`pr_info/.blocked.txt` if it does not hold.

## Architectural / design changes

### New subpackage `mcp_workspace/github_operations/caching/`

```
caching/
  __init__.py       # docstring only — must stay import-free (cycle guard, see below)
  errors.py         # GitHubRateLimitError + rate_limit_guard()
  _store.py         # generic JSON load/save, cache file paths
  branches.py       # BranchLookupCache + invalidate_branch_entry()
  pull_requests.py  # PullRequestCache + private undecorated PR fetchers
```

Files live next to the existing issue cache:
`<app-data>/mcp_coder/coordinator_cache/<cache_safe_name>.{issues,prs,branches}.json`.

### Design rules (apply to both new caches)

1. **Run-scoped object per repo.** `X.load(manager)` → query methods → `save()` once.
2. **Fingerprints decide validity.** Every entry stores `fp` (a JSON list) and
   `expires_at`. A lookup is a hit only if `fp` matches **and** `expires_at` is in the
   future. `expires_at = now + MAX_AGE * uniform(0.75, 1.0)` so entries written in the
   same run are rechecked spread out over later runs. `MAX_AGE = 6 h` (one constant).
3. **Not-final results are returned but never stored** (mergeable `unknown`/`null`,
   CI not completed / no runs / lookup failed, feedback with any `unavailable` entry).
4. **Errors are never cached.** Fetchers are undecorated and raise; a raised error
   propagates out of the query method and nothing is stored for it.
5. **Rate limits:** one rule — `format_rate_limit_error(exc) is not None`. Every public
   cache method converts such an error into `GitHubRateLimitError` (via
   `rate_limit_guard()`), and sets a `_rate_limited` flag that makes `save()` a no-op.
   The flag matters because mcp_coder's `check_pr_health` catches `Exception` per issue.
6. **Merge on save = "file on disk + my fetched entries, mine win".** Each object keeps
   what it *loaded* separate from what it *fetched* this run. `save()` reloads the file,
   drops expired entries, overlays only this run's fetched entries, applies this run's
   deletes, and writes. Untouched loaded entries are never written back, so a deleted
   entry (closed PR, expired, invalidated) can't be resurrected, and two concurrent
   writers both keep their entries. No file lock, no tombstones, no timestamp compare.
7. **`version` checked only for `.prs.json` / `.branches.json`.** Missing, corrupt or
   mismatched → empty cache → rebuild, never raises. `.issues.json` keeps its current
   self-healing behaviour (version written, not branched on).
8. **`_store.py` is shape-agnostic**: load/save JSON + path helper only. Each cache does
   its reload-and-merge inline in its own `save()`.

### PR cache (`pull_requests.py`)

- **Layer 1 – open-PR snapshot**: undecorated `repo.get_pulls(state="open")`, parsed
  field by field (never `_pr_to_data`, which lazy-loads `mergeable*`/`merged`).
  `find_pr(branch)` matches `head_label == "<owner>:<branch>"`. Snapshot also stores the
  base-branch tip SHAs (`repo.get_branch(base)`, once per distinct base). Within
  `DUPLICATE_PROTECTION_SECONDS` of the snapshot's `fetched_at`, neither is re-fetched.
  On save, the newer snapshot wins whole; layer-2 entries for PRs not in it are pruned.
- **Layer 2 – one entry per PR, four slots** (every `fp` starts with the issue's
  `updated_at`, so a relabel invalidates everything for that PR):

  | slot | fp (after issue `updated_at`) | fetch | not final |
  |---|---|---|---|
  | `mergeable_state` | `head_sha`, base tip SHA | `repo.get_pull(n).mergeable_state` | `unknown` / `None` |
  | `ci` | `head_sha` | `repo.get_workflow_runs(head_sha=…)` + `aggregate_conclusion`, no jobs | any run not `completed`, no runs |
  | `feedback` | PR `updated_at` | undecorated `_collect_pr_feedback(n, include_alerts=False)` (body of `get_pr_feedback`) | any `unavailable` |
  | `label_events` | — | `get_issue_events(n, LABELED)` | — |

- Branch with no open PR: `check_pr_health` keeps calling live `get_latest_ci_status`
  (mcp_coder side, #1300).

### Branch-lookup cache (`branches.py`)

- New raising core `IssueBranchManager.resolve_branch_for_issue(issue_number) ->
  BranchLookup` (`found` / `not_found` / `ambiguous`). `get_branch_with_pr_fallback`
  becomes a thin decorated wrapper around it — no duplicated resolution logic.
  The core treats `_query_linked_branches(...) is None` and every non-404 error as an
  error (raises); only 404 in the closed-PR branch probe means "branch gone".
- `BranchLookupCache.lookup(issue: IssueData)`: fp = `[issue updated_at]`.
- `invalidate_branch_entry(repo_identifier, issue_number)`: load → delete → save.
  Called from `create_remote_branch_for_issue` on success via a **function-local import**
  (avoids the load-time cycle `issues/_cache_io → caching/_store`,
  `caching/branches → issues`).

### Issue cache changes

- `get_all_cached_issues` / `_fetch_additional_issues`: a rate-limit error now raises
  `GitHubRateLimitError` and saves nothing. Other errors keep today's stale-return path.
- `_save_cache_file` moves to `caching/_store.py` (re-imported by `issues/_cache_io.py`;
  underscore names stay importable from `issues/__init__` until mcp_coder#1300 ships).
- New narrow public `get_issue_cache_last_checked(repo_identifier) -> datetime | None`
  replacing mcp_coder's use of `_get_cache_file_path` + `_load_cache_file`.

### Public API additions

- `mcp_workspace.github_operations.GitHubRateLimitError`
- `mcp_workspace.github_operations.issues.get_issue_cache_last_checked`
- `mcp_workspace.github_operations.caching.branches.BranchLookupCache`, `invalidate_branch_entry`
- `mcp_workspace.github_operations.caching.pull_requests.PullRequestCache`
- `IssueBranchManager.resolve_branch_for_issue`, `BranchLookup`

No tach / import-linter changes: everything stays inside `github_operations`.

## Files created / modified

### Created
- `src/mcp_workspace/github_operations/caching/__init__.py`
- `src/mcp_workspace/github_operations/caching/errors.py`
- `src/mcp_workspace/github_operations/caching/_store.py`
- `src/mcp_workspace/github_operations/caching/branches.py`
- `src/mcp_workspace/github_operations/caching/pull_requests.py`
- `tests/github_operations/caching/__init__.py`
- `tests/github_operations/caching/conftest.py`
- `tests/github_operations/caching/test_errors.py`
- `tests/github_operations/caching/test_store.py`
- `tests/github_operations/caching/test_branches.py`
- `tests/github_operations/caching/test_pull_requests_snapshot.py`
- `tests/github_operations/caching/test_pull_requests_results.py`
- `tests/github_operations/issues/test_cache_rate_limit.py`
- `tests/github_operations/issues/test_branch_manager_resolve.py`

### Modified
- `src/mcp_workspace/github_operations/__init__.py` — export `GitHubRateLimitError`
- `src/mcp_workspace/github_operations/issues/cache.py` — rate-limit raise
- `src/mcp_workspace/github_operations/issues/_cache_io.py` — use `_store`; `get_issue_cache_last_checked`
- `src/mcp_workspace/github_operations/issues/__init__.py` — export `get_issue_cache_last_checked`, `BranchLookup`, `BranchLookupError`; keep underscore aliases
- `src/mcp_workspace/github_operations/issues/branch_manager.py` — `BranchLookup`, `resolve_branch_for_issue`, wrapper, invalidation hook
- `src/mcp_workspace/github_operations/issues/linked_branches_mixin.py` — raise `GitHubRateLimitError` on a GraphQL `RATE_LIMITED` body in `_query_linked_branches`
- `src/mcp_workspace/github_operations/pr_feedback_mixin.py` — undecorated `_collect_pr_feedback`; `get_pr_feedback` wraps it
- `tests/github_operations/issues/test_cache_io.py` — patch targets if the temp-file tests patch the moved helper
- `tests/github_operations/issues/test_branch_manager_pr_fallback_a.py`, `_b.py` — mock `_pattern_lookup` instead of `_search_branches_by_pattern`, `_fetch_linked_branches` instead of `get_linked_branches`
- `README.md` — caches section
- `docs/release-notes.md` — new exception, issue-cache rate-limit change, underscore-export deprecation

## Steps

1. `GitHubRateLimitError` + issue cache raises on rate limit — [step_1.md](step_1.md)
2. `_store.py` + `get_issue_cache_last_checked` — [step_2.md](step_2.md)
3. Raising branch-resolution core in `IssueBranchManager` — [step_3.md](step_3.md)
4. `BranchLookupCache` + invalidation — [step_4.md](step_4.md)
5. `PullRequestCache` layer 1 (open-PR snapshot, base tips, save/merge) — [step_5.md](step_5.md)
6. `PullRequestCache` layer 2 (four fingerprinted slots) — [step_6.md](step_6.md)
7. README + release notes — [step_7.md](step_7.md)
