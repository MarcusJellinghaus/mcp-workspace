# Plan Review Log — Issue #222

Reorganize issue-manager tests to mirror `issues/` package + split oversized test files.

- Branch: `222-reorganize-issue-manager-tests-to-mirror-issues-package-split-oversized-test-files`
- Base: `main` (up to date, CI passing)
- Plan: `pr_info/steps/step_1.md` … `step_6.md` + `summary.md`
- Started: 2026-07-22
- Supervisor: plan_review_supervisor

---

## Round 1 — 2026-07-22

**Findings** (from `/plan_review` engineer, codebase-verified):
1. **[blocker]** Step 5 cache grouping table separates `_make_cursor_issue` (defined once, used by 4 classes) from 2 of its consumers (`TestWatermarkRecovery`, `TestCacheBookkeeping` placed in a separate `test_cache_watermark.py`) → `NameError` on collection. All 4 consumer classes (~562 lines) fit in one file under 750.
2. [improvement] Stale line counts (issue quotes cache at 1654; actual ~2239). Step 5 already catches this and sizes from actual ranges.
3. [nit] Step 3 names `test_issue_manager_comments.py` (pre-Step-1 name) alongside post-rename names; Step 1 already renamed it to `test_comments_mixin.py`.
4–6. [nit/no-action] `1:module` acceptance satisfied by union of Steps 1/3/4; Step 6 heaviest but valid one-commit; `TestGetBranchWithPRFallback` two-file split confirmed clean (no class-level state).

**Decisions**:
- Finding 1 — **accept, fix**: correct Step 5 table so all four `_make_cursor_issue` consumers share one file.
- Finding 3 — **accept, fix**: use `test_comments_mixin.py` in Step 3's "do not remove imports" list.
- Findings 2, 4, 5, 6 — **skip**: already handled / self-resolved / no action.

**User decisions**: none. Split-file boundary reproducibility question NOT escalated — issue already decided boundaries are finalized during implement (no scope/architecture impact).

**Changes**:
- `pr_info/steps/step_5.md` — revised cache-split table so all four `_make_cursor_issue` consumers land in one file (`test_cache_refresh.py`) with the helper; removed the separate `test_cache_watermark.py` row.
- `pr_info/steps/step_3.md` — `test_issue_manager_comments.py` → `test_comments_mixin.py` (post-Step-1 name).

**Status**: committed (2 plan files changed → loop to Round 2).

## Round 2 — 2026-07-22

Re-review after Round 1 fixes. Commit `09014da`.

**Findings**:
- Round-1 fixes verified: Step 5 `NameError` blocker resolved (helper + consumers now grouped), Step 3 filenames all post-Step-1. ✓
1. **[improvement]** Step 5 suggested `test_cache_refresh.py` still bundles `TestLastFullRefresh` (~182 lines) with the helper group → ~780 lines, over 750. `TestLastFullRefresh` does not use `_make_cursor_issue`, so it can move to a 5th file for a clean split.
2. [nit] Step 5 labels "four `_make_cursor_issue` consumers (~562 lines)"; actually three consume it — `TestNewCacheSchemaFields` is defined above the helper and never calls it. Accuracy only, no collection impact.
- Verified clean: Step 6 split math (all groups <750), Step 4 math (~620 single file), Step 3 `parse_base_branch` cases match source, allowlist entries exact, dependencies/verification steps correct.

**Decisions**:
- Findings 1 & 2 — **accept, fix**: move `TestLastFullRefresh` out of `test_cache_refresh.py` into a 5th cache file so every suggested group lands <750; correct "four consumers → three".

**User decisions**: none. No design/requirements questions raised.

**Changes**:
- `pr_info/steps/step_5.md` — split the over-750 `test_cache_refresh.py` row into two: `test_cache_full_refresh.py` (`TestLastFullRefresh`, ~182) + `test_cache_refresh.py` (helper + its 3 real consumers, ~600). Now a 5-file cache split, each <750. Corrected "four consumers" → "three".

**Status**: committed (1 plan file changed → loop to Round 3).
