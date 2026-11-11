# Issue #392 — gitignore checks follow git's rules (nested `.gitignore`, `info/exclude`)

## Goal

Every file tool decides "ignored?" with the same rules git uses: `.git/info/exclude` <
root `.gitignore` < deeper `.gitignore` files, last matching line wins, a negation cannot
re-include a path inside an excluded directory, and a `.gitignore` inside an ignored
directory is never read. Today `is_path_gitignored` reads only the root `.gitignore`, and
`list_files(<subdir>)` reads only `<subdir>/.gitignore`, so subdirectory listings leak
ignored names.

The issue text (#392) is the specification; this plan is how it is built.

## Architectural / design changes

All logic stays in `src/mcp_workspace/file_tools/directory_utils.py` (the module path is
public: mcp_coder imports from it and silences its logger by name).

| Before | After |
|---|---|
| `read_gitignore_rules(path)` parses one file into a matcher | `_rules_for(directory, project_dir) -> IgnoreParser`: `info/exclude`, then every `.gitignore` from the root down to `directory`, stopping at the first ignored level |
| `is_path_gitignored` matches 3 spellings against the root `.gitignore` | same 3 spellings, each matched with the rules of its own ancestor chain; a path that leaves `project_dir` is not ignored (and no rule file outside `project_dir` is read) |
| `list_files` walks everything, then filters with `<dir>/.gitignore` | `list_files` walks once, pruning ignored directories as it goes; each directory's rules = parent's rules + its own `.gitignore` |
| `_discover_files(directory, project_dir)` | `_discover_files(directory, project_dir, skip=None)`; `skip(path) -> bool` is called for every entry (dirs and files) |
| `apply_gitignore_filter`, `filter_with_gitignore`, `_link_target_ignored` | deleted; a symlinked entry is dropped when `is_path_gitignored` says so (it already checks the resolved spelling) |
| `.git/info/exclude` never read | `_info_exclude_path(project_dir)`: `.git` directory, or `.git` file → `gitdir:`; then `commondir` if present |
| `list_directory("<ignored dir>")` lists its files | refused with the same check as `read_file` |
| Message `File '<p>' is excluded by .gitignore and …` | `Path '<p>' is excluded by .gitignore rules and cannot be accessed. Use list_directory() to see available files.` |

Design points:

- **Engine:** igittigitt `>=2.4.0` (ordered rules, last match wins, ancestor pruning in
  `match`). GitPython only in tests, as the oracle.
- **Precedence by load order:** rules are appended in precedence order; igittigitt's
  "last matching rule wins" does the rest. Each `.gitignore` is parsed with
  `base_dir` = its own folder; `info/exclude` with `base_dir` = `project_dir`.
- **One parser per directory during the walk**, created on demand: a directory without a
  `.gitignore` reuses its parent's parser object; one with a `.gitignore` gets a new
  parser with `list(parent.rules)` plus its own rules, so siblings never share rules.
- **No cache across calls** (#73: edits to `.gitignore` apply immediately). **No global
  excludes.** Never call `IgnoreParser.parse_rule_files` (plural).
- `project_dir` is the root: nothing above it is read except what `project_dir/.git`
  points to (`info/exclude` of a worktree / submodule).
- `list_files` on an ignored directory returns `[]`; only the `list_directory` tool refuses.
- Logging in rule loading / filtering is DEBUG only (#48); a rule file that exists but
  can't be read logs a WARNING.

## Files

Modified:

- `src/mcp_workspace/file_tools/directory_utils.py` — rules builder, `info/exclude`
  lookup, `is_path_gitignored`, message, walk with `skip`, helper deletions
- `src/mcp_workspace/toolset/read.py` — `list_directory` refuses ignored directories
- `src/mcp_workspace/toolset/checks.py` — `check_file_size` description
- `pyproject.toml` — `igittigitt>=2.4.0`
- `tests/file_tools/test_directory_utils.py` — delete tests of removed helpers, extend
  `test_list_files_with_gitignore`
- `tests/test_server.py` — new message wording (`test_check_not_gitignored_absolute_path_message_is_forward_slash`)
- `tests/test_server_list_directory.py` — refusal tests
- `README.md`, `SECURITY.md`, `docs/ARCHITECTURE.md`,
  `docs/processes-prompts/refactoring-guide.md`, `docs/release-notes.md`

Created:

- `tests/file_tools/test_gitignore_rules.py` — unit tests for rule loading and the walk
- `tests/file_tools/test_gitignore_conformance.py` — conformance test against
  `git check-ignore` (`git_integration`)

## Steps

1. Rules builder, `info/exclude`, `is_path_gitignored`, new message, igittigitt bump
2. `list_files` walk with `skip` callback; delete the old helpers
3. `list_directory` refuses ignored directories
4. Conformance test against `git check-ignore`
5. Documentation and release notes

Not committed: the before/after timing of listing this repository (baseline ~1.9 s for
14,488 files; single-path check ~1.8 ms) is measured by hand and goes in the PR text.
