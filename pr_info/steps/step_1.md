# Step 1 — Migrate the glob matcher to `GitIgnoreSpec`

See [summary.md](./summary.md) for context and rationale. One commit: test + implementation
+ checks.

## WHERE

- `tests/file_tools/test_search.py` — append one test class at end of file.
- `src/mcp_workspace/file_tools/search.py` — lines 8, 18, 57.

## WHAT

No function signatures change. `_match_glob(glob: str, files: List[str]) -> List[str]` keeps
its signature, return type and `ValueError` contract.

New test:

```python
class TestSearchFilesNoDeprecationWarning:
    @pytest.mark.filterwarnings("error::DeprecationWarning")
    def test_search_files_with_glob_emits_no_deprecation_warning(
        self, project_dir: Path
    ) -> None: ...
```

## HOW

**Test (write first — it must fail before the implementation change).**

Append to `tests/file_tools/test_search.py`. `pytest`, `Path` and `search_files` are already
imported at lines 4–8; no new imports needed.

```python
class TestSearchFilesNoDeprecationWarning:
    """The glob matcher must not route through a deprecated pathspec name."""

    @pytest.mark.filterwarnings("error::DeprecationWarning")
    def test_search_files_with_glob_emits_no_deprecation_warning(
        self, project_dir: Path
    ) -> None:
        """A glob-bearing search compiles its pattern without deprecation."""
        (project_dir / "a.py").write_text("x = 1\n")

        result = search_files(project_dir, glob="**/*.py")

        assert result["mode"] == "file_search"
```

Three properties this relies on, all load-bearing:

- **The `glob` argument is mandatory.** A globless `search_files` never reaches
  `_match_glob` and emits nothing, so the test would pass vacuously without it.
- **The filter is blanket** (`error::DeprecationWarning`, not a message match) — the
  stronger pin, and it fires on nothing else in this call path today.
- **Order-independence under `-n auto`**: pytest applies `warnings.simplefilter("always")`
  before its own filters when handling the mark, so a warning already registered by an
  earlier test in the same worker still re-fires here.

The `assert` on the result is not the point of the test; it keeps the call's return value
used and documents that the search ran.

**Implementation.**

`search.py:8` — drop `PathSpec`, which becomes unused and would fail ruff and pylint:

```python
from pathspec import GitIgnoreSpec, RegexPattern
```

`RegexPattern` stays: it is used by the `usable` check at line 60.

`search.py:57`:

```python
spec = GitIgnoreSpec.from_lines([glob.lower() if win32 else glob])
```

`GitIgnoreSpec.from_lines` takes `lines` first and defaults `pattern_factory` to `None`,
resolving to `GitIgnoreSpecPattern` — no factory argument, no registry lookup.

`search.py:18` — the comment currently names the deprecated registry entry
(`# Braces are the one silent-zero case that cannot raise: gitwildmatch compiles`). Reword to
say "gitignore semantics" rather than naming a class, matching the vocabulary already used at
lines 24, 45, 162 and 180. Leave the rest of the comment unchanged.

Leave lines 59–62 (`usable`), the win32 lowercasing at line 56, and `_norm` alone.

## ALGORITHM

`_match_glob` keeps its shape; only the second line changes:

```
win32   = platform is win32
spec    = GitIgnoreSpec.from_lines([lowercased glob if win32 else glob])   # was PathSpec.from_lines("gitwildmatch", ...)
usable  = any pattern is a RegexPattern with regex not None and include true
if not usable: raise ValueError("matches nothing by construction ...")
return [f for f in files if spec.match_file(normalised f)]
```

## DATA

Unchanged. `_match_glob` returns `List[str]` of project-relative paths; `search_files`
returns its `file_search` / `content_search` dict as before. `spec` is a `GitIgnoreSpec`
(a `PathSpec[GitIgnoreSpecPattern]`) instead of a `PathSpec`; it is a local, never annotated,
never returned, and both classes expose the `.patterns` and `.match_file` members used here.

## Verification

Run in order:

1. `mcp__mcp-tools-py__run_format_code`
2. `mcp__mcp-tools-py__run_pylint_check`
3. `mcp__mcp-tools-py__run_pytest_check` with `extra_args: ["-n", "auto"]`
4. `mcp__mcp-tools-py__run_mypy_check`

The real acceptance signal is that the pre-existing #249 tests in
`tests/file_tools/test_search.py` pass **untouched** — in particular
`test_glob_matching_nothing_by_construction_raises` over
`["", "   ", "#*.py", "!*.py", "[", "[a-", "a[b"]` and
`test_malformed_glob_still_raises_value_error` over `["!", "a\\"]`. If any of those need
editing, the migration changed behaviour and the approach is wrong — stop rather than adjust
the test.

Then commit (tests + implementation together) and tick the task in
`pr_info/TASK_TRACKER.md`.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`, then implement step 1.
>
> Work test-first: append the `TestSearchFilesNoDeprecationWarning` class to
> `tests/file_tools/test_search.py` exactly as specified, run
> `mcp__mcp-tools-py__run_pytest_check` with
> `extra_args: ["-n", "auto", "tests/file_tools/test_search.py"]` and confirm the new test
> **fails** on the current `gitwildmatch` matcher. Then apply the three edits to
> `src/mcp_workspace/file_tools/search.py` (lines 8, 18, 57) and confirm the whole file's
> tests pass.
>
> Do not touch `pyproject.toml`, the `usable` check, the win32 lowercasing, or any of the
> "gitignore/wildmatch semantics" wording in `server.py`, `server_reference_tools.py` or the
> other `search.py` docstrings — the summary explains why each stays. Do not add
> glob-behaviour tests. Do not edit the #249 tests; if they fail, the migration is wrong.
>
> Finish with format, pylint, pytest (`-n auto`), mypy, then one commit and a tick in
> `pr_info/TASK_TRACKER.md`.
