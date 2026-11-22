# Step 1 — Newline-only line split in the compact diff pipeline

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **this step only**
> (`pr_info/steps/step_1.md`) for issue #406. Follow TDD: write the tests
> below first, run them and check that the "must fail" tests fail on the
> current code. Then apply the fix in `compact_diffs.py`. Run format, pylint,
> pytest (`extra_args: ["-n", "auto"]`) and mypy until all pass. Make exactly
> one commit. Do not touch `render_hunk` (that is step 2).

## Precondition

If a test marked "must fail" below passes on the unfixed code, write one line
to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/git_operations/compact_diffs.py` (modify)
- `tests/git_operations/test_compact_diffs_line_split.py` (create)
- `tests/git_operations/test_output_filtering.py` (modify, `TestFilterDiffOutput`)
- `tests/git_operations/test_read_operations.py` (modify, `TestGitDiff`)

## WHAT

In `compact_diffs.py`, next to `_ANSI_ESCAPE_RE`, or in a small section
before Layer 1 so that `parse_diff` can use it:

```python
# Split on newlines only: str.splitlines() also breaks on \x0b, \x0c, \x1c-\x1e,
# \x85, U+2028, U+2029 and a lone \r, which are diff line content.
_LINE_SPLIT_RE = re.compile(r"\r?\n")


def _split_diff_lines(text: str) -> list[str]:
    """Split diff text into lines on \\n / \\r\\n only, like splitlines() otherwise."""
```

- `parse_diff`: `for line in text.splitlines():` → `for line in _split_diff_lines(text):`
- `extract_moved_blocks_ansi`: `for line in ansi_diff.splitlines():` → `for line in _split_diff_lines(ansi_diff):`

## ALGORITHM

```
lines = _LINE_SPLIT_RE.split(text)
if lines and lines[-1] == "":
    lines.pop()          # drop exactly one trailing empty element
return lines
```

## DATA

`list[str]`, with no line terminators and the `\r` of CRLF removed. A lone `\r`
and the other Unicode separators stay inside their line.
`"a\n"` → `["a"]`, `"a\n\n"` → `["a", ""]`, `""` → `[]`.

## HOW — tests

### `tests/git_operations/test_compact_diffs_line_split.py` (new)

Module docstring in the style of `test_compact_diffs_header_only.py`. Imports:
`pytest`, and `parse_diff`, `render_compact_diff` from
`mcp_workspace.git_operations.compact_diffs`.

```python
_SEPARATORS = ["\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", " ", " "]


def _diff(*hunk_lines: str) -> str:
    """One-file, one-hunk diff with hunk_lines joined by \\n (no trailing newline)."""
    return (
        "diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n@@ -1,3 +1,3 @@\n"
        + "\n".join(hunk_lines)
    )
```

Class `TestSplitDiffLines`:

1. `test_separator_terminated_line_followed_by_line` — **must fail**.
   Parameterize `sep` over `_SEPARATORS` and `prefix` over `["+", "-", " "]`.
   `result = render_compact_diff(_diff(prefix + sep, " tail"), "")` and
   assert `result.split("\n")[-2:] == [prefix + sep, " tail"]`.
2. `test_other_separator_terminated_lines` — **must fail**. Parameterize over
   `"+foo\x0c"` and `"+foo\r\r"` (the second gives CR CR LF once joined).
   The call is the same as in test 1, and it asserts `result.split("\n")[-1] == " tail"`.
3. `test_mid_line_separator_not_split` — **must fail**. Parameterize over
   `"+x = 1\x0c-fake"` and `"+x\r-fake"`.
   `lines = render_compact_diff(_diff(line, " tail"), "").split("\n")`.
   Assert `line in lines` (content preserved byte-for-byte, `\x0c`/`\r`
   survives) and `"-fake" not in lines`.
4. `test_trailing_newline_adds_no_empty_line` (pins current behaviour):
   `parse_diff(_diff("+a", " b") + "\n")[0].hunks[0].lines == ["+a", " b"]`.
5. `test_crlf_carriage_return_stripped` (pins current behaviour):
   `lines = render_compact_diff(_diff("+a\r", " b\r", ""), "").split("\n")`.
   Assert `"+a" in lines`, `" b" in lines`, and no line ends with `"\r"`.

### `tests/git_operations/test_output_filtering.py` — `TestFilterDiffOutput`

6. `test_mid_line_separator_not_split` — **must fail**:
   ```python
   diff = (
       "diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n"
       "@@ -1 +1 @@\n-x = 0\n+x = 1\x0c-fake"
   )
   lines = filter_diff_output(diff, "fake").split("\n")
   assert "+x = 1\x0c-fake" in lines
   assert "-fake" not in lines
   ```

### `tests/git_operations/test_read_operations.py` — `TestGitDiff`

Add `from .conftest import commit_files` to the imports.

7. `test_diff_compact_form_feed_context_line` — **must fail**:
   ```python
   repo, project_dir = git_repo_with_commit
   repo.git.config("core.autocrlf", "false")
   commit_files(repo, {"ff.py": b"a = 1\n\x0c\nb = 2\n"}, "add form feed file")
   (project_dir / "ff.py").write_bytes(b"a = 2\n\x0c\nb = 2\n")
   result = git_diff(project_dir)
   assert "+a = 2" in result
   assert "\x0c" in result
   ```
   The `\x0c` context line is followed by ` b = 2`, so it is not the last
   diff line. Without the fix, `git_diff` raises `IndexError`.

## Commit message

`fix(compact_diffs): split diff lines on newlines only (#406)`
