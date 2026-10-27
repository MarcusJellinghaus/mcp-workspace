# Step 3 — Save fetched additional issues on the duplicate-protection and list-failure paths

## LLM prompt
Read `pr_info/steps/summary.md`, then implement this step (`pr_info/steps/step_3.md`)
only. Step 2 must be done: `_fetch_additional_issues` returns `set[str]` of
fetched keys. If it does not, write one line to `pr_info/.blocked.txt` and stop.
Write the tests first, then the implementation. Run pylint, pytest (`-n auto`)
and mypy; all must pass. Run format_code, then make exactly one commit.

## WHERE
- `src/mcp_workspace/github_operations/issues/cache.py` — new private helper;
  step 3 (duplicate protection branch) and the step-4 `except` branch of
  `get_all_cached_issues`
- `tests/github_operations/issues/test_cache_additional.py`

## WHAT
```python
def _save_fetched_issues(
    repo_identifier: RepoIdentifier, cache_data: CacheData, fetched_keys: set[str]
) -> None
```
Private helper, same module. Called from the duplicate-protection branch
(before its `return`) and from the step-4 `except` branch (after the snapshot
restore, before its `return`), so a list-API outage does not re-fetch stale
closed session issues on every call.

## HOW
Uses existing `_get_cache_file_path`, `_load_cache_file`, `_save_cache_file`.

## ALGORITHM
```
# _save_fetched_issues
if not fetched_keys: return
path = _get_cache_file_path(repo_identifier)
on_disk = _load_cache_file(path)                         # reload: another process may have refreshed
on_disk.setdefault("cached_at", {})
for key in fetched_keys:
    on_disk["issues"][key] = cache_data["issues"][key]
    on_disk["cached_at"][key] = cache_data["cached_at"][key]
_save_cache_file(path, on_disk)

# duplicate-protection branch
_save_fetched_issues(repo_identifier, cache_data, fetched_keys)
return list(cache_data["issues"].values())               # unchanged

# step-4 except branch (snapshots restored in step 2)
cache_data["issues"] = issues_snapshot; cache_data["cached_at"] = cached_at_snapshot
_save_fetched_issues(repo_identifier, cache_data, fetched_keys)
return list(cache_data["issues"].values())               # unchanged
```
Never touch `last_checked`, `updates_covered_through`, `last_full_refresh`
(bumping `last_checked` would extend the window forever). Leave `version` as
loaded.

## DATA
Return value unchanged. Saved file = reloaded file + fetched entries only.

## Tests (`test_cache_additional.py`)
Use `now_utc` patched and `last_checked` within `DUPLICATE_PROTECTION_SECONDS`.
- Uncached additional issue → `get_issue` called once, `_save_cache_file`
  called once; saved `last_checked`, `updates_covered_through`,
  `last_full_refresh` equal the on-disk values; saved `cached_at[key] == now`.
- Reload merge: `_load_cache_file` side_effect returns a first snapshot, then a
  second snapshot containing an extra issue `#200` and a newer `last_checked`
  (simulating another process) → saved data contains `#200` and the second
  snapshot's timestamps.
- Nothing fetched (all cached and fresh) → `_save_cache_file` not called.
- Second call after the save (real tmp cache file) → `get_issue` not called again.
- List-API outage: stale closed session issue, `last_checked` outside the
  duplicate window, `_list_issues_no_error_handling` raises (real tmp cache
  file) → first call fetches it once and returns the cached issues; saved file
  keeps the old `last_checked`/`updates_covered_through`/`last_full_refresh`;
  a second call (list still failing) does not call `get_issue` again.
