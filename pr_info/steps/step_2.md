# Step 2 — `list_files` walk with a `skip` callback; delete the old helpers

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_2.md`). Step 1 is done:
> `_rules_for`, `_load_rule_file` and the new `is_path_gitignored` exist in
> `directory_utils.py`. Implement **only** this step, test first. Run pylint, pytest
> (`-n auto`) and mypy; all must pass. Format, then make exactly one commit.

## WHERE

- `src/mcp_workspace/file_tools/directory_utils.py`
- `tests/file_tools/test_gitignore_rules.py`
- `tests/file_tools/test_directory_utils.py`

## WHAT

```python
def _discover_files(
    directory: Path, project_dir: Path, skip: Callable[[Path], bool] | None = None
) -> list[str]: ...
def _gitignore_skip(start: Path, project_dir: Path) -> Callable[[Path], bool]: ...
def list_files(directory: str | Path, project_dir: Path, use_gitignore: bool = True) -> list[str]:  # signature unchanged
```

Delete: `read_gitignore_rules`, `_link_target_ignored`, `apply_gitignore_filter`,
`filter_with_gitignore`.

## HOW

- `_discover_files` stays the only walker: `os.walk` (default `followlinks=False`), skips
  `.git` entries, returns forward-slash project-relative paths. `skip` is called with the
  absolute path of each subdirectory (a skipped one is removed from `dirs[:]` and never
  entered) and of each file (a skipped one is not returned). Compute `root_path` before
  filtering `dirs`.
- `list_files`:
  - `use_gitignore=False` → `_discover_files(abs_path, project_dir)`, unchanged behaviour.
  - Otherwise: if `is_path_gitignored(rel_path, project_dir)` → return `[]` (no exception;
    `"."` is never ignored). Else `_discover_files(abs_path, project_dir, _gitignore_skip(abs_path, project_dir))`.
  - Demote `"Discovered %s files in %s"` from INFO to DEBUG. The INFO line of
    `apply_gitignore_filter` disappears with the function.
  - Keep the existing validation, `try/except` and error log.
- `Callable` import from `collections.abc` stays (now used by `_discover_files`).

## ALGORITHM

`_gitignore_skip(start, project_dir)`:
```
parsers = {start: _rules_for(start, project_dir)}
def parser_for(d):                       # walk is top-down, so the parent is already known
    if d not in parsers:
        parsers[d] = parent = parser_for(d.parent)
        if (d / ".gitignore").is_file():
            parsers[d] = IgnoreParser(); parsers[d].rules = list(parent.rules)
            _load_rule_file(parsers[d], d / ".gitignore", d)
    return parsers[d]
def skip(path): return parser_for(path.parent).match(path) or (
    path.is_symlink() and is_path_gitignored(path.relative_to(project_dir).as_posix(), project_dir))
return skip
```
`parser_for` is only reached for directories the walk entered, so a `.gitignore` inside a
pruned directory is never read.

## DATA

- `list_files` returns `list[str]` of forward-slash project-relative file paths; `[]` for an
  ignored directory or one whose files are all ignored.
- `parsers: dict[Path, IgnoreParser]` lives only for one `list_files` call (no cache).

## Tests (write first)

In `tests/file_tools/test_gitignore_rules.py`:

1. Repro from the issue: root `.gitignore` = `secret/\n*.env\n`; files `secret/key.txt`,
   `sub/a.env`, `sub/ok.txt` → `list_files(".")` has neither ignored file,
   `list_files("secret") == []`, `list_files("sub") == ["sub/ok.txt"]`.
2. Nested rules in listing: `sub/.gitignore` `*.tmp` → `sub/x.tmp` absent, `x.tmp` present.
3. Siblings don't share rules: `a/.gitignore` `*.txt` → `a/x.txt` absent, `b/x.txt` present.
4. Deeper negation: root `*.log`, `sub/.gitignore` `!keep.log` → `sub/keep.log` listed.
5. `.gitignore` in an ignored directory not read: root `build/`, `build/.gitignore` `!*`,
   `build/a` → not listed, and the `parse_rule_file` spy never saw `build/.gitignore`.
6. `use_gitignore=False` lists every non-`.git` file, ignored ones included.
7. Extend the #48 logging test from step 1 with `list_files(".")` and `list_files("sub")`.

In `tests/file_tools/test_directory_utils.py`:

- Remove the imports and tests of the deleted helpers: `test_read_gitignore_rules_no_file`,
  `test_read_gitignore_rules_with_file`, `test_read_gitignore_rules_logs_nothing_above_debug`
  (ported in step 1), `test_apply_gitignore_filter`, `test_filter_with_gitignore_no_gitignore`.
- `test_list_files_with_gitignore`: add the root case — a root `.gitignore` with `*.env`
  and `testdata/test_file_tools/x.env` → `x.env` not in `list_files(str(TEST_DIR), ...)`.
- `test_discover_files`, `test_git_directory_exclusion`, `test_list_files_without_gitignore`,
  `test_list_files_with_exception` must pass unchanged.

Must still pass unchanged: `tests/test_file_tool_path_rules.py`, including
`test_listing_omits_file_link_to_gitignored_file` and `test_git_file_not_listed`.

## Commit

`fix(file_tools): list_files applies every .gitignore and prunes ignored dirs (#392)`
