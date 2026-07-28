# Step 2 — Sync the stale README feature summaries

**Commit:** shared with Step 1 — the docstring rewrites and this README sync form a **single
commit**. Both are trivially small and tightly coupled (the README bullet text must be
byte-identical to the Step 1 docstring first lines), so per planning_principles' "merge tiny or
intertwined steps" they are not split into separate commits.

> Prerequisite reading: `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`
> (the new summary strings must match Step 1 exactly).

## WHERE

- `README.md` (feature list, lines 25–26, 30, 34)

> **Scope deviation — flag for reconciliation.** Issue #235's approved Decisions table scopes
> the README sync to `read_file` and `save_file` only (lines 25–26) and states the other tools
> "are not individually summarized there." That claim is factually wrong: the README feature
> list (lines 24–34) summarizes every tool individually. This plan therefore edits **4** bullets
> (25, 26, 30, 34), not 2 — extending the sync to `edit_file` (30) and `read_reference_file`
> (34) so the public docs also carry the newly-surfaced capabilities (`replace_all`, line
> slice). This is a deliberate expansion beyond the approved 2-line scope; surface it for
> sign-off rather than presenting it as already authorized.

## WHAT

Update the feature-list bullets whose summaries drift from the docstrings changed in Step 1.
Four bullets are affected: `read_file` and `save_file` are stale exact copies of the old
docstrings, and `edit_file` and `read_reference_file` omit the newly-surfaced capabilities
(`replace_all`, line slice). The README **does** individually summarize the other tools too,
but `delete_directory` (README:29) and `move_file` (README:31) already surface their key
capability (recursive delete, git-aware move) and so need no change.

| Line | Old | New |
|---|---|---|
| 25 | `- `read_file`: Read the contents of a file` | `- `read_file`: Read a file, or a line slice via start_line/end_line.` |
| 26 | `- `save_file`: Write content to a file atomically` | `- `save_file`: Write a file, creating parent directories as needed.` |
| 30 | `- `edit_file`: Make selective edits using exact string matching` | `- `edit_file`: Edit a file by exact string match; replace_all for multiple matches.` |
| 34 | `- `read_reference_file`: Read files from reference projects` | `- `read_reference_file`: Read a reference-project file, or a line slice via start_line/end_line.` |

Preserve the existing bullet/backtick formatting; change only the summary text after the
tool name.

## HOW

- Plain Markdown text edit. No code, no schema, no tests involved.
- Keep the wording identical to the Step 1 docstring first lines so public docs and generated
  schemas stay consistent (that consistency is the point of the README-sync requirement).

## ALGORITHM

None — four exact-string Markdown replacements.

## DATA

None.

## TDD note

Not applicable — documentation change.

## Verification (must pass before committing)

1. Confirm the four new README summaries are byte-identical to the Step 1 first lines for
   `read_file`, `save_file`, `edit_file`, and `read_reference_file`.
2. Run the standard quality gate (pylint/pytest/mypy) — expected unaffected, run for safety.
3. `./tools/format_all.sh`, review diff is docs-only, then commit.

## Suggested commit message

```
Sync README feature summaries with updated tool docstrings

Refresh the read_file, save_file, edit_file, and read_reference_file README
bullets to match the updated tool docstrings, keeping public docs consistent
with the discoverability goal of #235.
```
