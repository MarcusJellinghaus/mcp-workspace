# Step 11 — Read, list and search read at the ref

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_11.md`.
> Write the tests first, then the implementation. Use the MCP tools from `.claude/CLAUDE.md`.
> Run pylint, pytest (`extra_args: ["-n", "auto"]`), mypy, lint-imports and vulture; all
> must pass. Also run the performance tests serially
> (`run_pytest_check(markers=["performance"], extra_args=["-n", "0"])`). Run
> `run_format_code`, then make exactly one commit for this step.

## WHERE

- `src/mcp_workspace/toolset/reference.py`
- `tests/test_reference_reads_at_ref.py` (new)
- Existing tests to adapt: `tests/test_reference_projects_mcp_tools.py`,
  `tests/test_reference_search_mcp_tools.py`, `tests/test_tool_refusals_mcp_layer.py`,
  `tests/test_reference_path_rules.py`, and any other reference-tool test using a real git
  repo (pass `reference_fetch_interval_minutes=0` where the test is not about fetching).

## WHAT

```python
T = TypeVar("T")

async def _reference_call(
    ctx: WorkspaceContext,
    name: str,
    at_ref: Callable[["RefSnapshot"], T],
    local: Callable[[Path], T],
) -> tuple[T, list[str]]:
    """Run one reference read at origin/<default> (or the local folder) in a worker thread.

    Returns:
        The result and the notes to attach (fetch-failure first, then fallback).
    """
```

Tool bodies (docstrings are updated in step 12):

```python
# read_reference_file
def at_ref(snap):
    rel = ref_relative_path(file_path, snap_root)          # snap_root = the project path
    return read_content(snap.read_bytes(rel), file_path, start_line, end_line,
                        with_line_numbers, ctx.read_max_lines)
def local(path):                                            # today's code, unchanged
    require_access(file_path, path, FileAccess.READ_ONLY)
    return read_file_util(file_path, project_dir=path, ...)
content, notes = await _reference_call(ctx, reference_name, at_ref, local)
return content if not notes else content + ("" if not content or content.endswith("\n") else "\n") + "\n".join(notes)

# list_reference_directory
at_ref = lambda snap: snap.list_files()
local  = today's listing incl. the WARNING-first line
return files if not notes else [*files, "\n".join(notes)]

# search_reference_files
at_ref = lambda snap: search_paths(snap.list_files(), lambda p: decode_lines(snap.read_bytes(p)), glob, pattern, ...)
local  = lambda path: search_files_util(project_dir=path, glob=..., ...)
if notes: result["freshness"] = "\n".join(notes)
```

## HOW

- `_reference_call` awaits `reference_project_path` (lazy clone; marks fetched), then one
  `asyncio.to_thread(_run_reference_read, ...)`. Everything blocking — fetch, git, blob
  decode, line loop, search, and the local fallback — runs in that thread.
- `ref_snapshot` and `RefSnapshot` are imported lazily inside `_run_reference_read`
  (`TYPE_CHECKING` import for the annotation). `read_content`, `decode_lines`,
  `search_paths`, `ref_relative_path` are plain `file_tools` imports.
- The local fallback keeps calling `require_access`, `read_file_util`, `search_files_util`,
  `list_accessible_files`, `access_rules_warning` by their current names in
  `toolset.reference`, so existing patches of those names keep working.
- `ref_relative_path` gets `ctx.reference_projects[name].path`; it resolves the root itself.
- At the ref, `.gitignore` and `.mcp-file-access` do not apply (only tracked content exists);
  `.git` spellings and `..` are still refused by `ref_relative_path`.

## ALGORITHM (`_run_reference_read`, sync)

```
fetch_if_stale(ctx, name, path)
notes: list[str] = []
try:
    with open_ref_snapshot(path, name) as snap:
        notes = _notes(ctx, name, snap)
        result = at_ref(snap) if isinstance(snap, RefSnapshot) else local(path)
except Exception as exc:          # incl. ValueError from snapshot resolution (before notes)
    notes = notes or _notes(ctx, name, None)
    if not notes: raise
    error = with_notes(exc, notes)
else:
    return result, notes
raise error

_notes(ctx, name, snap):
    where = snap.where if isinstance(snap, RefSnapshot) else None
    out = [n for n in (fetch_failure_note(ctx, name, where),) if n]
    if snap is RefFallback.NO_DEFAULT: out.append(fallback_note(name))
    return out
```

## DATA

- read: `"<content>\n[reference x: fetch failed (…) — read origin/main @ 03d1741]"`
- search: `{..., "freshness": "[reference x: …]"}` (key only when there are notes)
- list: `[..., "[reference x: no usable origin default branch — read the local folder]"]`

## Tests (write first) — `tests/test_reference_reads_at_ref.py`

Use the bare-origin fixtures; interval `0` unless the test is about fetching.
- Feature branch, dirty working tree, and behind-origin checkouts: read, list and search all
  return the origin/main content; no note.
- Behind origin with interval 15 and no manual fetch: the first read auto-fetches and
  returns the new upstream content.
- Dangling `origin/HEAD` → reads `origin/main`.
- Search at the ref: glob (win32 case-insensitive), regex, `context_lines`, `max_results`
  truncation in `git ls-tree -r` order, `glob_note`, a blob that can't be read (patch
  `RefSnapshot.read_bytes` to raise `ValueError` for one path) → `skipped_files`; a binary
  blob → silently skipped.
- Read at the ref: CRLF and lone-CR files give the same line numbers / slices / truncation as
  `read_file` on the same bytes.
- Plain folder, broken `.git`, folder nested in a checkout → local content, no note, no
  fetch (patch `fetch_origin` / `run_git_timed` and assert not called for the nested folder).
- Git repo without `origin` → local content + fallback note in each placement (read line,
  list trailing entry after any `WARNING` first line, `freshness`); no fetch runs.
- Corrupt ref target (step 6 setup) → error result, not a local fallback.
- Not-found names ref + short SHA; case mismatch names the correct spelling; directory →
  `IsADirectoryError` "is not a file"; symlink / gitlink absent from list and search,
  reading one → not-found.
- Paths: absolute inside the reference folder, backslashes, leading `./` work; `..` →
  traversal error; absolute outside → "outside the project directory"; `.GIT/config` and
  `.git./config` refused at the ref.
- Tracked file matching `.gitignore` is readable at the ref; an untracked local file is not.
- Fetch failure (patched `fetch_origin` → `FetchOutcome(True, "boom")`): read succeeds on the
  last-fetched state with the note after the content (new line added when the content has no
  trailing newline, and after the truncation note); search `freshness`; list trailing entry;
  a not-found error carries the note; origin present + fetch failed + no default ref → both
  notes, fetch-failure first, also on error results.
- `get_reference_projects()` output unchanged.

Existing tests: tests that patch `read_file_util` / `search_files_util` /
`list_accessible_files` on non-existent paths keep passing (silent fallback).
`tests/test_tool_refusals_mcp_layer.py` git references without `origin` now get the
fallback note — adjust exact-output assertions. `tests/test_reference_path_rules.py`'s `.git`
holds only `config`, so it does not open as a repo — expect it unchanged; if it fails,
adjust it to the fallback note rather than changing the fixture.
