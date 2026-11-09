# Step 2 — `github_label_list` reads through the label cache

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **Step 2** exactly as described
> in `pr_info/steps/step_2.md`. Step 1 (`caching/labels.py`) is already done.
> Write or adjust the tests first, then the code. Run pylint, pytest (`-n auto`)
> and mypy via the MCP tools until all pass, format the code, and make exactly
> one commit.

## Precondition

`src/mcp_workspace/github_operations/caching/labels.py` defines `get_cached_labels`.
If it does not, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `tests/github_operations/conftest.py`: add the autouse `cache_dir` fixture,
  moved verbatim from `tests/github_operations/caching/conftest.py`.
- `tests/github_operations/caching/conftest.py`: delete it (its only fixture moved up).
- `src/mcp_workspace/server.py`: `_rate_limit_message` (new), `_tool_error`,
  `_api_error`, `github_label_list`.
- `tests/github_operations/test_github_write_tools_labels_pr.py` and
  `tests/github_operations/test_github_write_tools_reference.py`: their
  `_make_manager` helpers and inline `MagicMock()` managers used for
  `github_label_list` must set
  `mock_mgr.repo_identifier = RepoIdentifier("owner", "repo")`. A MagicMock
  `cache_safe_name` would produce an invalid file name.

## WHAT

```python
def _rate_limit_message(exc: Exception) -> str | None:
    """GitHubRateLimitError → its message; otherwise format_rate_limit_error(exc)."""

def github_label_list(search: str | None = None,
                      reference_name: str | None = None,
                      refresh_labels: bool = False) -> str: ...
```

## HOW

- Lazy imports inside the functions, as already done for
  `format_rate_limit_error` (this keeps PyGithub off the startup path):
  `from mcp_workspace.github_operations.caching.errors import GitHubRateLimitError`,
  `from mcp_workspace.github_operations.caching.labels import get_cached_labels`.
- `_tool_error`: `return _rate_limit_message(e) or f"Error: {e}"`.
- `_api_error`: replace its `format_rate_limit_error(exc)` call with
  `_rate_limit_message(exc)`. The suffix behaviour is unchanged.
- `github_label_list`: `labels, footer = get_cached_labels(manager, refresh_labels)`.
  Filtering and line format stay unchanged. Append `footer` as the last line,
  including after "No labels found…".
- Docstring additions:
  - `refresh_labels`: forces a reload of the cache.
  - The labels come from a disk cache shared across sessions. A label created
    on GitHub may not show for up to 24 h unless `refresh_labels=True`. This
    differs from the create/edit label check, which is uncached.
  - The output ends with `Label cache last updated <timestamp>`, marked stale
    when a refresh was rate-limited.

## ALGORITHM

```
manager = _issue_manager(reference_name)
labels, footer = get_cached_labels(manager, refresh=refresh_labels)
filter by search (unchanged)
body = "No labels found{suffix}." if not labels else "\n".join(lines)
return f"{body}\n{footer}"
```

## DATA

Output: the existing lines, then `Label cache last updated <fetched_at>[ — refresh failed: …]`.

## Tests (write first / adjust)

- Existing `TestGithubLabelList` assertions: compare `result.splitlines()[:-1]`
  (or the full text including the footer) and assert that the last line starts
  with `Label cache last updated `.
- New: `refresh_labels=True` calls `get_available_labels` again when a cache
  entry exists. Without it, a second call does not fetch.
- New: a rate limit on a forced refresh with an existing entry returns the old
  labels and a stale footer.
- `test_label_list_rate_limit_names_bucket` must pass **unchanged**. The
  `GitHubRateLimitError` message contains `` `core` `` and has no `Error:` prefix.
- New: `_api_error` given a `GitHubRateLimitError` returns its message plus the
  reference suffix.
- `test_exception_is_reported` (`"Error: boom"`) and the 500 test still pass.
