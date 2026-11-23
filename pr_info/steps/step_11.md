# Step 11 — Read and list read at the ref

`search_reference_files` is unchanged in this step (step 12 moves it to the ref).

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_11.md`.
> Write the tests first, then the implementation. Use the MCP tools from `.claude/CLAUDE.md`.
> Run pylint, pytest (`extra_args: ["-n", "auto"]`), mypy, lint-imports and vulture; all
> must pass. Also run the performance tests serially
> (`run_pytest_check(markers=["performance"], extra_args=["-n", "0"])`). Run
> `run_format_code`, then make exactly one commit for this step.

## WHERE

- `src/mcp_workspace/toolset/reference.py` — `_reference_call`, `_run_reference_read`,
  `read_reference_file`, `list_reference_directory`
- `tests/test_reference_reads_at_ref.py` (new; read and list cases)
- Existing tests to adapt (read / list only):
  - `tests/test_reference_projects_mcp_tools.py` — the read and list tests
  - `tests/test_tool_refusals_mcp_layer.py` — the `read_reference_file` rows of
    `test_file_tool_refusals`
  - `tests/test_reference_path_rules.py` — the read and list assertions
  - any other read/list test using a real git repo (pass `reference_fetch_interval_minutes=0`
    where the test is not about fetching)

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

Tool bodies (docstrings are updated in step 13):

```python
# read_reference_file
def at_ref(snap):
    rel = ref_relative_path(file_path, snap_root)          # snap_root = the project path
    return read_content(snap.read_bytes(rel, file_path), file_path, start_line, end_line,
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
```

## HOW

- `_reference_call` awaits `reference_project_path` (lazy clone; marks fetched), then one
  `asyncio.to_thread(_run_reference_read, ...)`. Everything blocking (fetch, git, blob
  decode, line loop and the local fallback) runs in that thread.
- `ref_snapshot` and `RefSnapshot` are imported lazily inside `_run_reference_read`
  (`TYPE_CHECKING` import for the annotation). `read_content` and `ref_relative_path` are
  plain `file_tools` imports.
- The local fallback keeps calling `require_access`, `read_file_util`,
  `list_accessible_files` and `access_rules_warning` by their current names in
  `toolset.reference`, so existing patches of those names keep working.
- `ref_relative_path` gets `ctx.reference_projects[name].path`; it resolves the root itself.
- `read_bytes` gets the caller's `file_path` as `display_path`, so error texts name it as today.
- At the ref, `.gitignore` and `.mcp-file-access` do not apply (only tracked content exists);
  `.git` spellings and `..` are still refused by `ref_relative_path`.
- `_reference_call` is generic; step 12 reuses it for search unchanged.

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
- list: `[..., "[reference x: no usable origin default branch — read the local folder]"]`

## Tests (write first): `tests/test_reference_reads_at_ref.py`

Use the bare-origin fixtures; interval `0` unless the test is about fetching.
- Feature branch, dirty working tree, and behind-origin checkouts: read and list return the
  origin/main content; no note.
- Behind origin with interval 15 and no manual fetch: the first read auto-fetches and
  returns the new upstream content.
- Dangling `origin/HEAD` → reads `origin/main`.
- Read at the ref: CRLF and lone-CR files give the same line numbers / slices / truncation as
  `read_file` on the same bytes.
- Plain folder, broken `.git`, folder nested in a checkout → local content, no note, no
  fetch (patch `fetch_origin` / `run_git_timed` and assert not called for the nested folder).
- Git repo without `origin` → local content + fallback note in the read line and in the list
  trailing entry (after any `WARNING` first line); no fetch runs.
- Corrupt ref target (step 6 setup) → error result, not a local fallback.
- Not-found names the caller's path, ref + short SHA; case mismatch names the correct
  spelling; directory → `IsADirectoryError` "is not a file"; symlink / gitlink absent from
  list, reading one → not-found.
- Paths: absolute inside the reference folder, backslashes, leading `./` work; `..` →
  traversal error; absolute outside → "outside the project directory"; `.GIT/config` and
  `.git./config` refused at the ref.
- Tracked file matching `.gitignore` is readable and listed at the ref; an untracked local
  file is not.
- Fetch failure (patched `fetch_origin` → `FetchOutcome(True, "boom")`): read succeeds on the
  last-fetched state with the note after the content (new line added when the content has no
  trailing newline, and after the truncation note); list trailing entry; a not-found error
  carries the note; origin present + fetch failed + no default ref → both notes,
  fetch-failure first, also on error results.
- `get_reference_projects()` output unchanged.

Existing tests: read/list tests in `tests/test_reference_projects_mcp_tools.py` that patch
`read_file_util` / `list_accessible_files` on non-existent paths keep passing (silent
fallback; `assert_called_once_with(".", ref_path)` still holds). The `read_reference_file`
rows of `tests/test_tool_refusals_mcp_layer.py` use git references without `origin`; they
now get the fallback note, so adjust any exact-output assertions.
`tests/test_reference_path_rules.py`'s `.git` holds only `config`, so it does not open as a
repo. Expect its read/list assertions unchanged; if one fails, adjust it to the fallback note
rather than changing the fixture.
