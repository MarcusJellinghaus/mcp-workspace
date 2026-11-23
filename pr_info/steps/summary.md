# Summary — #340 Reference tools: read from origin/<default> with auto-fetch

## Goal

`read_reference_file`, `search_reference_files` and `list_reference_directory` return the
reference project's upstream `origin/<default>` (at most one fetch interval old, default
15 min), whatever state the local checkout's working tree is in. Normal results look exactly
like today's; a note appears only when the fetch failed, or when a git repo has no usable
`origin` default branch (then the local folder is read, as today). `git(…, reference_name=…)`
uses the same auto-fetch. `git log` gains pickaxe (`-S<text>`, `-G<regex>`).

The issue body (#340) is the authoritative spec: Decisions, Constraints & Rationale and
Acceptance criteria apply to every step. This summary only fixes the design used to meet them.

## Architectural / design changes

### 1. Reads come from git objects, not the working tree

A new `git_operations/ref_snapshot.py` owns all GitPython access for reading at the ref:

```
open_ref_snapshot(path, name)  (context manager, sync, one Repo per call, closed at exit)
    -> RefFallback.NOT_A_REPO   plain folder / broken .git / missing path  → local read, no note
    -> RefFallback.NO_DEFAULT   git repo, no origin or no default ref      → local read + note
    -> RefSnapshot              ref ("origin/main"), sha, where ("origin/main @ 03d1741"),
                                list_files(), read_bytes(path)
```

- Default ref: `refs/remotes/origin/HEAD` → `…/origin/main` → `…/origin/master`, falling
  through only on `BadName`. The SHA is resolved once per call (it is a field of the snapshot).
- `list_files()` = `ls-tree -r -z <sha>` order, blobs only (symlinks `120000` and gitlinks skipped).
- `read_bytes(path, display_path)` raises `FileNotFoundError` (names the caller's path, ref +
  short SHA, case hint), `IsADirectoryError` (today's text, caller's path), or `ValueError`
  for any git failure — never a GitPython exception type.

### 2. `file_tools` works on injected content (no GitPython in `file_tools`)

- `file_operations.read_content(data: bytes, file_path, …)` — same line loop as `read_file`
  (slicing, line numbers, max-lines note) on bytes decoded with `TextIOWrapper` semantics
  (identical universal newlines). `read_file` and `read_content` share `_validate_read_args`
  and `_render_lines`.
- `file_operations.decode_lines(data) -> list[str]` — same decoding, for search.
- `search.search_paths(files, read_lines, …)` — the search engine on a file list plus a
  `read_lines(path)` callable; `search_files(project_dir, …)` becomes a thin wrapper.
- `path_utils.ref_relative_path(path, root) -> str` — lexical path normalisation at the ref.

### 3. Throttled auto-fetch, per server, in one worker thread

- `git_operations/origin_fetch.py`: `fetch_origin(path, timeout) -> FetchOutcome(attempted, failure)`.
  Opens the repo itself first (no parent search), skips when there is no `origin`, runs the
  exact fetch command from the issue through `run_git_timed`, retries once unless timed out.
- `toolset/_reference_freshness.py` (sync): `fetch_if_stale`, `mark_fetched`,
  `fetch_failure_note`, `fallback_note`, `with_notes`. Staleness is judged on a monotonic
  clock against the last completed attempt; a per-project `threading.Lock` is taken and
  staleness re-checked, so queued readers wait for the fresh result and never fetch twice.
- Every reference tool call does: `await reference_project_path(...)` (lazy clone; a fresh
  clone counts as fetched) → **one** `asyncio.to_thread(...)` running fetch-if-stale →
  `open_ref_snapshot` → read/list/search → notes. All blocking work (fallback path included)
  is off the event loop.

Design note: the fetch opens its own short-lived `Repo` (inside `fetch_origin`) before the
read opens the snapshot's `Repo`. Both are opened and closed in the same worker thread and
never cached, which keeps the issue's lifetime rule, guarantees the read sees the refs the
fetch just wrote, and avoids a callback between the two. Repo opening spawns no process.

### 4. State moves into `WorkspaceContext`

`WorkspaceContext` gains two defaulted fields after `enforce_base_branch_format`:

- `reference_fetch_interval_minutes: int = 15` (`0` = auto-fetch off, no fetch-failure note)
- `reference_state: ReferenceState` — clone locks, clone-failure cache (moved from module
  globals in `reference_projects.py`), fetch locks, fetch records.

`ensure_available(project, *, locks, failures)` returns `True` after a fresh clone, else `None`.
`clear_clone_failure_cache` is removed.

### 5. Notes

```
[reference <name>: fetch failed (<reason>) — read origin/main @ 03d1741]
[reference <name>: fetch failed (<reason>)]          ← no ref known (git tool, or NO_DEFAULT)
[reference <name>: no usable origin default branch — read the local folder]
```

Placement: read → own line after the content; search → `freshness` key; list → one trailing
entry; git → trailing line. Both notes → fetch-failure first, joined by `\n`. Error results
keep their exception type (`with_notes`) and carry the notes in the message; the error is
raised outside the `except` block.

### 6. Setting plumbing

CLI `--reference-fetch-interval-minutes` (non-negative) → `run_server` → `create_server` →
`tool_specs(reference_fetch_interval_minutes=…)` (negative → `ValueError`) → `WorkspaceContext`.
Default constant `DEFAULT_REFERENCE_FETCH_INTERVAL_MINUTES = 15` in `reference_projects.py`
(importable by `main`, `server` and `toolset` without loading GitPython).

### 7. Small independent git changes

- `run_git_timed` names the command after leading `-c key=value` pairs ("git fetch …").
- `git log` allowlist: `-S<text>`, `-G<regex>` (attached form only), `--pickaxe-regex`, `--pickaxe-all`.

## Module boundaries (unchanged contracts)

- Only `git_operations.*` imports `git`; `file_tools` and `toolset` import `git_operations`
  lazily inside functions, so server startup stays free of GitPython.
- Layers: `toolset` → `file_tools` / `reference_projects` → `git_operations` → `utils`.

## Files

### Created
- `src/mcp_workspace/git_operations/ref_snapshot.py`
- `src/mcp_workspace/git_operations/origin_fetch.py`
- `src/mcp_workspace/toolset/_reference_freshness.py`
- `tests/git_operations/test_ref_snapshot.py`
- `tests/git_operations/test_origin_fetch.py`
- `tests/file_tools/test_read_content.py`
- `tests/file_tools/test_search_paths.py`
- `tests/file_tools/test_ref_relative_path.py`
- `tests/toolset/test_reference_freshness.py`
- `tests/test_reference_reads_at_ref.py`

### Modified
- `src/mcp_workspace/git_operations/_subprocess_git.py` — command naming
- `src/mcp_workspace/git_operations/arg_validation.py` — pickaxe flags
- `src/mcp_workspace/file_tools/file_operations.py` — `read_content`, `decode_lines`, shared helpers
- `src/mcp_workspace/file_tools/search.py` — `search_paths`
- `src/mcp_workspace/file_tools/path_utils.py` — `ref_relative_path`
- `src/mcp_workspace/reference_projects.py` — `ensure_available` signature, constant, globals removed
- `src/mcp_workspace/toolset/_context.py` — `ReferenceState`, `FetchRecord`, new fields
- `src/mcp_workspace/toolset/__init__.py` — `reference_fetch_interval_minutes` keyword
- `src/mcp_workspace/toolset/reference.py` — reads at the ref, `_reference_call`, docstrings
- `src/mcp_workspace/toolset/git.py` — auto-fetch for `reference_name`, docstring
- `src/mcp_workspace/server.py` — `run_server` parameter, `_INSTRUCTIONS`
- `src/mcp_workspace/main.py` — CLI flag + validation, usage/option text
- `vulture_whitelist.py` — drop `_.clear_clone_failure_cache`
- `README.md`, `SECURITY.md`, `docs/file-access.md`, `docs/ARCHITECTURE.md`,
  `docs/LIBRARY_USE.md`, `tests/LLM_Test.md`
- Tests: `tests/git_operations/test_subprocess_git.py`, `tests/git_operations/test_arg_validation.py`,
  `tests/git_operations/test_read_operations.py`, `tests/test_reference_projects_utils.py`,
  `tests/test_reference_projects_mcp_tools.py`, `tests/test_reference_search_mcp_tools.py`,
  `tests/test_reference_projects_git.py`, `tests/test_tool_refusals_mcp_layer.py`,
  `tests/test_credential_scrubbing.py`, `tests/test_main.py`, `tests/test_server.py`,
  `tests/toolset/test_toolset.py`, `tests/test_tool_descriptions.py`,
  `tests/test_server_instructions.py`

## Steps

1. `run_git_timed` names the command after `-c` pairs
2. `git log` pickaxe flags
3. `read_content` / `decode_lines` — the read line loop on bytes
4. `search_paths` — search engine on an injected file list and reader
5. `ref_relative_path` — lexical paths at the ref
6. `ref_snapshot` — reading at `origin/<default>` via GitPython
7. `origin_fetch` — fetch with retry
8. Clone state moves into `WorkspaceContext`; `ensure_available` reports a clone
9. `reference_fetch_interval_minutes` setting (tool_specs, server, CLI)
10. Throttled auto-fetch + notes; `git` tool uses it
11. Read and list read at the ref (`_reference_call`, fallback, notes)
12. Search reads at the ref (`search_paths` with a blob reader, `freshness`, `skipped_files`)
13. Tool docstrings, server instructions, description tests
14. Documentation
