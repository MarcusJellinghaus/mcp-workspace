# Step 2 — Fetch additional issues only when needed; keep session issues on full refresh

## LLM prompt
Read `pr_info/steps/summary.md`, then implement this step (`pr_info/steps/step_2.md`)
only. Write the tests first, then the implementation. Run pylint, pytest
(`-n auto`) and mypy; all must pass. Run format_code, then make exactly one commit.

## WHERE
- `src/mcp_workspace/github_operations/issues/cache.py` — `_fetch_additional_issues`,
  `get_all_cached_issues` (steps 2, 3, 5b, 5c)
- `tests/github_operations/issues/test_cache_additional.py`
- `tests/github_operations/issues/test_cache_full_refresh.py`

## WHAT
```python
def _fetch_additional_issues(
    issue_manager: "IssueManager",
    additional_issue_numbers: list[int],
    repo_name: str,
    cache_data: CacheData,
    now: datetime,
    cache_refresh_minutes: int,
) -> set[str]
```
Returns the keys actually fetched. Writes each fetched issue into
`cache_data["issues"][key]` and stamps `cache_data["cached_at"][key] = format_for_cache(now)`
in place.

Helper (private, same module):
```python
def _needs_fetch(cache_data: CacheData, key: str, now: datetime, cache_refresh_minutes: int) -> bool
```
True when `key` not in `issues`, or `cached_at[key]` is missing, unparseable
(`ValueError` from `parse_iso_timestamp`), or older than `cache_refresh_minutes`.

## HOW
- In `get_all_cached_issues`, move `now = now_utc()` above step 2 (it is reused
  by step 3 and later steps; there must be only one `now_utc()` call).
- Use `cache_data.setdefault("cached_at", {})` before stamping (mocked loads may
  omit the key).
- Step 2 keeps the returned `fetched_keys: set[str]` for step 3 (next step).
- Next to `issues_snapshot`, add `cached_at_snapshot = dict(cache_data.get("cached_at", {}))`
  — taken after step 2, so fetched keys already carry the new stamp.
- Remove the old `additional_dict` merges in steps 2 and 5b.

## ALGORITHM
```
# _fetch_additional_issues
for num in numbers: key = str(num)
    if not _needs_fetch(...): continue
    try: issue = issue_manager.get_issue(num)
    except Exception: warn (mention "using cached version" if key cached); continue
    if issue["number"] != 0: issues[key] = issue; cached_at[key] = now_str; fetched.add(key)
return fetched
```
```
# step 5b (after cache_data["issues"].update(fresh_dict))
for num in additional_issues or []: key = str(num)
    if key in fresh_dict or key not in issues_snapshot: continue
    cache_data["issues"][key] = issues_snapshot[key]
    if key in cached_at_snapshot: cache_data["cached_at"][key] = cached_at_snapshot[key]
# step 5c: stamp now only for fresh_dict keys (drop the additional_dict loop)
```

## DATA
- Deleted (404 → `number == 0`) and transferred (`IssueIdentityMismatchError`)
  issues are never cached, so `_needs_fetch` is True on every call (unchanged).
- A failed fetch of a cached-but-stale issue keeps the cached copy and its old
  `cached_at` (not re-stamped).
- Step-4 exception path: restore `cache_data["cached_at"] = cached_at_snapshot`
  next to the existing `issues_snapshot` restore (both snapshots carry the
  step-2 fetches). Persisting `fetched_keys` on this path is added in step 3,
  which introduces the reload-and-merge save.
- Docstrings: fix `_fetch_additional_issues` (no longer claims "doesn't re-fetch";
  describe the fetch rule and return value) and the `additional_issues` arg of
  `get_all_cached_issues` (fetched only when not cached or stale; put back after
  a full refresh).

## Tests
`test_cache_additional.py`:
- Replace `test_additional_issues_always_refreshed` with:
  - cached with fresh `cached_at` → `get_issue` not called, cached issue returned;
  - cached with `cached_at` older than `cache_refresh_minutes` → fetched, re-stamped with `now`;
  - cached with missing `cached_at` → fetched;
  - cached with unparseable `cached_at` → fetched.
- `get_issue` returns empty issue (`number == 0`) → not cached, fetched again on
  the next call (call twice with a real tmp cache file or a stateful load mock).
- `get_issue` raises for a stale cached issue → cached copy returned, its
  `cached_at` unchanged in saved data.
- Acceptance: N cached open session issues with fresh `cached_at` → zero
  `get_issue` calls on an incremental refresh.
- Existing tests (`test_additional_issues_fetched_and_cached`, API failure,
  empty list) still pass.

`test_cache_full_refresh.py`:
- Full refresh (`last_full_refresh` older than threshold) with closed session
  issue `#123` cached (fresh `cached_at`), `state=open` list not containing it →
  `#123` in result and saved data, `cached_at["123"]` equals the old value,
  `get_issue` not called.
- Session issue that is in `fresh_dict` → saved entry is the `fresh_dict`
  version, not the cached one, stamped with `now`.
- Non-session issues missing from the open list are still dropped.
