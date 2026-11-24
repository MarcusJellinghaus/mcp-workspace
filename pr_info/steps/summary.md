# Summary — #400 file_tools: use mcp-coder-utils `fs`; LF default for new files

## Goal

A refactoring plus **one** intended behaviour change.

- **Refactoring:** the duplicated mechanisms in `file_tools/` and
  `toolset/_github_write_helpers` are replaced by `mcp_coder_utils.fs`
  (mcp-coder-utils#69, merged as #88 on `main`). Existing functions become thin
  callers.
- **Behaviour change:** the default newline (new file, file without line breaks,
  tie in a mixed file) is `.gitattributes` `eol=`, else **LF** — was the platform
  default (CRLF on Windows).

Everything else keeps today's behaviour: error types, messages (except the
containment reason text), return values. No new handling.

## Architectural / design changes

Reuse rule (mcp-coder-utils `docs/architecture/architecture.md` rule 3):
**mechanism in mcp-coder-utils, policy in the consumer.**

| Concern | Mechanism → `mcp_coder_utils.fs` | Policy → stays in mcp-workspace |
|---|---|---|
| Normalise to LF | `normalize_line_endings` | — |
| Count endings | `count_line_endings` | `describe_line_endings` (wording for `github_issue_view`) |
| Dominant ending | `dominant_newline` (returns `None` on tie / no breaks) | default = `.gitattributes` `eol=`, else LF (`_eol_from_gitattributes`) |
| Write text with a newline | `write_text(path, text, newline=, append=)` | `append_file` exists/is_file checks and `ValueError` wrap; atomic temp-file `save_file` |
| Path containment | `check_path_within(path, root)` | `project_dir is None` check, error wording, lexical fallback on `OSError`, `relative_to` check, `.git` refusal, `(joined_abs, rel_posix)` return |

Aligned line-ending policy (shared with mcp_coder#1419):

1. Existing file with line breaks → its dominant ending.
2. Tie, no line breaks, or new file → `.gitattributes` `eol=` (`lf` / `crlf`), else **LF**.

Design rules:

- **No shim module.** Import from `mcp_coder_utils.fs` directly, like
  `mcp_coder_utils.log_utils`. Never import `fs.normalize_path` or `fs.read_file`
  by name — they clash with local functions of different meaning.
- `PLATFORM_NEWLINE` is removed. Fallback tests assert LF with no platform
  patch, so they run the same on every OS.
- `ref_relative_path` stays lexical and local (must not resolve against the
  checkout; reference reads are at `origin/<default>`).
- tach: new module entry `mcp_coder_utils.fs` (layer `utilities`), a dependency
  of `mcp_workspace.file_tools` and `mcp_workspace.toolset`. Tests do not import
  `fs` (duplicate tests are deleted), so the `tests` module is unchanged. One more
  tach ModuleNotFound warning is expected, not a failure.

## Files modified (no files created except these plan files)

| File | Step | Change |
|---|---|---|
| `tach.toml` | 1 | `mcp_coder_utils.fs` module; added to `file_tools` and `toolset` `depends_on` |
| `src/mcp_workspace/file_tools/path_utils.py` | 1, 4 | delete `normalize_line_endings` (1); `normalize_path` via `check_path_within`, docstrings (4) |
| `src/mcp_workspace/file_tools/line_endings.py` | 1, 3 | `count_line_endings` from `fs` (1); `dominant_newline`, LF default, `PLATFORM_NEWLINE` gone (3) |
| `src/mcp_workspace/file_tools/edit_file.py` | 1, 2, 3 | `normalize_line_endings` from `fs` (1); `write_text`, `_write_file` deleted (2); docstring (3) |
| `src/mcp_workspace/file_tools/file_operations.py` | 1, 2, 3 | `normalize_line_endings` from `fs` (1); `append_file` via `write_text` (2); docstring (3) |
| `src/mcp_workspace/toolset/_github_write_helpers.py` | 1 | `_normalize_newlines` delegates to `fs` |
| `src/mcp_workspace/toolset/write.py` | 3 | tool descriptions of save_file / append_file / edit_file |
| `tests/file_tools/test_path_utils.py` | 1 | delete 3 duplicate `normalize_line_endings` tests |
| `tests/file_tools/test_edit_file_issues.py` | 1 | delete duplicate `test_normalize_line_endings` |
| `tests/file_tools/test_line_endings.py` | 1, 3 | delete `test_count_line_endings` (1); LF reworks (3) |
| `tests/file_tools/test_line_endings_file_tools.py` | 2, 3 | lone-surrogate tests (2); LF reworks (3) |
| `tests/file_tools/test_file_operations.py` | 3 | `test_save_file_normalizes_crlf` asserts LF, no patch |
| `tests/file_tools/test_ref_relative_path.py` | 4 | rename `test_error_texts_match_normalize_path` |
| `docs/ARCHITECTURE.md` | 1, 4 | Shared Libs row adds `fs` (1); §6 native-path wrapper (4) |
| `docs/release-notes.md` | 3, 4 | new #400 section: LF line (3), dependency line (4) |
| `docs/file-access.md` | 4 | symlink-loop limitation for 3.11/3.12 and 3.13+ |

## Steps (one commit each)

1. **Shared normalisation and counting from `fs`** — pure refactoring, tach entry.
2. **`edit_file` / `append_file` write via `fs.write_text`** — encode-error tests.
3. **LF default via `fs.dominant_newline`** — the behaviour change; `PLATFORM_NEWLINE` removed.
4. **Containment via `fs.check_path_within`** — `normalize_path` wrapper, docs.

## Behaviour changes (for the PR description)

Intended:
- New file / file without line breaks, no `eol=`: platform default → **LF**.
- Mixed file with a tie: platform default → `eol=`, else LF. The git lookup now
  runs on a tie (never when the file has a dominant ending).

Side effects (accepted, no new handling):
- Containment error reason now comes from the shared message (e.g.
  `contains a '..' segment`); `Security error`, `outside the project directory`
  and `traversal` are kept.
- `edit_file` with unencodable content no longer empties the file (`write_text`
  encodes before opening); still a bare `UnicodeEncodeError`.
- The outside-path message names the root twice; `fs` prints the resolved root,
  the wrapper prints `project_dir` as given. Cosmetic.
- Python 3.13+: a symlink loop resolving outside the project now passes
  containment via the lexical fallback and is treated as missing (was
  "Security error"). Nothing outside the project is opened or written.
  Analytical. 3.11/3.12 still raise `RuntimeError` from `resolves_into_git_dir`.
- Two extra `stat()` calls per `normalize_path` (incl. per file in `search_files`).
