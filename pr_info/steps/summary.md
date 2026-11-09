# Summary — #388 `github_issue_set_status` + shared disk label cache

## Goal

A dedicated MCP tool that moves an issue through its workflow `status-*` labels,
on the workspace repo or a reference project's repo, without Bash and without a
clone. Valid statuses are validated against a new per-repo disk label cache,
which `github_label_list` also uses. The general write tools keep rejecting
`status-*`.

## Architectural / design changes

- **New disk cache `caching/labels.py`** — joins the existing `caching/` family
  (`branches.py`, `pull_requests.py`) and reuses `_store.py` (path, versioned
  `load_json`, atomic `_save_cache_file`, `is_expired`, `new_expiry`).
  - File: `<app-data>/mcp_coder/coordinator_cache/<cache_safe_name>.labels.json`,
    one repo per file, shared by every MCP server process and mcp-coder.
  - Shape: `{"version": 1, "fetched_at": str, "expires_at": str, "labels": [LabelData, ...]}`
    (all labels, every `LabelData` field).
  - Single entry point: `get_cached_labels(manager, refresh=False) -> CachedLabels`
    (a `NamedTuple(labels, footer)`). No run-scoped `load()`/`save()` object.
    The file is read on every call.
  - Reloads only when the entry is missing, invalid or expired, or when
    `refresh=True`. Never on an unknown name.
  - Expiry: 24 h maximum via the new optional `max_age` parameter on
    `_store.new_expiry()` (jitter → 18–24 h). The other caches keep `MAX_AGE` (6 h).
  - Fetch runs inside `rate_limit_guard()`. A rate-limited reload falls back to
    an existing entry and marks the footer stale. With no entry, the rate-limit
    error propagates. Other errors propagate. A failed fetch is never saved.
  - The footer string is built inside `get_cached_labels`, so both tools share
    one implementation.
- **New narrow read `LabelsMixin.get_issue_for_status(number) -> IssueData`** —
  one `_get_issue_checked` call, rejects PRs, converts with the existing
  `issue_to_data` (no base-branch trust lookup). Undecorated, so GitHub errors
  (404/5xx/network) propagate as themselves.
- **New `issues/cache.py:set_issue_labels_in_cache(repo_identifier, number, labels)`** —
  writes a whole label set into mcp-coder's coordinator issue cache
  (`<repo>.issues.json`). Debug log on a miss, never raises. This closes the
  60 s duplicate-protection gap.
- **New module `issues/status.py:set_issue_status(...) -> str`** — owns the
  transition logic and returns the final user-facing text for every outcome
  (invalid label, guard failed, no-op, changed, unconfirmed write). Keeps the
  logic out of `server.py`, which is already far over the file-size limit.
- **`server.py`**
  - New tool `github_issue_set_status` (thin: `_issue_manager` →
    `set_issue_status` → return, inside `try/_tool_error`).
  - `github_label_list` reads through `get_cached_labels`, gains
    `refresh_labels`, and ends with the cache footer.
  - `_tool_error`/`_api_error` render a `GitHubRateLimitError` as its bare
    message, via one small shared helper `_rate_limit_message`.
  - `_check_labels` and the create/edit docstrings point to
    `github_issue_set_status`. `_check_labels` itself stays uncached.
  - `_check_labels` uses `issues.status.is_status_label` (lazy import);
    `_STATUS_LABEL_PREFIX` is deleted, so the rule lives in one place.
- **Test isolation** — the autouse `cache_dir` fixture moves from
  `tests/github_operations/caching/conftest.py` up to
  `tests/github_operations/conftest.py`, so the tool tests never write to the
  real app-data dir.

## Simplifications chosen (KISS)

- `get_cached_labels` returns `(labels, footer)`. There is no separate
  footer-formatting function or error-carrying result type.
- `set_issue_status` returns a string. There is no result object or enum, and
  no separate render step.
- `get_issue_for_status` returns the existing `IssueData`. There is no new TypedDict.
- One reused fixture. There is no second cache-dir fixture.

## Decisions taken without explicit confirmation

- The footer prints `fetched_at` exactly as stored (UTC, `format_for_cache` format).
- `.claude/CLAUDE.md` keeps `mcp-coder gh-tool set-status` in the Bash allow
  list, because the synced skills still call it. The "Status labels" rule
  changes to prefer `github_issue_set_status`.

## Files

### Created
- `src/mcp_workspace/github_operations/caching/labels.py`
- `src/mcp_workspace/github_operations/issues/status.py`
- `tests/github_operations/caching/test_labels.py`
- `tests/github_operations/issues/test_status.py`
- `tests/github_operations/test_github_issue_set_status.py`

### Modified
- `src/mcp_workspace/github_operations/caching/_store.py` (`new_expiry(max_age=...)`)
- `src/mcp_workspace/github_operations/issues/labels_mixin.py` (`get_issue_for_status`)
- `src/mcp_workspace/github_operations/issues/cache.py` (`set_issue_labels_in_cache`)
- `src/mcp_workspace/server.py` (new tool, `github_label_list`, `_rate_limit_message`, `_check_labels` wording, docstrings)
- `vulture_whitelist.py` (new tool)
- `tests/github_operations/conftest.py` (receives the `cache_dir` fixture)
- `tests/github_operations/caching/conftest.py` (deleted — fixture moved up)
- `tests/github_operations/caching/test_store.py`
- `tests/github_operations/issues/test_labels_mixin.py`
- `tests/github_operations/issues/test_cache_update.py`
- `tests/github_operations/test_github_write_tools_labels_pr.py`
- `tests/github_operations/test_github_write_tools_reference.py`
- `SECURITY.md`, `README.md`, `tests/LLM_Test.md`
- `.claude/CLAUDE.md`, `.claude/settings.local.json`

## Steps

1. `new_expiry(max_age)` + `caching/labels.py` (`get_cached_labels`)
2. `github_label_list` via the label cache + rate-limit rendering + fixture move
3. `LabelsMixin.get_issue_for_status`
4. `set_issue_labels_in_cache` in `issues/cache.py`
5. `issues/status.py` — `set_issue_status`
6. `github_issue_set_status` tool + `_check_labels`/docstring wording
7. Docs and `.claude/` config

## Checks (every step)

`mcp__mcp-tools-py__run_pylint_check`, `run_pytest_check` (`extra_args: ["-n", "auto"]`),
`run_mypy_check`; also `run_lint_imports_check` when the step adds imports
between packages. Run `run_format_code` before committing.
