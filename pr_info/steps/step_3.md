# Step 3 — Schema bookkeeping: `cached_at` sidecar + `version` write

**Goal:** Complete the schema deliverables required by the acceptance criteria —
maintain the top-level `cached_at` sidecar map and stamp a `version` on every
save. Pure bookkeeping; independent of the Step 2 fix mechanism. One commit.
Depends on Steps 1–2.

## WHERE
- `src/mcp_workspace/github_operations/issues/cache.py`
  (`_fetch_and_merge_issues` full-refresh branch, `get_all_cached_issues` step 5)
- `tests/github_operations/test_issue_cache.py` (new tests)

## WHAT

### `cache.py` — module constant
```python
CACHE_SCHEMA_VERSION: int = 1
```
Written on save; **not** branched on (migration keys off `updates_covered_through`
absence, per Step 2).

### `cache.py` — `cached_at` maintenance
- On **full refresh** (where `cache_data["issues"] = {}` is set in
  `_fetch_and_merge_issues`): also reset `cache_data["cached_at"] = {}`.
- On **merge** (in `get_all_cached_issues`, after issues are updated): stamp
  `now` for every issue number written this refresh (both `fresh_dict` and
  `additional_dict` keys).

### `cache.py` — `version` write
In `get_all_cached_issues` before save: `cache_data["version"] =
CACHE_SCHEMA_VERSION`.

## HOW / integration
- `cache_data["cached_at"]` is guaranteed to be a dict after Step 1's
  `_load_cache_file`, so `.update()` / assignment is safe without guards.
- Use `format_for_cache(now)` for the timestamp value (consistent with
  `last_checked`).
- No new function; a couple of inline lines in the existing merge/save region.

## ALGORITHM — merge region (delta in `get_all_cached_issues`)
```
now_str = format_for_cache(now)
for num in fresh_dict:            cache["cached_at"][num] = now_str
for num in additional_dict:       cache["cached_at"][num] = now_str
cache["version"] = CACHE_SCHEMA_VERSION
# (full refresh already reset cache["cached_at"] = {} inside _fetch_and_merge_issues)
```

## DATA
- `cached_at`: `Dict[str, str]` mapping issue-number string → ISO timestamp of
  last write; rebuilt from scratch on full refresh, incrementally stamped on
  incremental refresh.
- `version`: `int` persisted in every saved cache file.

## TESTS (write first — TDD)
New `TestCacheBookkeeping` class:
1. `test_version_written_on_save` — after any refresh, saved cache has
   `version == CACHE_SCHEMA_VERSION`.
2. `test_cached_at_stamped_for_merged_issues` — incremental refresh returning
   issue #N ⇒ saved `cached_at["N"] == last_checked` timestamp (== `now`).
3. `test_cached_at_rebuilt_on_full_refresh` — seed `cached_at` with a stale
   entry for an issue no longer returned ⇒ after full refresh that stale entry
   is gone and only currently-returned issues are present.
4. `test_cached_at_includes_additional_issues` — an `additional_issues` number
   gets a `cached_at` stamp.

## CHECKS (before commit)
```
mcp__tools-py__run_pylint_check
mcp__tools-py__run_pytest_check(extra_args=["-n","auto","-m",
  "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])
mcp__tools-py__run_mypy_check
```

## LLM PROMPT
> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`. Implement Step 3
> only (Steps 1–2 are already merged), following TDD: write the
> `TestCacheBookkeeping` tests first, watch them fail, then implement. Add a
> `CACHE_SCHEMA_VERSION = 1` module constant to
> `src/mcp_workspace/github_operations/issues/cache.py`; reset
> `cache_data["cached_at"] = {}` on full refresh (alongside the existing
> `issues = {}` reset in `_fetch_and_merge_issues`); stamp `format_for_cache(now)`
> into `cached_at` for every merged issue number (fresh + additional) in
> `get_all_cached_issues`; and write `cache_data["version"] =
> CACHE_SCHEMA_VERSION` before save. Do **not** branch on `version`, add a
> public parameter, or touch `IssueData`. Use MCP tools for all file and check
> operations. Run pylint, pytest (not-integration exclusion, `-n auto`), and
> mypy; fix until all pass, then stop. State "All CLAUDE.md requirements
> followed".
