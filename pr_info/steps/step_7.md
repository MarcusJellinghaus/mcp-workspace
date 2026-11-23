# Step 7 — Workspace label ` (read-only, not committed)` (gaps 13a, 13b)

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_7.md`.
> Write or adjust the tests first, then the code. Run pylint, pytest (`-n auto`) and mypy until all
> pass, run `run_format_code`, and make exactly one commit.

## Goal

In `list_directory`, a gitignored file exposed `read-only` by a rule is labelled
` (read-only, not committed)`; a tracked read-only file stays ` (read-only)`. The description
lists all three labels and says labels are omitted while the rules file is invalid.

## WHERE

- `src/mcp_workspace/file_tools/file_access.py` — `_NOTE_*` constants, `_exposure_skip.note`, `AccessListing` docstring
- `src/mcp_workspace/toolset/read.py` — `list_directory` description
- `tests/test_file_access_listing.py`, `tests/file_tools/test_accessible_listing.py`, `tests/test_tool_descriptions.py`
- `docs/file-access.md`, `README.md`, `docs/release-notes.md`

## WHAT

```python
_NOTE_READ_ONLY = "(read-only)"
_NOTE_READ_ONLY_NOT_COMMITTED = "(read-only, not committed)"
_NOTE_NOT_COMMITTED = "(read-write, not committed)"
```

## ALGORITHM (`note()` inside `_exposure_skip`)

```
if rules.problems: return
level = _rule_access(rel, rules)[0]
if level is READ_ONLY:
    notes[rel] = _NOTE_READ_ONLY_NOT_COMMITTED if is_ignored else _NOTE_READ_ONLY
elif level is READ_WRITE and is_ignored:
    notes[rel] = _NOTE_NOT_COMMITTED
```

## HOW / DATA

- **`AccessListing.notes` docstring:** "Path to `(read-only)`, `(read-only, not committed)` or
  `(read-write, not committed)` …".
- **`list_directory` Returns:** "A file line may end in `` (read-only)``,
  `` (read-only, not committed)`` or `` (read-write, not committed)``; strip that suffix before
  passing the path to `read_file`. Labels are omitted while ``.mcp-file-access`` is invalid. The
  first line may be a ``WARNING:`` …"

## Tests (write or adjust first)

- **`tests/test_file_access_listing.py`:**
  - The assertion on the `read-only /logs/` listing (`logs/sub/b.log (read-only)`,
    `logs/a.log (read-only)`) changes to the new label.
  - In the `suffix_tools` fixture, `uv.lock` is gitignored and exposed `read-only`, so it now
    renders as `uv.lock (read-only, not committed)`. Update the assertion at
    `tests/test_file_access_listing.py:46` to that string.
  - Only the tracked read-only files `.mcp.json` and `.mcp-file-access` keep the plain
    ` (read-only)` suffix.
- **`tests/file_tools/test_accessible_listing.py`:**
  - Add `READ_ONLY_NOT_COMMITTED_NOTE = "(read-only, not committed)"`.
  - Update the notes assertions for gitignored read-only files, and add one asserting a tracked
    read-only file keeps `READ_ONLY_NOTE`.
- Fix any other test that now fails only because of the changed label.
- **`tests/test_tool_descriptions.py`:** the `list_directory` description contains
  `(read-only, not committed)` and `omitted while`.

## Docs

- **`docs/file-access.md`, "Listing" paragraph:** three labels, gitignored read-only files are
  marked `(read-only, not committed)`, no labels while the rules file is invalid.
- **`README.md`, list_directory section:** the label list.
- **`docs/release-notes.md`:**
  - Add a #404 bullet for the new label.
  - The #83 `list_directory` labels bullet gets ` Changed in #404, see above.`

## Commit

`feat(list_directory): label gitignored read-only files as not committed (#404)`
