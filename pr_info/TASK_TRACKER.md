# Task Status Tracker

## Instructions for LLM

This tracks **Feature Implementation** consisting of multiple **Tasks**.

**Summary:** See [summary.md](./steps/summary.md) for implementation overview.

**How to update tasks:**
1. Change [ ] to [x] when implementation step is fully complete (code + checks pass)
2. Change [x] to [ ] if task needs to be reopened
3. Add brief notes in the linked detail files if needed
4. Keep it simple - just GitHub-style checkboxes

**Task format:**
- [x] = Task complete (code + all checks pass)
- [ ] = Task not complete
- Each task links to a detail file in steps/ folder

---

## Tasks

### Step 1: Foundation — constant + schema fields + backward-compatible load

Detail: [step_1.md](./steps/step_1.md)

- [x] Implementation (tests + production code): add `SINCE_OVERLAP_MINUTES` to `constants.py`; extend `CacheData` TypedDict with `updates_covered_through`, `cached_at`, `version`; update `_load_cache_file` to surface them with safe defaults on all return paths; update docstrings
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: The fix — two-clock split + read-time overlap + migration + DEBUG logs

Detail: [step_2.md](./steps/step_2.md)

- [x] Implementation (tests + production code): change `_fetch_and_merge_issues` to return `(fresh_issues, is_full_refresh, new_cursor)` and take parsed cursor; compute incremental `since` as `cursor - SINCE_OVERLAP_MINUTES`; extend full-refresh trigger with `or not updates_covered_through`; wire cursor through `get_all_cached_issues`; add DEBUG logs; update incremental-path fixtures
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared (blocked: `pr_info/.commit_message.txt` is gitignored and cannot be written via MCP tools; no Bash tool available this session — message text ready, see run output)

### Step 3: Schema bookkeeping — `cached_at` sidecar + `version` write

Detail: [step_3.md](./steps/step_3.md)

- [ ] Implementation (tests + production code): add `CACHE_SCHEMA_VERSION = 1`; reset `cached_at = {}` on full refresh; stamp `cached_at` for merged issues (fresh + additional); write `version` on save
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] Address PR review feedback
- [ ] Prepare PR summary
