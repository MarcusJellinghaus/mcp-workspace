# Summary — #406 compact diff: `splitlines()` mis-splits diff lines

## Problem

`parse_diff` and `extract_moved_blocks_ansi` in
`src/mcp_workspace/git_operations/compact_diffs.py` split diffs with
`str.splitlines()`, which also breaks on lone `\r`, `\x0b`, `\x0c`,
`\x1c`–`\x1e`, `\x85`, ` `, ` `.

- A diff line ending in one of these (and followed by another line) yields an
  empty string inside a hunk → `render_hunk` reads `line[0]` → `IndexError`.
  `git_diff` / `git_show` (compact by default) and `get_compact_diff` crash.
- A separator mid-line splits one diff line into two → fabricated diff lines
  (e.g. `+x = 1\x0c-fake` renders a fake `-fake` removal). `filter_diff_output`
  inherits this via `parse_diff`.
- With `diff.suppressBlankEmpty=true`, git itself emits blank context lines as
  `""` → same `IndexError` in `render_hunk`, independent of the split.

## Architectural / design changes

Two small, independent fixes inside one module; no new modules, no public API
changes, no changes to callers.

1. **Newline-only line splitting** (root-cause fix for separators).
   A private regex + helper in `compact_diffs.py`:
   - `_LINE_SPLIT_RE = re.compile(r"\r?\n")`
   - `_split_diff_lines(text: str) -> list[str]` — split on `\r?\n`, drop
     exactly one trailing empty element (same trailing behaviour as
     `splitlines()`).
   - Used by **both** passes (`parse_diff` = plain pass, and
     `extract_moved_blocks_ansi` = ANSI Pass 1) so moved-line contents stay
     comparable between them.
   - CRLF unchanged: the `\r` of `\r\n` is consumed by the split, as before.
     A lone `\r` is diff content and stays inside its line.
   - Deliberately local: `_LINE_BREAK` in `github_operations/issues/base.py`
     also splits on lone `\r`, so it is not reused.
2. **Empty-line guard in `render_hunk`** (defence for `suppressBlankEmpty`
   output and hand-built `Hunk` input — `Hunk`/`render_hunk` are public).
   The context-line condition becomes `not line or line[0] not in ("+", "-")`;
   an empty line is emitted as-is (not dropped), keeping line counts intact.

Explicitly **not** done (per issue): no renderer fallback/try-except in
`git_diff`/`git_show`; no changes to other `splitlines()` call sites
(`read_operations.py` header counts, `truncate_output`,
`filter_content_output`); no shared helper in another package.

## Files

| File | Change |
|---|---|
| `src/mcp_workspace/git_operations/compact_diffs.py` | modify — add `_LINE_SPLIT_RE`, `_split_diff_lines`; use it in `parse_diff` and `extract_moved_blocks_ansi` (step 1); `render_hunk` guard (step 2) |
| `tests/git_operations/test_compact_diffs_line_split.py` | **create** — unit tests for the split (step 1) and the `render_hunk` guard (step 2) |
| `tests/git_operations/test_output_filtering.py` | modify — one test in `TestFilterDiffOutput` (step 1) |
| `tests/git_operations/test_read_operations.py` | modify — two tests in `TestGitDiff`: form feed (step 1), `suppressBlankEmpty` (step 2). Already in `.large-files-allowlist` |

No new folders.

## Steps

- [Step 1](./step_1.md) — newline-only split helper used by both passes, with
  unit, `filter_diff_output` and form-feed integration tests.
- [Step 2](./step_2.md) — `render_hunk` empty-line guard, with hand-built
  `Hunk` and `suppressBlankEmpty` integration tests.

The two fixes are independent, so each has its own commit. Each step adds
its tests first, confirms they fail, then applies the fix.

## Test conventions (both steps)

- Split rendered output with `.split("\n")`, **never** `.splitlines()`. It
  re-splits on the separators under test.
- Integration test files are written as bytes (`write_bytes` /
  `commit_files` from `tests/git_operations/conftest.py`). `write_text`
  turns `\n` into `\r\n` on Windows. Set `core.autocrlf=false` in the test
  repo.
- In integration tests the trigger line must be **followed by** another diff
  line. As the last diff line it is hidden by GitPython's final-newline strip
  and the test would pass without the fix.
