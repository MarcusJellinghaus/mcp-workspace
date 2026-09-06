# Step 3 — README: correct List Directory's `.gitignore` claim, add a `check_file_size` entry

Read [summary.md](summary.md) first.

Documentation-only. Single commit. Independent of steps 1, 2 and 4.

Two edits, both in `README.md`. They are kept in one step because they are one theme — making the
README's statements about `.gitignore` scope accurate — and because 3b is the reason 3a matters: a
reader of `check_file_size` never reaches line 243 today, so the corrected bullet alone would not
reach them.

## WHERE

`README.md` only. Three locations:

| Location | Edit |
|---|---|
| Line 243, under `#### List Directory` | Correct and split (3a) |
| End of the tool table (currently ends with the `git` row at line 237) | New row (3b) |
| End of the Tool Details section — after `#### Cross-Repo GitHub Access`, before `## Security Features` at line 475 | New block (3b) |

## WHAT

### 3a — correct `README.md:243`

The bullet currently reads:

> - By default, results are filtered based on .gitignore patterns and .git folders are excluded

Only the `.gitignore` clause is wrong. `list_files` passes the **listed** directory as `base_dir`
(`directory_utils.py:216` → `:166`), so `list_directory(path="src")` reads `src/.gitignore` and not
the project-root one.

Replace the `.gitignore` clause with:

> The `.gitignore` in the listed directory is applied; no other `.gitignore` file is read —
> including the project-root one when listing a subdirectory — nor `.git/info/exclude`.

The `.git`-folders statement is **true and stays**, retained as its own bullet. So one bullet
becomes two:

```markdown
#### List Directory
- Returns a list of file and directory names
- The `.gitignore` in the listed directory is applied; no other `.gitignore` file is read — including the project-root one when listing a subdirectory — nor `.git/info/exclude`
- `.git` folders are excluded
```

This is documented, **not fixed**. Changing it would alter what `search_files`, `list_directory`
and `delete_directory` see. No follow-up issue.

### 3b — add a `check_file_size` README entry

The tool has no row in the tool table (lines 213-237) and no Tool Details block. Its only README
mention today is `--file-size-limit` at line 67.

**Table row** — the **last** row of the table, after the `git` row. Columns are
`| Operation | Description | Example Prompt |`; rows are ordered functionally, not alphabetically,
so appending is correct. Example Prompt in the style of the neighbours:

```markdown
| `check_file_size` | Reports files whose line count exceeds a threshold | "Which files in this project are too long?" |
```

**Tool Details block** — at the end of the Tool Details section (which runs 239-473 and ends with
`#### Cross-Repo GitHub Access`), before `## Security Features`.

Follow the `#### Delete Directory` template (lines 271-285) — the bold-heading style with
`**Parameters:**` / `**Features:**`. It is the closest fit because it already documents an internal
cap ("capped at 20 entries with a summary line"). Follow it for **style, not length**: keep the
block tight, no examples block.

Content it must state:

- The single parameter `max_lines: Optional[int] = None` (`server.py:1531`) and its resolution
  chain `max_lines` → `--file-size-limit` → 600 (`server.py:1547-1549`).
- The scan scope, matching step 2's docstring wording: every UTF-8 file under the project
  directory, all file types, tracked or not, excluding `.git/` and project-root `.gitignore`
  matches; nested `.gitignore` files are not read.
- The `.large-files-allowlist` file (`server.py:1550`) — currently undocumented anywhere in the
  README. Note that entries are **exact paths**, not globs (`file_sizes.py:119`), and that stale
  entries are reported.
- The two 50-item report caps, stated as internal with no lift parameter.

Draft:

```markdown
#### Check File Size
Reports files whose line count exceeds a threshold.

**Parameters:**
- `max_lines` (integer, optional): Line threshold. Falls back to the server's `--file-size-limit` flag, then to `600`

**Features:**
- Counts lines in every UTF-8 file under the project directory — all file types, tracked or not — excluding `.git/` and anything the project-root `.gitignore` matches. Nested `.gitignore` files are not read
- Files listed in `.large-files-allowlist` (one path per line, `#` comments allowed) are exempt; entries are matched as exact paths, not globs
- Allowlist entries that no longer exceed the threshold are reported as stale
- The violations list and the stale-entries list are each capped at 50 with a `showing X of Y` notice; the caps are internal and there is no parameter to lift them
```

## ALGORITHM

None — no executable change.

## DATA

None — no change to return values or data structures.

## TESTS

None. No test in this repo asserts on README content.

## CHECKS

No Python changed, so the Python checks are not strictly required. Run pytest (`-n auto`) once
anyway to confirm the tree is green before committing.

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`.
>
> Implement step 3 only, all in `README.md`:
> 1. Split the `#### List Directory` bullet at line 243 into two bullets — the corrected
>    `.gitignore` sentence given in step_3.md, and the `.git`-folders statement kept as its own
>    bullet.
> 2. Append a `check_file_size` row as the last row of the tool table, after the `git` row.
> 3. Append a `#### Check File Size` block at the end of the Tool Details section — after
>    `#### Cross-Repo GitHub Access`, before `## Security Features` — following the
>    `#### Delete Directory` bold-heading style.
>
> Use the wording drafted in step_3.md. Keep the block tight; no examples section.
>
> Constraints: do not change any other README section, do not touch `--file-size-limit` at line 67,
> and do not change any Python file.
>
> Then run pytest (`-n auto`) to confirm the tree is green, and commit as
> `docs(readme): document check_file_size and fix gitignore scope`.
