# Step 6 — Search `warning` key (gaps 3, 7)

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_6.md`.
> Write the tests first, then the code. Run pylint, pytest (`-n auto`) and mypy until all pass,
> run `run_format_code`, and make exactly one commit.

## Goal

While the rules file is invalid, `search_files` and `search_reference_files` results carry a
`warning` key with the `access_rules_warning` text, in both file and content mode. When the file is
valid or absent, there is no such key. Both tool descriptions say this in one Returns clause.

## WHERE

- `src/mcp_workspace/file_tools/search.py` — `search_files`
- `src/mcp_workspace/toolset/read.py` — `search_files` description
- `src/mcp_workspace/toolset/reference.py` — `search_reference_files` description
- `tests/file_tools/test_search.py`, `tests/file_tools/test_accessible_listing.py`, `tests/test_tool_descriptions.py`
- `docs/file-access.md`, `docs/release-notes.md`

## WHAT

`search_files(...)` keeps its signature. The result dict gains an optional `"warning": str`.

## HOW

- Import `access_rules_warning` in `search.py`, next to the existing `GlobPattern` import from
  `file_tools.access_rules`.
- Keep the `AccessListing` that `list_accessible_files(".", project_dir)` already returns, instead
  of taking only `.files`. This is the single source of the problems, so there is no second load.
- In the `search_files` docstring Returns, add: `Carries a "warning" key with the invalid-rules
  warning while .mcp-file-access is invalid.`

## ALGORITHM

```
listing = list_accessible_files(".", project_dir)
all_files = listing.files
warning = access_rules_warning(listing.problems)
... build result (content mode) / file_result (file mode) as today ...
if warning is not None: result["warning"] = warning      # in both branches
```

## DATA

`{"mode": "file_search", "files": [...], "total_files": n, "truncated": b,
"warning": "WARNING: .mcp-file-access is invalid (line 1: unknown level 'readonly') - writes are
refused and no gitignored path is exposed."}`

## Tool descriptions

Add to the Returns of both `search_files` (`read.py`) and `search_reference_files`
(`reference.py`):

`Gitignored paths that .mcp-file-access exposes are included; a "warning" key appears while that
rules file is invalid.`

## Tests (write first)

- **`tests/file_tools/test_search.py`** (mirrors `file_tools/search.py`): call `search_files`
  directly on a project whose rules file is invalid.
  - File mode (`glob="*.txt"`) and content mode (`pattern="MARKER"`) both have
    `result["warning"] == access_rules_warning(load_access_rules(project).problems)`.
  - A valid rules file and an absent one both give `"warning" not in result`.
- **`tests/file_tools/test_accessible_listing.py`, `TestReferenceListing`** (tool-level case only): `search_reference_files("ref", glob="**/*.log")` with an
  invalid reference rules file returns a result with a `"warning"` key.
- **`tests/test_tool_descriptions.py`:** for `search_files` and `search_reference_files`, the
  description contains `"warning" key` and `.mcp-file-access`.

## Docs

- **`docs/file-access.md`, "Invalid rules file" list:** add a bullet for the `warning` key in
  `search_files` / `search_reference_files` results, with the same text as the listing warning.
- **`docs/file-access.md`, "Listing" paragraph:** remove any wording that says search has no warning.
- **`docs/release-notes.md`:** add a #404 bullet for the search `warning` key.

## Commit

`feat(search): add warning key while .mcp-file-access is invalid (#404)`
