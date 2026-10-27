# Step 2: `caching/_store.py` + `get_issue_cache_last_checked`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_2.md` exactly.
> TDD: write the tests first, then the code. Run pylint, pytest (`-n auto`) and mypy;
> all must pass. One commit.

## WHERE

- Create `src/mcp_workspace/github_operations/caching/_store.py`
- Modify `src/mcp_workspace/github_operations/issues/_cache_io.py`
- Modify `src/mcp_workspace/github_operations/issues/__init__.py`
- Tests: `tests/github_operations/caching/test_store.py`,
  `tests/github_operations/caching/conftest.py`; adjust
  `tests/github_operations/issues/test_cache_io.py` only where it patches
  `os.replace` / `tempfile` / `time.sleep` in the old module path.

## WHAT

```python
# caching/_store.py
CACHE_DIR_PARTS = ("mcp_coder", "coordinator_cache")

def cache_file_path(repo_identifier: RepoIdentifier, suffix: str) -> Path:
    """<app-data>/mcp_coder/coordinator_cache/<cache_safe_name>.<suffix>.json"""

def load_json(path: Path, expected_version: int | None = None) -> dict[str, Any]:
    """Load a JSON object. Missing/corrupt/non-dict → {}.
    If expected_version is given and data.get("version") != expected_version → {}. Never raises."""

def _save_cache_file(cache_file_path: Path, cache_data: Mapping[str, Any]) -> bool:
    """MOVED unchanged from issues/_cache_io.py (tempfile, cleanup, one replace retry)."""

# issues/_cache_io.py
def get_issue_cache_last_checked(repo_identifier: RepoIdentifier) -> datetime | None:
    """Parsed `last_checked` of the issue cache, or None (missing/unparseable)."""
```

## HOW

- Move `_save_cache_file` and `_REPLACE_RETRY_DELAY_SECONDS` byte-for-byte; only widen the
  parameter type to `Mapping[str, Any]` (CacheData is still accepted).
- `issues/_cache_io.py`: `from ..caching._store import _save_cache_file, cache_file_path, load_json`.
  - `_get_cache_file_path(repo_identifier)` → `cache_file_path(repo_identifier, "issues")`.
  - `_load_cache_file(path)` → `data = load_json(path)` (no `expected_version`), then the
    existing `"issues"` key check and defaults. Keep the existing warning log on invalid
    structure (`load_json` logs corrupt JSON itself).
  - Keep `_save_cache_file` importable from `issues._cache_io` and `issues/__init__`.
- `get_user_app_data_dir` import moves to `_store.py`.
- `issues/__init__.py`: add `get_issue_cache_last_checked` to imports and `__all__`;
  leave all underscore exports as they are (needed by pinned mcp_coder).
- Import order matters: `caching/__init__.py` stays import-free so
  `issues/_cache_io → caching._store` does not pull in `caching.branches`.
- `tests/github_operations/caching/conftest.py`: autouse fixture
  `cache_dir(tmp_path, monkeypatch)` that patches `_store.get_user_app_data_dir` to return
  `tmp_path`, so no test touches the real app-data dir.

## ALGORITHM

```
load_json(path, v):
    if not path.exists(): return {}
    try: data = json.loads(path.read_text())
    except (JSONDecodeError, OSError, UnicodeDecodeError): log warning; return {}
    if not isinstance(data, dict): return {}
    if v is not None and data.get("version") != v: log debug; return {}
    return data
```

## DATA

`load_json` → plain `dict[str, Any]`; `{}` means "empty cache".

## Tests (`test_store.py`)

- Path: `cache_file_path(RepoIdentifier("o","r"), "prs")` ends with `coordinator_cache/<cache_safe_name>.prs.json`.
- `load_json`: missing → `{}`; invalid JSON → `{}`; JSON list → `{}`; version mismatch / missing version with `expected_version=1` → `{}`; matching version → data; no `expected_version` → data regardless.
- `_save_cache_file` round-trips through `load_json`; existing temp-file tests in `test_cache_io.py` still pass (repoint patches to `caching._store` if needed).
- `get_issue_cache_last_checked`: file with `last_checked` → aware `datetime`; missing file / missing key / garbage → `None`.
- Old-shape `.issues.json` (no `version`) still loads with defaults — existing `test_cache_refresh.py` unchanged and green.
- `from mcp_workspace.github_operations.issues import _get_cache_file_path, _load_cache_file, _save_cache_file, _log_stale_cache_entries` still works.
