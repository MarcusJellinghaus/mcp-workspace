# Step 1 — Unique temp file names in `_save_cache_file`

## LLM prompt
Read `pr_info/steps/summary.md`, then implement this step (`pr_info/steps/step_1.md`)
only. Write the tests first, then the implementation. Run pylint, pytest
(`-n auto`) and mypy; all must pass. Run format_code, then make exactly one commit.

## WHERE
- `src/mcp_workspace/github_operations/issues/cache.py` — `_save_cache_file`
- `tests/github_operations/issues/test_cache_io.py`

## WHAT
```python
def _save_cache_file(cache_file_path: Path, cache_data: CacheData) -> bool
```
Signature and return contract unchanged.

## HOW
- `import os`, `import tempfile`, `import time` in `cache.py`.
- Module constant `_REPLACE_RETRY_DELAY_SECONDS: float = 0.1` (tests patch `time.sleep`).
- Update the docstring: unique temp file per save, one retry on replace.

## ALGORITHM
```
tmp = None
try: mkdir parent
     fd, tmp = tempfile.mkstemp(dir=parent, prefix=name + ".", suffix=".tmp")
     write json via os.fdopen(fd, "w")
     for attempt in range(2):
         try: os.replace(tmp, cache_file_path); return True
         except OSError: if attempt == 1: raise; time.sleep(delay)
except OSError as e: log warning (as today); return False
finally: if tmp is not None and it still exists: unlink it (missing_ok, ignore OSError)
```
`mkdir` and `mkstemp` stay inside the `try`, as today, so an unwritable cache
dir returns `False` instead of propagating.
`PermissionError` is a subclass of `OSError`; one `except OSError` covers both.

## DATA
Returns `True` on success, `False` on failure (unchanged). No `.tmp` file remains
after either outcome.

## Tests (`test_cache_io.py`)
- Two saves to the same target use different temp paths (patch `os.replace` to
  record its `src` argument, or spy on `tempfile.mkstemp`).
- Temp file lives in the target's directory and is not `x.issues.tmp`.
- Write failure (patch `json.dump` to raise `OSError`) → returns `False`, no
  `*.tmp` file left in the directory.
- `os.replace` fails once then succeeds → returns `True`, file content correct,
  `time.sleep` called once.
- `os.replace` fails twice → returns `False`, warning logged, no `*.tmp` left.
- `tempfile.mkstemp` raises `OSError` → returns `False` (no exception propagates).
- Existing save/load tests still pass.
