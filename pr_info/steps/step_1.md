# Step 1 — Pin current glob semantics (tests only)

Read [summary.md](./summary.md) first.

Tests only, no production code. These pin the behaviours that must survive this issue's
changes **and** the follow-up matcher migration (#285). The issue lists them as required
scope: none of them exist in `tests/file_tools/test_search.py` today.

## WHERE

`tests/file_tools/test_search.py` — new class `TestSearchFilesGlobSemantics`, appended
after the existing `TestSearchFilesGlobOnly`.

Existing imports (`sys`, `Path`, `pytest`, `search_files`) already cover what is needed.
The `project_dir` fixture comes from `tests/conftest.py` — an isolated `tmp_path` per test.

## WHAT

```python
class TestSearchFilesGlobSemantics:
    def test_trailing_slash_matches_files_beneath(self, project_dir: Path) -> None
    @pytest.mark.parametrize("glob", ["[!a]*.py", "[^a]*.py"])
    def test_character_class_negation(self, project_dir: Path, glob: str) -> None
    def test_double_star_matches_everything_below_prefix(self, project_dir: Path) -> None
    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only")
    def test_glob_is_case_sensitive_on_posix(self, project_dir: Path) -> None
```

## HOW

The existing win32 companion is `test_windows_case_insensitive_match_preserved`
(`skipif(sys.platform != "win32")`). Step 4 documents case-insensitivity as
platform-specific behaviour, so the POSIX branch must be asserted too — put the new test
directly beside the win32 one so the pair is obvious.

## ALGORITHM

```
create files under project_dir
result = search_files(project_dir, glob=<pattern>)
names = {Path(f).name for f in result["files"]}
assert expected in names
assert unexpected not in names
```

Use containment assertions, never `len(result["files"]) == N`: the `project_dir` fixture
copies `tests/testdata/` into the tmp dir, so unrelated files are present.

## DATA

Fixtures per test (all created inside `project_dir`):

- trailing slash: `src/a.py`, `root.py` → `glob="src/"` matches `a.py`, not `root.py`
- negation: `a.py`, `b.py` → both `[!a]*.py` and `[^a]*.py` match `b.py`, not `a.py`
- `**`: `src/a.py`, `src/deep/b.py`, `root.py` → `glob="src/**"` matches `a.py` and `b.py`,
  not `root.py`
- POSIX case: write `readme.md`, search `glob="README.md"`, assert `result["files"] == []`
  and `result["total_files"] == 0`

Return shape is the existing `file_search` dict: `mode`, `files`, `total_files`,
`truncated`.

## Checks

`run_format_code`, then pylint / pytest (`-n auto`) / mypy.

Expect all four to pass against unmodified production code — they pin today's behaviour. If
one fails, the assumption behind it is wrong: fix the test, do not change `search.py` in
this step.

## Commit

`test(search): pin gitignore glob semantics`

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`.
>
> Add the `TestSearchFilesGlobSemantics` class to `tests/file_tools/test_search.py` exactly
> as specified. Tests only — do not touch `src/`. Use containment assertions on basenames,
> not exact list lengths. Assert only `search_files` return values, never `pathspec`
> internals.
>
> Then run `run_format_code`, `run_pylint_check`, `run_pytest_check` with
> `extra_args: ["-n", "auto"]`, and `run_mypy_check`. All four tests must pass against
> unmodified production code. Commit as
> `test(search): pin gitignore glob semantics`.
