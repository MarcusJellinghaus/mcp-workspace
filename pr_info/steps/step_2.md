# Step 2 — Raise on globs that match nothing by construction

Read [summary.md](./summary.md) first.

TDD: write the failing tests, then extract `_match_glob` and add the validation.

## WHERE

- `tests/file_tools/test_search.py` — new class `TestSearchFilesGlobValidation`
- `src/mcp_workspace/file_tools/search.py` — new module-level helper `_match_glob`, placed
  above `_search_content`; `search_files` body edited to call it
- `pyproject.toml` — raise the `pathspec` floor to `>=1.1.1` (see below)

## WHAT — tests first

```python
class TestSearchFilesGlobValidation:
    @pytest.mark.parametrize(
        "glob", ["", "   ", "#*.py", "!*.py", "[", "[a-", "a[b"]
    )
    def test_glob_matching_nothing_by_construction_raises(
        self, project_dir: Path, glob: str
    ) -> None

    def test_raise_happens_in_combined_mode_too(self, project_dir: Path) -> None

    @pytest.mark.parametrize("glob", ["!", "a\\"])
    def test_malformed_glob_still_raises_value_error(
        self, project_dir: Path, glob: str
    ) -> None
```

- First test: `pytest.raises(ValueError, match="matches nothing by construction")`.
- Second: same assertion with `glob=""` **and** `pattern="x"` — the raise must precede the
  content search.
- Third: `pytest.raises(ValueError)` with **no** `match=`. These two already raise
  `GitIgnorePatternError` out of `PathSpec.from_lines` today; the test pins the exception
  *type* only, so it keeps passing whether pathspec raises or the new check does.

Unterminated bracket expressions (`[`, `[a-`, `a[b`) **are** in this parametrization, as in
issue #249's decision table. A probe on the installed pathspec (1.1.1) shows they compile to
a single pattern with `regex is None` and `include is None` — exactly the condition below,
so they need no separate mechanism. A closed class such as `[a-]` compiles normally and is
unaffected.

## WHAT — implementation

```python
def _match_glob(glob: str, files: List[str]) -> List[str]:
```

Raises `ValueError` if the pattern cannot match anything; otherwise returns the subset of
`files` that matches.

## HOW

Add `RegexPattern` to the existing pathspec import:

```python
from pathspec import PathSpec, RegexPattern
```

`PathSpec.patterns` is typed as a collection of the base `Pattern`, which declares
`include` but not `regex`; the `isinstance` narrowing below keeps mypy strict happy. If
mypy still objects, narrow with a local variable — do not add a `type: ignore`.

`search_files` loses its inline glob block and gains:

```python
matched = _match_glob(glob, all_files) if glob is not None else all_files
```

Everything downstream (content mode, file mode, truncation) is untouched.

## ALGORITHM

```
win32 = sys.platform == "win32"
spec = PathSpec.from_lines("gitwildmatch", [glob.lower() if win32 else glob])
if not any(isinstance(p, RegexPattern) and p.regex is not None and p.include
           for p in spec.patterns):
    raise ValueError(f"Glob pattern {glob!r} matches nothing by construction "
                     "(gitignore comment, blank, negation-only, or unparseable pattern)")
return [f for f in files if spec.match_file(_norm(f))]   # _norm: '\'->'/' , lower on win32
```

One condition covers every input above, so the empty-pattern-list versus null-regex
distinction never reaches the caller. The message is keyed on the **effect**, not the
cause — the same signal fires for inputs that are neither a comment nor blank.

## pathspec floor

`pyproject.toml` currently declares `pathspec>=0.12.1`. Which malformed patterns compile to
a null regex is version-dependent, and only 1.1.1 has been probed, so raise the floor to
`pathspec>=1.1.1` in the same commit — that is the version whose classification these tests
assert.

## DATA

- Returns: `List[str]` of project-relative paths (unchanged from the inline code it
  replaces).
- Raises: `ValueError` — document it in the `_match_glob` docstring `Raises:` block, and add
  it to the existing `Raises:` block of `search_files` (`search.py:118-119`). Wrapper
  docstrings are step 4.

## Checks

`run_format_code`, then pylint / pytest (`-n auto`) / mypy, plus `run_ruff_check` — the new
helper needs a Google-style docstring with `Args:`, `Returns:`, and `Raises:`.

If one of the parametrized inputs does not raise, the installed pathspec gave it a usable
regex, and no attribute separates it from a legitimate literal search. Do not widen the
condition to chase it and do not add a second raise site: check the installed pathspec
version against the `>=1.1.1` floor above first, and only if the floor holds, drop that
input from the parametrization. Do not assert pathspec internals in the test.

## Commit

`fix(search): raise on globs that match nothing by construction`

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`.
>
> First add `TestSearchFilesGlobValidation` to `tests/file_tools/test_search.py` and confirm
> it fails. Then extract `_match_glob(glob, files) -> List[str]` in
> `src/mcp_workspace/file_tools/search.py` — win32 lowercasing, `PathSpec` build, the single
> validation condition with its one `ValueError`, and the matching — and call it from
> `search_files`. Add `ValueError` to the `search_files` `Raises:` block. Raise the
> `pathspec` floor to `>=1.1.1` in `pyproject.toml`. Leave `note`, `_search_content`, and
> both wrapper modules alone.
>
> Then run `run_format_code`, `run_pylint_check`, `run_pytest_check` with
> `extra_args: ["-n", "auto"]`, `run_mypy_check`, and `run_ruff_check`. The step 1 tests must
> still pass. Commit as
> `fix(search): raise on globs that match nothing by construction`.
