# Summary — Fix incremental issue-cache watermark drop (#215)

## Problem

`get_all_cached_issues()` in `src/mcp_workspace/github_operations/issues/cache.py`
can **permanently lose an issue update** (assignee/label change) until the next
full refresh (24h default).

Root cause: a single `last_checked` field conflates two clocks.
- Incremental fetch uses it as the `since` floor:
  `_list_issues_no_error_handling(state="all", ..., since=last_checked)`.
- After merging it is advanced **unconditionally to wall-clock `now`**.

GitHub's `since` filter on the **list** endpoint is eventually-consistent and
lags an issue's real `updated_at`. A write at time `T` can be briefly absent
from a `since`-filtered list at `T+ε`, yet the watermark still advances past `T`.
Because it only moves forward, `[...T...]` is never re-queried — the update is
abandoned until the next full refresh. Downstream, `mcp-coder vscodeclaude`
never opens a session for a freshly-assigned issue (stale empty `assignees`).

## Fix (three cohesive deliverables)

1. **Read-time overlap** — re-scan a short trailing window each incremental
   refresh: `since = updates_covered_through - SINCE_OVERLAP_MINUTES`. A write
   missed at the boundary is re-queried on the next refresh and merged
   idempotently. Constant `SINCE_OVERLAP_MINUTES = 5` lives in `constants.py`
   (mirroring `DUPLICATE_PROTECTION_SECONDS`); **not** a public parameter.

2. **Data-model split** — separate the two clocks:
   - `last_checked` — wall-clock of the last poll (duplicate-protection + age
     display). Unchanged meaning.
   - **new** `updates_covered_through` — the data cursor used as the `since`
     floor. Set from the **max `updated_at` actually merged from the incremental
     list** (honest high-water mark), **never** from wall-clock `now`.
   - **new** `cached_at` — top-level sidecar map `{issue_number → ISO ts}`
     recording when each entry was last written. Cache-level metadata, **not** a
     field on `IssueData` (issue schema stays a pure GitHub mirror).
   - **new** `version` — cache-schema field for safe migrations.

3. **DEBUG logging** — per incremental refresh: the `since` used, count
   returned, min/max `updated_at`, cursor `before → after` + gap, and returned
   issue numbers/count.

## Architectural / design changes

- **Two-clock separation (the core design change).** The cache schema now
  encodes "don't advance past data you haven't observed" structurally, instead
  of relying on the assumption that a `since`-filtered list is complete. This
  makes the bug class unreachable, not just patched.
- **Cursor derives strictly from the incremental `since`-list response.**
  Force-fetched `additional_issues` (fetched by number, bypassing `since`) must
  **never** contribute to the cursor — folding their recent `updated_at` in
  would advance the cursor past a window the list never covered, re-opening the
  gap for other issues. `None` `updated_at` values are filtered before `max()`.
- **Empty incremental response does NOT advance the cursor** — an empty response
  is exactly the eventual-consistency lag hiding a write. On empty: leave the
  cursor unchanged; the next refresh cheaply re-scans the same floor.
- **Full refresh sets `updates_covered_through = now`** — a `state="open"`,
  no-`since` enumeration is a complete observation, not a filtered delta.
- **Overshoot WARN dropped** — structurally unreachable once the cursor is set
  *from* `max(updated_at)`; it would be dead code.
- **Self-healing migration, no back-fill.** Old-shape caches lack
  `updates_covered_through`; the existing full-refresh trigger is extended with
  `or not updates_covered_through`, so an old cache does one full refresh and
  repopulates in the new shape. `version` is written but not branched on
  (migration keys off cursor absence — simpler and equivalent).
- **No change to `IssueData`** and no new public API (`get_all_cached_issues`
  signature unchanged; overlap is an internal constant). `cached_at`/`version`
  bookkeeping never leaks to external consumers (mcp-coder).

## Files created / modified

| File | Action | Purpose |
|------|--------|---------|
| `src/mcp_workspace/constants.py` | modify | add `SINCE_OVERLAP_MINUTES = 5` |
| `src/mcp_workspace/github_operations/issues/cache.py` | modify | `CacheData` fields, `_load_cache_file`, `_fetch_and_merge_issues`, `get_all_cached_issues`, DEBUG logs |
| `tests/github_operations/test_issue_cache.py` | modify | new load/cursor/migration/recovery/log tests; update incremental-path fixtures |
| `tests/github_operations/conftest.py` | modify | add `updates_covered_through` to `sample_cache_data` (keeps incremental-path tests incremental) |
| `pr_info/steps/summary.md` + `step_1..3.md` | create | this plan |

**Not modified:** `types.py` (`IssueData` stays a pure GitHub mirror);
`issues/__init__.py` (no new exports — `SINCE_OVERLAP_MINUTES` is internal).

## Implementation steps (one commit each, TDD)

- **Step 1 — Foundation.** `SINCE_OVERLAP_MINUTES` constant; extend `CacheData`;
  `_load_cache_file` surfaces the three new fields with safe defaults
  (backward-compatible). No refresh-behavior change.
- **Step 2 — The fix.** Two-clock split + read-time overlap + self-healing
  migration + DEBUG logging in `_fetch_and_merge_issues` / `get_all_cached_issues`,
  plus the end-to-end recovery acceptance test.
- **Step 3 — Schema bookkeeping.** `cached_at` sidecar (populate on merge, clear
  on full refresh) and write `version` on save.

## Constraints (from the issue)

- `SINCE_OVERLAP_MINUTES` is a module constant, default 5, not a public param.
- Cursor = `max(updated_at)` over the incremental list **only** (exclude
  `additional_issues`); `None` filtered first; empty ⇒ unchanged; full ⇒ `now`.
- Old-shape caches self-heal via one full refresh; no back-fill code.
- Every code edit must pass pylint + pytest + mypy (MCP tool checks) before commit.
