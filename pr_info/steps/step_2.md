# Step 2 — The fix: two-clock split + read-time overlap + migration + DEBUG logs

**Goal:** Stop losing updates. Split the data cursor from the wall-clock, apply
the read-time overlap, self-heal old caches, add DEBUG logging, and prove
recovery end-to-end. One commit. Depends on Step 1.

## WHERE
- `src/mcp_workspace/github_operations/issues/cache.py`
  (`_fetch_and_merge_issues`, `get_all_cached_issues`)
- `tests/github_operations/test_issue_cache.py` (new tests + fixture updates)
- `tests/github_operations/conftest.py` (`sample_cache_data` fixture)

## WHAT

### `cache.py` — imports
Add `from mcp_workspace.constants import DUPLICATE_PROTECTION_SECONDS,
SINCE_OVERLAP_MINUTES` (extend existing import).

### `cache.py` — `_fetch_and_merge_issues(...)` new signature
Replace the two returned values with three, and take the parsed cursor:
```python
def _fetch_and_merge_issues(
    issue_manager, cache_data, repo_name, force_refresh,
    last_checked, now, cache_refresh_minutes,
    last_full_refresh=None,
    updates_covered_through=None,          # NEW: parsed datetime | None
) -> Tuple[List[IssueData], bool, Optional[datetime]]:  # (+ new_cursor)
```

### `cache.py` — `get_all_cached_issues(...)`
Signature **unchanged** (no new public param). Internally:
- parse `updates_covered_through` from cache (like `last_full_refresh`);
- pass it into `_fetch_and_merge_issues`;
- assign the returned `new_cursor` only when not `None`;
- keep `cache_data["last_checked"] = format_for_cache(now)` as-is.

## HOW / integration
- Migration: extend the existing `is_full_refresh` boolean with
  `or not updates_covered_through` (old-shape caches self-heal via one full
  refresh). `version` is **not** read here.
- Incremental `since` floor is computed at read time from the cursor, not
  `last_checked`.
- **DEBUG-log style:** keep the new incremental-refresh DEBUG lines consistent
  with the existing `_log_cache_metrics(action, repo_name, **kwargs)` helper in
  `cache.py` — include `repo_name` context so all cache logging shares one
  idiom. Inline `logger.debug(...)` is acceptable, but do not introduce a second
  divergent logging style in the module.

## ALGORITHM — `_fetch_and_merge_issues`
```
is_full = force_refresh or not last_checked or not last_full_refresh
          or not updates_covered_through
          or (now - last_full_refresh) > threshold
if is_full:
    fresh = list(state="open", include_prs=False); cache["issues"] = {}
    new_cursor = now
else:
    since = updates_covered_through - timedelta(minutes=SINCE_OVERLAP_MINUTES)
    fresh = list(state="all", include_prs=False, since=since)
    stamps = [parse(i["updated_at"]) for i in fresh if i.get("updated_at")]
    new_cursor = max(stamps) if stamps else None      # empty/all-None -> None (unchanged)
    <DEBUG log: since, len(fresh), min/max stamps, cursor before->after + gap, numbers>
return fresh, is_full, new_cursor
```

## ALGORITHM — `get_all_cached_issues` step 5 (delta)
```
fresh, was_full, new_cursor = _fetch_and_merge_issues(..., updates_covered_through=cursor_dt)
cache["issues"].update({str(i["number"]): i for i in fresh})
if additional_dict: cache["issues"].update(additional_dict)   # unchanged; excluded from cursor
cache["last_checked"] = format_for_cache(now)                 # wall clock (unchanged)
if new_cursor is not None:
    cache["updates_covered_through"] = format_for_cache(new_cursor)
if was_full: cache["last_full_refresh"] = format_for_cache(now)
```

## DATA
- `_fetch_and_merge_issues` → `(fresh_issues, is_full_refresh, new_cursor)`
  where `new_cursor` is a tz-aware `datetime` or `None`.
- Cursor value is `max(updated_at)` over the **since-list only** (full: `now`;
  empty incremental: `None` ⇒ caller leaves stored cursor unchanged).
- `additional_dict` is merged into `issues` but never feeds `new_cursor`.

## TESTS (write first — TDD)
Unit (new `TestUpdatesCoveredThrough` class):
1. `test_incremental_cursor_is_max_updated_at` — two returned issues
   (`updated_at` A < B) ⇒ saved `updates_covered_through == B`.
2. `test_full_refresh_cursor_is_now` — full refresh ⇒ cursor == `now`.
3. `test_empty_incremental_does_not_advance_cursor` — `[]` returned ⇒ saved
   cursor unchanged from seed.
4. `test_none_updated_at_filtered` — returned issues all `updated_at=None` ⇒
   treated as empty (cursor unchanged).
5. `test_additional_issues_excluded_from_cursor` — `additional_issues` with a
   newer `updated_at` than the since-list ⇒ cursor reflects the since-list max,
   not the additional issue.
6. `test_incremental_since_uses_cursor_minus_overlap` — assert
   `_list_issues_no_error_handling` called with
   `since == cursor - timedelta(minutes=SINCE_OVERLAP_MINUTES)`.
7. `test_old_shape_cache_triggers_full_refresh` — seed with no
   `updates_covered_through` ⇒ called with `state="open"` (migration).
8. `test_malformed_cursor_triggers_full_refresh` — seed a **malformed**
   `updates_covered_through` (unparseable timestamp) that parses to `None`;
   assert it self-heals into a full refresh (`state="open"`) via the existing
   `or not updates_covered_through` clause. No new validation code — rely on the
   implicit malformed→`None`→full-refresh behavior; this test just covers the
   edge.
9. DEBUG-log test — `caplog` at DEBUG asserts the since/count/min-max/cursor
   before→after lines are emitted on incremental refresh.

Acceptance / recovery (headline — `TestWatermarkRecovery`):
10. `test_missed_update_recovered_on_next_incremental` — construct **two
   consecutive incremental refreshes**:
   - seed recent `last_full_refresh` (stays incremental), seed
     `updates_covered_through` + `last_checked` > 60s old;
   - `@patch(...cache.now_utc)` to advance time between the two calls;
   - drive two `_list_issues_no_error_handling` returns via `side_effect`:
     first call returns **without** the missed issue; second call returns it
     (its `updated_at` within `[cursor - overlap, cursor]`);
   - assert the missed issue is present in the cache after the second refresh,
     with **no full refresh** performed.

Fixture updates (so existing incremental-path tests stay incremental under the
new migration clause — add `updates_covered_through` to their seeds):
- `conftest.py` `sample_cache_data`: add
  `"updates_covered_through": "2025-12-31T09:00:00Z"`.
- **Search ALL of `test_issue_cache.py` (and the `conftest.py` fixtures)** for
  tests that construct a cache dict inline (grep the seed shapes, e.g.
  `"last_checked"` / `"last_full_refresh"` / `"issues":`) and are on an
  **intended incremental path**. Add `updates_covered_through` to **every** such
  seed so it stays incremental under the new `or not updates_covered_through`
  migration clause — do not stop at the two named `TestLastFullRefresh` tests;
  those are only examples of the class, not the full set. (Full-refresh /
  force-refresh / empty-cache seeds should be left as-is.)
- Concretely, this includes at least
  `TestLastFullRefresh.test_incremental_refresh_does_not_update_last_full_refresh`
  and `test_full_refresh_triggers_when_last_full_refresh_is_old`: add
  `updates_covered_through` so the incremental case is genuinely incremental and
  the full-refresh case still triggers via the age threshold — but audit the
  whole file, not just these two.

## CHECKS (before commit)
```
mcp__tools-py__run_pylint_check
mcp__tools-py__run_pytest_check(extra_args=["-n","auto","-m",
  "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])
mcp__tools-py__run_mypy_check
```

## LLM PROMPT
> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`. Implement Step 2
> only (Step 1 is already merged), following TDD: write the unit tests and the
> recovery acceptance test first, watch them fail, then implement. Change
> `_fetch_and_merge_issues` to return `(fresh_issues, is_full_refresh,
> new_cursor)`, take a parsed `updates_covered_through` argument, compute the
> incremental `since` as `cursor - SINCE_OVERLAP_MINUTES`, extend the
> `is_full_refresh` boolean with `or not updates_covered_through` (self-healing
> migration), and set `new_cursor` to `now` on full refresh, `max(updated_at)`
> over the since-list only (None-filtered) on incremental, and `None` on empty.
> In `get_all_cached_issues`, parse and pass the cursor, and store
> `updates_covered_through` only when the returned cursor is not None, keeping
> `last_checked = now`. `additional_issues` must never feed the cursor. Add the
> required DEBUG logs. Do **not** add a public parameter, touch `IssueData`, or
> maintain `cached_at`/`version` (Step 3). Update the existing incremental-path
> fixtures/seeds as listed so they stay incremental. Use MCP tools for all file
> and check operations. Run pylint, pytest (not-integration exclusion, `-n
> auto`), and mypy; fix until all pass, then stop. State "All CLAUDE.md
> requirements followed".
