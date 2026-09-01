# Step 3 — `glob_note` for brace patterns that match no files

Read [summary.md](./summary.md) first.

Braces are the only member of the silent-zero family with no structural signal:
gitwildmatch compiles a valid literal-brace regex, so detection is textual. They cannot
raise — `{{cookiecutter.project_slug}}` is a real directory name and no escape mechanism
exists.

## WHERE

- `tests/file_tools/test_search.py` — new class `TestSearchFilesGlobNote`
- `src/mcp_workspace/file_tools/search.py` — new module-level constant `_BRACE_NOTE`;
  `search_files` computes `glob_note` once and attaches it to both return paths

## WHAT — tests first

```python
class TestSearchFilesGlobNote:
    def test_brace_glob_with_no_matches_returns_note(self, project_dir: Path) -> None
    def test_brace_glob_note_in_content_search_mode(self, project_dir: Path) -> None
    def test_escaped_brace_also_returns_note(self, project_dir: Path) -> None
    def test_brace_glob_that_matches_files_has_no_note(self, project_dir: Path) -> None
    def test_glob_note_absent_when_glob_matched_but_pattern_did_not(
        self, project_dir: Path
    ) -> None
    def test_plain_glob_with_no_matches_has_no_note(self, project_dir: Path) -> None
```

Assert on `"brace expansion" in result["glob_note"].lower()` for presence, and
`"glob_note" not in result` for absence.

## HOW

`_BRACE_NOTE` sits beside the existing `_MAX_LINE_CHARS` constant. Text names the cause and
the workaround, e.g.:

> Glob matched no files and contains `{`. Brace expansion is not supported — patterns use
> gitignore/wildmatch semantics, where braces are literal. Issue one call per alternative,
> or widen to `*` and filter the results.

The file-search return dict needs an explicit `result: Dict[str, Any] = {...}` annotation
before a key can be added to it, or mypy strict infers a narrower value type.

`_search_content` keeps its current signature. In content mode, set `glob_note` on the
returned dict alongside the existing `note`:

```python
if note is not None:
    result["note"] = note
if glob_note is not None:
    result["glob_note"] = glob_note
```

`note` and its four existing tests must not change — the two keys are independent.

## ALGORITHM

```
matched = _match_glob(glob, all_files) if glob is not None else all_files
glob_note = _BRACE_NOTE if glob is not None and "{" in glob and not matched else None
# ... unchanged content-search / file-search branches ...
# both branches: if glob_note is not None: result["glob_note"] = glob_note
```

Computed once, before the content search runs, so the trigger is the same condition in both
modes. A textual `"{" in glob` covers `{` and `\{` alike — they compile to identical
regexes. It deliberately does **not** fire when the glob matched files but the content
search returned nothing: those braces were legitimate.

## DATA

New optional response key, both modes:

```
"glob_note": str   # present only when the glob contains '{' and matched zero files
```

Existing keys unchanged: `mode`, `files`/`details`, `total_files`/`total_matches`,
`truncated`, `matched_files`, `note`.

## Test data

- no-match: `glob="{a,b}/f.py"` in a dir with `a.py` → note present, `total_files == 0`
- content mode: `glob="**/*.{md,json}"`, `pattern="x"` → `mode == "content_search"`, note
  present
- escaped: `glob="\\{a,b}/f.py"` → note present
- legitimate braces: create a directory literally named `{a,b}` containing `f.py`, search
  `glob="{a,b}/f.py"` → `total_files == 1`, no note (braces and commas are valid filename
  characters on both NTFS and POSIX)
- glob hit, pattern missed: same `{a,b}/f.py` file, `pattern="zzz_no_match_zzz"` → no note
- control: `glob="**/*.nonexistent_xyz"` → no note

## Checks

`run_format_code`, then pylint / pytest (`-n auto`) / mypy / ruff.

## Commit

`feat(search): flag brace patterns that match no files`

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`.
>
> First add `TestSearchFilesGlobNote` to `tests/file_tools/test_search.py` and confirm it
> fails. Then add `_BRACE_NOTE` and the `glob_note` computation to
> `src/mcp_workspace/file_tools/search.py`, attaching the key to both the file-search and
> content-search return paths. Do not change `_search_content`'s signature, the existing
> `note` key, or its tests.
>
> Then run `run_format_code`, `run_pylint_check`, `run_pytest_check` with
> `extra_args: ["-n", "auto"]`, `run_mypy_check`, and `run_ruff_check`. Steps 1 and 2 must
> still pass. Commit as `feat(search): flag brace patterns that match no files`.
