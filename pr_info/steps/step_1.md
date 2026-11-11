# Step 1 — Rules builder, `info/exclude`, `is_path_gitignored`, new message

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_1.md`), and issue #392
> for background. Implement **only** this step, test first: write the tests below, see them
> fail, then implement. Run pylint, pytest (`-n auto`) and mypy; all must pass. Format, then
> make exactly one commit.

## Precondition

Probe the installed igittigitt version with a scratch test
(`.scratch/test_probe.py`: `assert Version(importlib.metadata.version("igittigitt")) >= Version("2.4.0")`
or a plain tuple comparison), run it with
`run_pytest_check(extra_args=["-p", "no:cacheprovider", ".scratch/test_probe.py"])`,
then delete `.scratch/`. If the installed version is below 2.4.0, write one line to
`pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/file_tools/directory_utils.py`
- `pyproject.toml`
- `tests/file_tools/test_gitignore_rules.py` (new)
- `tests/test_server.py` (one assertion)

## WHAT

```python
def _info_exclude_path(project_dir: Path) -> Path | None: ...
def _load_rule_file(parser: IgnoreParser, rule_file: Path, base_dir: Path) -> None: ...
def _rules_for(directory: Path, project_dir: Path) -> IgnoreParser: ...
def _matches_rules(path: str, project_dir: Path) -> bool: ...
def is_path_gitignored(path: str, project_dir: Path) -> bool:          # signature unchanged
def check_path_not_gitignored(file_path: str, project_dir: Path) -> None:  # message changed
```

`read_gitignore_rules`, `apply_gitignore_filter`, `filter_with_gitignore` stay untouched in
this step (`list_files` still uses them); step 2 deletes them.

## HOW

- `pyproject.toml`: `"igittigitt>=2.1.5"` → `"igittigitt>=2.4.0"`.
- `is_path_gitignored` no longer calls `read_gitignore_rules`.
- Use only `IgnoreParser()`, `parse_rule_file(rule_file, base_dir=...)`, `match()` and the
  `rules` attribute. Never `parse_rule_files` (plural): it walks the tree and adds global
  excludes.
- New message in `check_path_not_gitignored`:
  `f"Path '{file_path}' is excluded by .gitignore rules and cannot be accessed. Use list_directory() to see available files."`
- Update docstrings of `is_path_gitignored` / `check_path_not_gitignored` (no longer "root
  .gitignore"). Keep the module's comment density.

## ALGORITHM

`_info_exclude_path(project_dir)`:
```
git = project_dir / ".git"
if git.is_file(): read it (OSError → warning, return None); take the "gitdir:" line
    (none → return None); git = project_dir / value.strip()   # absolute value stays absolute
commondir = git / "commondir"
if commondir.is_file(): git = git / commondir.read_text().strip()   # OSError → warning, return None
return git / "info" / "exclude"
```
(A plain `.git` directory has no `commondir`, so it falls through; a missing `.git` gives a
path that does not exist, which `_load_rule_file` treats as missing.)

`_load_rule_file(parser, rule_file, base_dir)`:
```
if not rule_file.is_file(): logger.debug("No rule file at %s", rule_file); return
try: parser.parse_rule_file(rule_file, base_dir=base_dir)
except Exception as e: logger.warning("Error reading rule file %s: %s", rule_file, e); return
logger.debug("Loaded %s (%s rules)", rule_file, len(parser.rules))
```

`_rules_for(directory, project_dir)` — rules in effect for entries of `directory`
(absolute, at or below `project_dir`):
```
parser = IgnoreParser()
exclude = _info_exclude_path(project_dir); if exclude: _load_rule_file(parser, exclude, project_dir)
_load_rule_file(parser, project_dir / ".gitignore", project_dir)
current = project_dir
for part in directory.relative_to(project_dir).parts:
    current /= part
    if parser.match(current): break          # ignored level: read nothing below it
    _load_rule_file(parser, current / ".gitignore", current)
return parser
```

`_matches_rules(path, project_dir)` — one spelling:
```
base = Path(os.path.normpath(project_dir)); full = Path(os.path.normpath(base / path))
if full == base or not full.is_relative_to(base): return False   # root, or leaves project_dir
return _rules_for(full.parent, base).match(full)
```

`is_path_gitignored(path, project_dir)`:
```
keep the two existing .git checks (is_path_in_git_dir, resolves_into_git_dir) → True
candidates = {path, canonical_spelling(path), _resolved_relative(joined, project_dir)}
return any(_matches_rules(c, project_dir) for c in candidates if c is not None)
```

## DATA

- `_rules_for` returns an `igittigitt.IgnoreParser`; `parser.rules` is the ordered rule list.
- `_info_exclude_path` returns the absolute path of the `info/exclude` to read, or `None`.
- `is_path_gitignored(".", ...)` is `False` (the root is never ignored).

## Tests (`tests/file_tools/test_gitignore_rules.py`, write first)

Use `tmp_path` as `project_dir`; create `.git/` as a plain directory where needed (no git binary).

1. Nested rules: `sub/.gitignore` = `*.tmp` → `sub/x.tmp`, `sub/deep/x.tmp` ignored; `x.tmp` not.
2. Deeper wins: root `*.log`, `sub/.gitignore` `!keep.log` → `sub/keep.log` not ignored,
   `sub/x.log` and `keep.log` ignored.
3. No re-include inside excluded dir: root `secret/` + `!secret/keep.txt` → `secret/keep.txt` ignored.
4. A `.gitignore` inside an ignored directory is not read: root `build/`, `build/.gitignore`
   `!*` → `build/a` ignored, and `patch.object(IgnoreParser, "parse_rule_file", autospec=True,
   side_effect=<original>)` shows `build/.gitignore` was never parsed.
5. `info/exclude`: `.git/info/exclude` `*.bak` → `a.bak` ignored; with root `!keep.bak` →
   `keep.bak` not ignored, `x.bak` ignored.
6. `.git` file, worktree layout: `.git` = `gitdir: <abs>/common/worktrees/wt`, that dir has
   `commondir` = `../..`, `<abs>/common/info/exclude` = `*.bak` → `a.bak` ignored.
7. `.git` file, submodule layout with a **relative** `gitdir:` and no `commondir` →
   `<gitdir>/info/exclude` is applied.
8. `.git` file without a `gitdir:` line → no exception, `a.bak` not ignored.
9. Outside `project_dir`: `tmp_path/.gitignore` = `*.log`, project = `tmp_path/proj`;
   `is_path_gitignored("../x.log", proj)` is False and the `parse_rule_file` spy saw no file
   outside `proj`.
10. A rule file that can't be read: patch `IgnoreParser.parse_rule_file` to raise `OSError`
    → result False, one WARNING record.
11. Port of #48 (`test_read_gitignore_rules_logs_nothing_above_debug`): with
    `caplog.at_level(logging.INFO, logger="mcp_workspace.file_tools.directory_utils")`, call
    `_rules_for` and `is_path_gitignored` with and without rule files → no records from that
    logger. (Step 2 adds `list_files` to this test.)
12. `is_path_gitignored(".", project)` is False with root `.gitignore` = `*`.

Also change `tests/test_server.py::test_check_not_gitignored_absolute_path_message_is_forward_slash`
to assert `"Path 'sub/deeper/debug.log' is excluded by .gitignore rules"`.

Must still pass unchanged: `tests/test_file_tool_path_rules.py` (`TestLinksIntoProtectedPaths`,
`TestGitignoreSpelling`, `test_case_variants_refused_on_windows`) and `TestIsPathGitignored`.

## Commit

`fix(file_tools): apply nested .gitignore files and info/exclude to path checks (#392)`
