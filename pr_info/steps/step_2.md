# Step 2 — Sync the 2 stale README feature summaries

**Commit:** 1 (README docs sync + verification passing)

> Prerequisite reading: `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`
> (the new summary strings must match Step 1 exactly).

## WHERE

- `README.md` (feature list, lines 25–26)

## WHAT

Update the two feature-list bullets whose summaries now drift from the docstrings changed in
Step 1. These are the only two README lines affected; the other five tools are not
individually summarized in the README.

| Line | Old | New |
|---|---|---|
| 25 | `- `read_file`: Read the contents of a file` | `- `read_file`: Read a file, or a line slice via start_line/end_line.` |
| 26 | `- `save_file`: Write content to a file atomically` | `- `save_file`: Write a file, creating parent directories as needed.` |

Preserve the existing bullet/backtick formatting; change only the summary text after the
tool name.

## HOW

- Plain Markdown text edit. No code, no schema, no tests involved.
- Keep the wording identical to the Step 1 docstring first lines so public docs and generated
  schemas stay consistent (that consistency is the point of the README-sync requirement).

## ALGORITHM

None — two exact-string Markdown replacements.

## DATA

None.

## TDD note

Not applicable — documentation change.

## Verification (must pass before committing)

1. Confirm the two new README summaries are byte-identical to the Step 1 first lines for
   `read_file` and `save_file`.
2. Run the standard quality gate (pylint/pytest/mypy) — expected unaffected, run for safety.
3. `./tools/format_all.sh`, review diff is docs-only, then commit.

## Suggested commit message

```
Sync README feature summaries for read_file and save_file

Refresh the two stale README bullets to match the updated tool docstrings,
keeping public docs consistent with the discoverability goal of #235.
```
