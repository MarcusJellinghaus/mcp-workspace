# Step 2 — `render_hunk` empty-line guard

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **this step only**
> (`pr_info/steps/step_2.md`) for issue #406. Step 1 (newline-only split) is
> already committed. Follow TDD: write the tests below first, run them and
> check that both fail on the current code. Then apply the guard in
> `render_hunk`. Run format, pylint, pytest (`extra_args: ["-n", "auto"]`) and
> mypy until all pass. Make exactly one commit.

## Precondition

If `_split_diff_lines` does not exist in
`src/mcp_workspace/git_operations/compact_diffs.py`, or either new test
passes on the code before the guard, write one line to `pr_info/.blocked.txt`
and stop.

## WHERE

- `src/mcp_workspace/git_operations/compact_diffs.py` (modify, `render_hunk`)
- `tests/git_operations/test_compact_diffs_line_split.py` (modify, created in step 1)
- `tests/git_operations/test_read_operations.py` (modify, `TestGitDiff`)

## WHAT

Signature unchanged:

```python
def render_hunk(
    hunk: Hunk,
    moved_lines: set[str],
    removed_to_file: dict[str, str] | None = None,
    added_to_file: dict[str, str] | None = None,
) -> str:
```

Only the context-line condition in the loop changes:

```python
# before
if line.startswith(" ") or (line and line[0] not in ("+", "-")):
# after
if not line or line[0] not in ("+", "-"):
```

Update the comment above it, e.g.
`# Context lines (including empty ones, e.g. diff.suppressBlankEmpty) are emitted as-is`.

## ALGORITHM

```
for each line in hunk.lines:
    if line is empty or line[0] not in "+-":
        emit line unchanged            # context, "\ No newline", blank
    else:
        gather same-sign run → _render_block(...)
```

## DATA

The return value is unchanged: a rendered hunk string joined with `\n`, or `""` when only the
header is left. An empty line in `hunk.lines` becomes an empty line in the output.
It is not dropped, so line counts stay the same.

## HOW — tests

### `tests/git_operations/test_compact_diffs_line_split.py`

Add `Hunk` and `render_hunk` to the import from
`mcp_workspace.git_operations.compact_diffs`.

Class `TestRenderHunkEmptyLine`:

1. `test_empty_line_rendered_as_context` — **must fail** (`IndexError`
   before the guard):
   ```python
   hunk = Hunk(header="@@ -1,3 +1,3 @@", lines=[" a", "", " b"])
   assert render_hunk(hunk, set()) == "@@ -1,3 +1,3 @@\n a\n\n b"
   ```

### `tests/git_operations/test_read_operations.py` — `TestGitDiff`

`commit_files` was already imported in step 1.

2. `test_diff_compact_suppress_blank_empty` — **must fail**:
   ```python
   repo, project_dir = git_repo_with_commit
   with repo.config_writer() as config:
       config.set_value("core", "autocrlf", "false")
       config.set_value("diff", "suppressBlankEmpty", "true")
   commit_files(repo, {"blank.py": b"a = 1\n\nb = 2\n"}, "add blank-line file")
   (project_dir / "blank.py").write_bytes(b"a = 2\n\nb = 2\n")
   result = git_diff(project_dir)
   assert "+a = 2" in result
   assert " b = 2" in result
   ```
   The blank context line (emitted by git as `""`) is followed by ` b = 2`,
   so it is not the last diff line. Without the guard, `git_diff` raises
   `IndexError`.

## Commit message

`fix(compact_diffs): render empty hunk lines as context (#406)`
