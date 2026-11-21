# Step 2 — `search_files` glob fix

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement this step
> (`pr_info/steps/step_2.md`). Step 1 is done: `GlobPattern` exists in
> `mcp_workspace.file_tools.access_rules`. If it does not, write one line to
> `pr_info/.blocked.txt` and stop. TDD: write the tests first, see them fail,
> then implement. Run `run_format_code`, pylint, pytest
> (`extra_args=["-n", "auto"]`, plus the serial performance run
> `markers=["performance"], extra_args=["-n", "0"]`), mypy, ruff, vulture
> and lint-imports; all must pass. Then make exactly one commit.

## WHERE

- `src/mcp_workspace/file_tools/search.py` (`_match_glob`, imports)
- `tests/file_tools/test_search.py`
- `docs/ARCHITECTURE.md` (module diagram line for `access_rules.py`, ~line 161)
- `docs/release-notes.md` (new top section)

## WHAT

- `_match_glob(glob: str, files: list[str]) -> list[str]`: signature and
  docstring unchanged.
- New private helper so the message is written once:
  ```python
  def _nothing_matches(glob: str) -> ValueError:
      """Build the error for a glob that cannot match anything."""
  ```
  It returns the existing message, unchanged:
  `f"Glob pattern {glob!r} matches nothing by construction (gitignore comment, blank, negation-only, or unparseable pattern)"`.

## HOW

- Add `from mcp_workspace.file_tools.access_rules import GlobPattern`.
- Remove `import sys` (unused once `.lower()` is gone). Keep `import re`,
  since it is used for `re.error`.
- Remove `win32`, `_norm` and both `.lower()` calls.

## ALGORITHM

```
try:
    spec = GitIgnoreSpec.from_lines([glob], GlobPattern)
except re.error as exc:
    raise _nothing_matches(glob) from exc
if not any(isinstance(p, RegexPattern) and p.regex is not None and p.include for p in spec.patterns):
    raise _nothing_matches(glob)
return [f for f in files if spec.match_file(f)]
```

Only `re.error` is caught. pathspec's own `ValueError`s (`"!"`, `"a\\"`) keep
propagating, so `test_malformed_glob_still_raises_value_error` must keep passing.

## DATA

Returns the subset of `files` (order kept) matching `glob`, case-insensitive
on win32.

## Tests (write first) — `tests/file_tools/test_search.py`

1. `TestSearchFilesGlobValidation.test_glob_matching_nothing_by_construction_raises`:
   add `"[b-a]x"` to the parametrize list.
2. A module-level fixture:
   ```python
   @pytest.fixture
   def win32(monkeypatch: pytest.MonkeyPatch) -> None:
       """Make spec builds take the win32 (case-insensitive) branch."""
       monkeypatch.setattr(sys, "platform", "win32")
   ```
3. In `TestSearchFilesGlobOnly`, next to
   `test_windows_case_insensitive_match_preserved`, which stays as is and
   skip-gated, add tests that call `_match_glob` directly. These stay at
   unit level; never monkeypatch around `search_files`:
   ```python
   @pytest.mark.usefixtures("win32")
   @pytest.mark.parametrize(
       ("glob", "path"),
       [("README.md", "readme.md"), ("[Z-a]x", "zx"), ("[Z-a]x", "_x"), ("[A-z]x", "_x")],
   )
   def test_win32_glob_matches_case_insensitively(self, glob, path):
       assert _match_glob(glob, [path]) == [path]

   @pytest.mark.usefixtures("win32")
   def test_win32_reversed_range_raises_value_error(self):
       with pytest.raises(ValueError, match="matches nothing by construction"):
           _match_glob("[b-a]x", ["a.py"])
   ```
   Import `_match_glob` from `mcp_workspace.file_tools.search`.

Tests 1 and 3 (`[Z-a]x`, `[A-z]x`, `[b-a]x`) fail before the change. The
POSIX-only `test_glob_is_case_sensitive_on_posix` stays platform-gated and
unchanged.

## Docs

- `docs/ARCHITECTURE.md`, diagram line:
  `file_tools/access_rules.py            parse + match the rules file (pure)`
  becomes
  `file_tools/access_rules.py            parse + match the rules file; case-insensitive pattern classes (also used by search.py) (pure)`.
  If that is too long for the diagram, keep the line short and add the
  `search.py` use to the `access_rules.py` bullet below it instead.
- `docs/release-notes.md`: insert at the top, directly under `# Release notes`
  and above the #83 section:
  ```markdown
  ## Next minor release — search_files glob fixes (#405)

  - `search_files` / `search_reference_files`: a glob with a reversed character range (e.g. `[b-a]x`) now raises the documented "matches nothing by construction" `ValueError` instead of `re.error`; on Windows, globs match case-insensitively without lower-casing the pattern, so ranges like `[A-z]` keep their meaning.
  ```

## Commit

`fix(search): case-insensitive globs via (?i), map re.error to ValueError (#405)`
