# Step 12 — Search reads at the ref

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_12.md`.
> Write the tests first, then the implementation. Use the MCP tools from `.claude/CLAUDE.md`.
> Run pylint, pytest (`extra_args: ["-n", "auto"]`), mypy, lint-imports and vulture; all
> must pass. Also run the performance tests serially
> (`run_pytest_check(markers=["performance"], extra_args=["-n", "0"])`). Run
> `run_format_code`, then make exactly one commit for this step.

## WHERE

- `src/mcp_workspace/toolset/reference.py`: `search_reference_files` only
- `tests/test_reference_reads_at_ref.py` (add the search cases)
- Existing tests to adapt (search only):
  - `tests/test_reference_search_mcp_tools.py`
  - `tests/test_tool_refusals_mcp_layer.py`: `test_search_tools_return_no_protected_content`
    (the `search_reference_files` rows)
  - `tests/test_reference_path_rules.py`: the search assertions
  - any other search test using a real git repo (pass `reference_fetch_interval_minutes=0`
    where the test is not about fetching)

## WHAT

```python
# search_reference_files, via step 11's _reference_call
at_ref = lambda snap: search_paths(
    snap.list_files(), lambda p: decode_lines(snap.read_bytes(p)),
    glob, pattern, context_lines, max_results, max_result_lines,
)
local  = lambda path: search_files_util(project_dir=path, glob=..., ...)   # today's call
result, notes = await _reference_call(ctx, reference_name, at_ref, local)
if notes: result["freshness"] = "\n".join(notes)
return result
```

(The docstring's Returns section, which lists `freshness`, is updated in step 13.)

## HOW

- `search_paths` and `decode_lines` are plain `file_tools` imports. The search, blob decode
  and line splitting run inside `_reference_call`'s worker thread, like read and list.
- Tree paths come straight from `snap.list_files()` (`git ls-tree -r` order) and never go
  through filesystem normalisation.
- Blob-read failures from `read_bytes` are `ValueError` / `OSError`, so `search_paths` puts
  them in `skipped_files`. A non-UTF-8 blob raises `UnicodeDecodeError` in `decode_lines`,
  which is a silent skip, as today.
- The local fallback keeps calling `search_files_util` by its current name, so existing
  patches keep working.
- `freshness` is a string; when both notes apply they are joined by `\n`, fetch-failure first
  (the order comes from `_reference_call`).

## DATA

`{..., "freshness": "[reference x: …]"}` — key present only when there are notes.

## Tests (write first): `tests/test_reference_reads_at_ref.py`

Use the bare-origin fixtures; interval `0` unless the test is about fetching.
- Feature branch, dirty working tree, and behind-origin checkouts: search returns the
  origin/main content (a symbol present only upstream is found; a local-only one is not);
  no `freshness` key.
- Search at the ref matches working-tree semantics: glob (win32 case-insensitive), regex,
  `context_lines`, `max_results` truncation in `git ls-tree -r` order, `glob_note`.
- A blob that can't be read (patch `RefSnapshot.read_bytes` to raise `ValueError` for one
  path) → that path in `skipped_files`, others still searched; a binary blob → silently
  skipped.
- Really missing blob, no patching of `RefSnapshot.read_bytes`: in a work clone, delete the
  loose object file of one upstream file's blob (same setup as step 6's missing-blob test;
  skip if the object stays packed) → a content search (`pattern` matching every file) lists
  that path in `skipped_files` and still returns matches from the other files.
- CRLF / lone-CR files: search line numbers equal the read tool's line numbers.
- Symlink / gitlink pushed upstream → absent from search results.
- Tracked file matching `.gitignore` is found at the ref; an untracked local file is not.
- Git repo without `origin` → local search result + `freshness` with the fallback note.
- Plain folder → local search result, no `freshness` key.
- Fetch failure (patched `fetch_origin` → `FetchOutcome(True, "boom")`) → `freshness` holds
  the fetch-failure note; with origin present + fetch failed + no default ref → `freshness`
  holds both notes joined by `\n`, fetch-failure first.

Existing tests: `tests/test_reference_search_mcp_tools.py` patches `search_files_util` on
non-existent paths and keeps passing (silent fallback). The `search_reference_files` rows of
`tests/test_tool_refusals_mcp_layer.py` use git references without `origin`; they now get a
`freshness` key, so adjust any exact-dict assertions (protected content must still be
absent). `tests/test_reference_path_rules.py`'s `.git` holds only `config`, so its search
assertions should stay unchanged; if one fails, adjust it to the fallback note rather than
changing the fixture.
