# Summary — #360 Reduce GitHub traffic

Quick wins that cut the per-minute API traffic of `coordinator --all`,
`vscodeclaude status` and `vscodeclaude launch --cleanup`, without the new
cache subpackage (#361).

## Architectural / design changes

| Area | Before | After |
|---|---|---|
| `additional_issues` (`issues/cache.py`) | `get_issue` for every number on every call, before duplicate protection | `get_issue` only when the issue is not cached, or its `cached_at` is missing, unparseable or older than `cache_refresh_minutes` |
| `cached_at` stamping | Stamped for fresh + all additional issues after the refresh | Stamped **at fetch time** for individually fetched issues and for `fresh_dict` in step 5c; never for issues put back from the cache |
| Full refresh + session issues | Step 5b re-applied the always-fetched additional issues, overwriting `fresh_dict` | Step 5b puts back session keys **not in `fresh_dict`** from the issue and `cached_at` snapshots, so closed session issues stay in the result with their old `cached_at` |
| Duplicate-protection and list-failure paths | Fetched additional issues returned but not saved | When something was fetched: `_save_fetched_issues` reloads the file, merges only `issues[k]`/`cached_at[k]` for the fetched keys, saves. Timestamps (`last_checked`, `updates_covered_through`, `last_full_refresh`) are never touched |
| `_save_cache_file` | Fixed temp name `x.issues.tmp` shared by all writers | Unique `tempfile.mkstemp` in the same directory, temp file deleted on failure, `os.replace` retried once after a short delay |
| Repository lookup (`base_manager.py`) | `get_repo` once per manager instance | Per-process cache of `(raw_data, raw_headers)` keyed by `(api_base_url, sha256(token), full_name.lower())`; each manager rebuilds its own object with `self._github_client.create_from_raw_data(...)`, so the `Repository` object and its Requester are never shared |
| Token keying | `_cached_login` computes its key inline | Shared `_token_key(base_url, token)` helper used by the login and repository caches |
| `get_pr_feedback` | Always fetches code-scanning alerts | `include_alerts: bool = True`; when `False`: no request, `alerts: []`, nothing in `unavailable` or `skipped` |
| `IssueBranchManager.__init__` | `(project_dir, repo_url)` | `(project_dir, repo_url, github_token)` |
| Repo identifier | Only private `_repo_identifier` | Public read-only `repo_identifier` property; outside readers switched to it |

Design rules:
- One mechanism for additional issues: fetched entries are written into
  `cache_data` with their stamp immediately; every later path (incremental,
  full refresh, duplicate protection) only copies them.
- Process-level caches store plain data, never PyGithub objects (thread
  safety, #359 per-client request wrapper).
- Failures are never cached (repository cache, deleted/transferred issues).
- No locks: a simultaneous miss costs at most one extra `get_repo`.

## Files to modify

| File | Step | Change |
|---|---|---|
| `src/mcp_workspace/github_operations/issues/cache.py` | 1, 2, 3 | `_save_cache_file`; `_fetch_additional_issues`; `get_all_cached_issues` |
| `src/mcp_workspace/github_operations/base_manager.py` | 4, 7 | `_token_key`, `_repository_cache`, `clear_repository_cache`, `_get_repository`; `repo_identifier` property |
| `src/mcp_workspace/github_operations/__init__.py` | 4 | Export `clear_repository_cache` |
| `src/mcp_workspace/github_operations/pr_feedback_mixin.py` | 5 | `include_alerts` parameter |
| `src/mcp_workspace/github_operations/issues/branch_manager.py` | 6 | `github_token` parameter |
| `src/mcp_workspace/server.py` | 7 | Use `repo_identifier` (lines ~208, ~944) |
| `src/mcp_workspace/github_operations/_permission_probes.py` | 7 | Use `repo_identifier` (line ~206) |
| `src/mcp_workspace/github_operations/issues/base_branch_trust.py` | 7 | Use `repo_identifier` (line ~104) |
| `tests/conftest.py` | 4 | Autouse fixture calling `clear_repository_cache()` |
| `tests/github_operations/issues/test_cache_io.py` | 1 | Temp-name, cleanup, retry tests |
| `tests/github_operations/issues/test_cache_additional.py` | 2, 3 | Fetch-rule tests; rewrite `test_additional_issues_always_refreshed`; duplicate-protection save tests |
| `tests/github_operations/issues/test_cache_full_refresh.py` | 2 | Closed session issues survive full refresh |
| `tests/github_operations/test_base_manager.py` | 4, 7 | Repository cache tests; `repo_identifier` tests |
| `tests/github_operations/test_pr_feedback_mixin.py` | 5 | `include_alerts=False` tests |
| `tests/github_operations/issues/test_branch_manager_create.py` | 6 | Constructor token test |

No new modules or folders. Unchanged on purpose: `checks/pr_feedback.py`
(keeps default alerts), `pr_manager.py` (internal `_repo_identifier` reads),
`PullRequestManager` constructor.

## Steps

1. Unique temp file names in `_save_cache_file`
2. Fetch additional issues only when needed; put back session issues after a full refresh
3. Save fetched additional issues on the duplicate-protection and list-failure paths
4. Per-process `Repository` raw-data cache
5. Optional code-scanning alerts in `get_pr_feedback`
6. `IssueBranchManager` accepts `github_token`
7. Public `repo_identifier` property

Each step = one commit: tests first, then implementation, then
`run_pylint_check`, `run_pytest_check` (`extra_args: ["-n", "auto"]`),
`run_mypy_check`, `run_format_code` — all passing.
