# Step 5 — Split `test_issue_cache.py` → `test_cache_*.py` + drop allowlist line

> Read `pr_info/steps/summary.md` first. This is Step 5 of 6. One commit.

## Kind
Test-only split by **whole test class**. Source (`cache.py`) stays as-is. The current file
is ~2240 lines (grew past the 1654 the issue quoted), so a comfortable split lands at
**4–5 files**, each well under 750. **No test-logic changes.**

## WHERE
- Delete: `tests/github_operations/test_issue_cache.py`
- Create: `tests/github_operations/issues/test_cache_*.py` (4–5 files)
- Modify: `.large-files-allowlist` — remove the line
  `tests/github_operations/test_issue_cache.py`

## WHAT — packing rule
Distribute the file's whole classes across files by concern; **never cut inside a class**.
Keep the classes that use the module helper `_make_cursor_issue` **together in one file** so
the helper stays local and is not duplicated. Copy the shared import block into each new
file. Suggested grouping (finalize from actual sizes; each must be < 750):

| File | Classes |
|---|---|
| `test_cache_io.py` | `TestCacheMetricsLogging`, `TestCacheFilePath`, `TestCacheFileOperations`, `TestStalenessLogging` |
| `test_cache_update.py` | `TestCacheIssueUpdate`, `TestCacheUpdateIntegration` |
| `test_cache_additional.py` | `TestAdditionalIssuesParameter`, `TestApiFailureHandling` |
| `test_cache_refresh.py` | `TestLastFullRefresh`, `_make_cursor_issue`, `TestNewCacheSchemaFields`, `TestUpdatesCoveredThrough`, `TestWatermarkRecovery`, `TestCacheBookkeeping` |

(`_make_cursor_issue` and its four consumers `TestNewCacheSchemaFields` /
`TestUpdatesCoveredThrough` / `TestWatermarkRecovery` / `TestCacheBookkeeping` (~562 lines
total) stay together in one file so the helper is defined where every user sees it; they may
be regrouped into other files only if all consumers move with the helper and each file stays
< 750 — the rule is whole-class packing keeping `_make_cursor_issue` with its users, not this
exact table.)

## HOW — imports / fixtures
Each new file repeats only the imports its classes need (e.g.
`from mcp_workspace.github_operations.issues.cache import ...`). Fixtures
(`mock_cache_issue_manager`, `sample_cache_data`, `sample_issue`) cascade from the parent
conftest — **unchanged**. Preserve existing class markers.

## ALGORITHM
```
list classes + line ranges in test_issue_cache.py
assign whole classes to files by concern, keeping _make_cursor_issue with its users
for each target file: write shared imports + its assigned classes verbatim
delete test_issue_cache.py
remove its line from .large-files-allowlist
check_file_size(750): every new file < 750 and none on allowlist
```

## DATA
No new data structures. Deliverable = 4–5 `test_cache_*.py` files (verbatim class bodies)
+ trimmed allowlist.

## Verify (MCP tools only)
- `mcp__tools-py__run_pytest_check(extra_args=["-n","auto","tests/github_operations/issues"])`
  (keep git markers) — same test count passes, none lost.
- `mcp__mcp-workspace__check_file_size(max_lines=750)` — all `test_cache_*.py` < 750;
  `test_issue_cache.py` no longer flagged/allowlisted.
- `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_mypy_check`.

## Done when
Every cache test lives in a `test_cache_*.py` file under 750, the original file and its
allowlist line are gone, all tests pass, checks green. One commit.

## LLM prompt
> Implement Step 5 from `pr_info/steps/step_5.md` (context in `pr_info/steps/summary.md`).
> Split `tests/github_operations/test_issue_cache.py` into 4–5
> `tests/github_operations/issues/test_cache_*.py` files by **whole test class** (never cut
> inside a class; keep `_make_cursor_issue` with its consumers), copying each class and the
> imports it needs **verbatim** — no logic changes. Delete the original file and remove its
> line from `.large-files-allowlist` (leave the three non-issue entries). Verify with
> `mcp__tools-py__run_pytest_check` on `tests/github_operations/issues`,
> `check_file_size(max_lines=750)`, then pylint and mypy. Follow all `CLAUDE.md` rules (MCP
> tools only; `./tools/format_all.sh` before committing). Produce exactly one commit.
