# Step 4 — `set_issue_labels_in_cache` (coordinator issue cache)

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **Step 4** exactly as described
> in `pr_info/steps/step_4.md`. Write the tests first, then the code. Run pylint,
> pytest (`-n auto`) and mypy via the MCP tools until all pass, format the code,
> and make exactly one commit.

## WHERE

- `src/mcp_workspace/github_operations/issues/cache.py`: add it next to
  `update_issue_labels_in_cache`, and mention it in the module docstring.
- `tests/github_operations/issues/test_cache_update.py`

## WHAT

```python
def set_issue_labels_in_cache(
    repo_identifier: RepoIdentifier, issue_number: int, labels: list[str]
) -> None:
    """Replace a cached issue's whole label set. Never raises; debug-logs a miss."""
```

## HOW

- Use the same helpers as `update_issue_labels_in_cache`: `_get_cache_file_path`,
  `_load_cache_file` and `_save_cache_file` from `._cache_io`.
- Unlike the existing function, a missing issue is logged at **debug** level
  (for example, a reference project the coordinator does not poll).
- A failed save is logged as a warning. Any exception is caught
  (`# pylint: disable=broad-exception-caught`) and logged as a warning.
- Touch nothing but `issues[key]["labels"]`. Leave `last_checked` and
  `cached_at` alone: bumping `last_checked` would extend the duplicate
  protection.

## ALGORITHM

```
try:
    path = _get_cache_file_path(repo_identifier); data = _load_cache_file(path)
    issue = data["issues"].get(str(issue_number))
    if issue is None: logger.debug(...); return
    issue["labels"] = list(labels)
    if not _save_cache_file(path, data): logger.warning(...)
except Exception as e: logger.warning(...)
```

## DATA

Returns `None`. Side effect: `<repo>.issues.json` updated in place.

## Tests (write first; follow the existing patterns in `test_cache_update.py`)

- a cached issue's labels are replaced with exactly the given list; other
  issues and `last_checked` are unchanged
- an issue not in the cache → file not rewritten, debug record logged, no warning
- a failed save → warning logged, no exception
- `_load_cache_file` raising → no exception, warning logged
