# Step 8 — Reference label ` (not committed)` (gap 13c)

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_8.md`.
> Write or adjust the tests first, then the code. Run pylint, pytest (`-n auto`) and mypy until all
> pass, run `run_format_code`, and make exactly one commit.

## Goal

`list_reference_directory` labels a gitignored file exposed by that project's rules with
` (not committed)`, and nothing else: every reference file is read-only, so read-only/read-write
labels would mislead. The data comes from a new defaulted `AccessListing` field, not from parsing
`notes`.

## WHERE

- `src/mcp_workspace/file_tools/file_access.py` — `AccessListing`, `_exposure_skip`, `list_accessible_files`
- `src/mcp_workspace/toolset/reference.py` — `list_reference_directory`
- `tests/file_tools/test_accessible_listing.py`, `tests/test_tool_descriptions.py`
- `docs/file-access.md`, `README.md`, `docs/release-notes.md`

## WHAT

```python
@dataclass(frozen=True)
class AccessListing:
    files: list[str]
    notes: dict[str, str]
    problems: list[str]
    exposed_ignored: frozenset[str] = frozenset()   # gitignored files a rule exposes

def _exposure_skip(
    start: Path, project_dir: Path, rules: AccessRules,
    notes: dict[str, str], exposed: set[str],
) -> Callable[[Path], bool]: ...

# toolset/reference.py
_NOTE_EXPOSED = "(not committed)"
```

## HOW

- **`_exposure_skip`:** in `skip()`, at the point where an ignored file is kept, add `exposed.add(rel)`
  right before `note(rel, is_ignored=True)`. Only files reach that point, and every one of them is
  listed, so no filtering is needed. While the rules file is invalid no ignored file is kept, so
  the set is empty. Document the `exposed` arg.
- **`list_accessible_files`:** create `exposed: set[str] = set()`, pass it in, and return
  `exposed_ignored=frozenset(exposed)`.
- **`AccessListing` docstring:** document `exposed_ignored`. It is used only by
  `list_reference_directory`.
- **Other constructors:** tests that build `AccessListing(files=…, notes=…, problems=…)` directly
  (`tests/test_reference_projects_mcp_tools.py`, `tests/test_server_list_directory.py`) keep working
  through the default.

## ALGORITHM (`list_reference_directory`)

```
listing = list_accessible_files(".", ref_path)
entries = [f"{rel} {_NOTE_EXPOSED}" if rel in listing.exposed_ignored else rel
           for rel in listing.files]
warning = access_rules_warning(listing.problems)
return [warning, *entries] if warning is not None else entries
```

## DATA

`["README.md", "logs/a.log (not committed)", "logs/sub/b.log (not committed)"]`

## Description (`list_reference_directory` Returns)

Replace "can be passed straight back to `read_reference_file`" with:

"A file line ends in `` (not committed)`` for a gitignored file that project's .mcp-file-access
exposes; strip that suffix before passing the path to `read_reference_file`."

Keep the forward-slash and invalid-file warning sentences.

## Tests (write or adjust first)

**`tests/file_tools/test_accessible_listing.py`:**
- Unit test: with `read-only /logs/` over a gitignored `logs/`, `list_accessible_files(".", p)`
  gives `exposed_ignored == frozenset({"logs/a.log", "logs/sub/b.log"})`. Tracked files are not in
  it, and it is empty while the rules file is invalid.
- `TestReferenceListing.test_list_reference_directory_includes_exposed`:
  - expect `"logs/a.log (not committed)"` and `"logs/sub/b.log (not committed)"`;
  - `x.log` stays absent;
  - no entry contains `(read-only` or `(read-write`.
- Adjust any other reference-listing assertion on a gitignored path.

**`tests/test_tool_descriptions.py`:** the `list_reference_directory` description contains
`(not committed)` and `strip that suffix`.

## Docs

- **`docs/file-access.md`, "Listing" paragraph:** `list_reference_directory` marks exposed gitignored files
  ` (not committed)` and nothing else; `search_files` / `search_reference_files` stay unmarked.
- **`README.md`, "List Reference Directory" features:** add the label.
- **`docs/release-notes.md`:**
  - Add a #404 bullet for the reference label.
  - The #83 bullet saying `list_reference_directory` includes exposed paths "unmarked" gets
    ` Changed in #404, see above.`

## Commit

`feat(reference): label exposed gitignored files in list_reference_directory (#404)`
