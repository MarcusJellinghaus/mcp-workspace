# Step 1 — Foundation: constant + schema fields + backward-compatible load

**Goal:** Introduce the overlap constant and the three new cache-schema fields,
and make `_load_cache_file` surface them with safe defaults. **No refresh
behavior changes yet** — this step is pure plumbing so the diff is small and
self-contained. One commit.

## WHERE
- `src/mcp_workspace/constants.py`
- `src/mcp_workspace/github_operations/issues/cache.py`
  (`CacheData` TypedDict, `_load_cache_file`)
- `tests/github_operations/test_issue_cache.py` (new tests)

## WHAT

### `constants.py`
```python
SINCE_OVERLAP_MINUTES: int = 5
```
Fixed margin against GitHub's `since`-index lag; mirrors the existing
`DUPLICATE_PROTECTION_SECONDS`. Add a one-line comment explaining why.

### `cache.py` — extend `CacheData`
```python
class CacheData(TypedDict):
    last_checked: Optional[str]
    last_full_refresh: NotRequired[Optional[str]]
    updates_covered_through: NotRequired[Optional[str]]   # data cursor (max observed updated_at)
    cached_at: NotRequired[Dict[str, str]]                # {issue_number: ISO ts} sidecar
    version: NotRequired[Optional[int]]                   # cache-schema version
    issues: Dict[str, IssueData]
```

### `cache.py` — `_load_cache_file(cache_file_path: Path) -> CacheData`
Surface the new fields on **both** the empty-structure returns and the
loaded-data return, exactly mirroring how `last_full_refresh` is already handled.

## HOW
- Import nothing new in `cache.py` for this step (`Dict` already imported).
- The empty/error return dicts gain: `"updates_covered_through": None`,
  `"cached_at": {}`, `"version": None`.
- The success return reads via `.get()`:
  `data.get("updates_covered_through")`, `data.get("cached_at", {})`,
  `data.get("version")`.
- `_save_cache_file` needs **no change** — it dumps the whole dict; new keys are
  written by callers in later steps.
- **Docstrings (Boy Scout):** update the `CacheData` TypedDict docstring **and**
  the `_load_cache_file` docstring to document the three new fields
  (`updates_covered_through`, `cached_at`, `version`) — they currently only
  document `last_checked`/`issues`.

## ALGORITHM (`_load_cache_file`, unchanged shape)
```
if not exists: return EMPTY (with new-field defaults)
data = json.load(...)
if not dict or "issues" missing: warn; return EMPTY (with new-field defaults)
return {last_checked, last_full_refresh,
        updates_covered_through, cached_at (default {}), version, issues}
on JSON/OS error: warn; return EMPTY (with new-field defaults)
```

## DATA
`_load_cache_file` always returns a `CacheData` where `cached_at` is a dict
(never missing), and `updates_covered_through` / `version` are `None` when absent
(old-shape files) — this `None` is what triggers the self-healing full refresh in
Step 2.

## TESTS (write first — TDD)
Add to `test_issue_cache.py` (e.g. extend `TestCacheFileOperations` /
`TestLastFullRefresh`):
1. `test_load_cache_file_nonexistent_has_new_field_defaults` — nonexistent path
   returns `updates_covered_through is None`, `cached_at == {}`, `version is None`.
2. `test_load_cache_preserves_new_fields` — a file containing all three new
   fields round-trips through `_load_cache_file` unchanged.
3. `test_load_old_shape_cache_defaults_new_fields` — a file with only
   `last_checked` + `issues` (no version/cursor/cached_at) loads with
   `updates_covered_through is None`, `version is None`, `cached_at == {}`,
   issues intact (backward compatibility / self-heal precondition).

## CHECKS (must pass before commit)
```
mcp__tools-py__run_pylint_check
mcp__tools-py__run_pytest_check(extra_args=["-n","auto","-m",
  "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])
mcp__tools-py__run_mypy_check
```

## LLM PROMPT
> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`. Implement Step 1
> only, following TDD (write the three `_load_cache_file` tests first, watch them
> fail, then implement). Add `SINCE_OVERLAP_MINUTES = 5` to
> `src/mcp_workspace/constants.py`; extend the `CacheData` TypedDict in
> `src/mcp_workspace/github_operations/issues/cache.py` with
> `updates_covered_through`, `cached_at`, and `version` (all `NotRequired`); and
> update `_load_cache_file` to surface them with safe defaults on every return
> path, mirroring `last_full_refresh`. Per the Boy Scout rule, update the
> `CacheData` TypedDict docstring and the `_load_cache_file` docstring to
> document the three new fields. Do **not** change refresh behavior,
> `_save_cache_file`, `IssueData`, or `__init__.py`. Use MCP tools for all file
> and check operations. After the edits, run pylint, pytest (with the
> not-integration marker exclusion and `-n auto`), and mypy; fix everything until
> all pass, then stop. State "All CLAUDE.md requirements followed".
