# Step 7 — `tree_listing`: name the narrowing options in the truncation summary

Reference: [summary.md](./summary.md)

## Context

`_truncate` already reports both numbers honestly — `... and 50 more entries (0 dirs, 50
files) — 300 total` — but names no way forward. `list_directory` has no `max_lines`-style
lift parameter and is not getting one (Decisions: "No new lift parameters for
`list_directory` or `check_branch_status`"). Instead the message names the parameters
that **narrow** the listing, and a code comment records that the cap is deliberate.

This truncation is rare: `_collapse` (line 122) greedily collapses directories until the
listing is under 250 lines, so `_truncate` only fires on a very wide, flat repo.

## WHERE

- `src/mcp_workspace/file_tools/tree_listing.py` — `_truncate`, lines 168-186
- `tests/file_tools/test_tree_listing.py` — `test_summary_line_format` (line 326)

## WHAT

Signature unchanged:

```python
def _truncate(lines: List[str], limit: int = _COLLAPSE_THRESHOLD) -> List[str]:
```

Only the summary string changes, plus a code comment.

## HOW

No new imports or symbols. Two edits inside the existing function:

1. Extend the `summary` f-string at lines 182-185 with the narrowing hint.
2. Add a comment above the summary recording that the 250-line cap is deliberate and
   naming the alternatives, e.g.:

```python
# The 250-line cap is deliberate: list_directory has no lift parameter and
# is not getting one. Callers narrow instead — path=<subdir>, dirs_only=True,
# or search_files for targeted lookups.
```

This file writes the em dash as the escape `—` (line 184). Keep that convention.

## ALGORITHM

```
if len(lines) <= limit: return lines        # unchanged
kept, remaining = lines[:limit], lines[limit:]
remaining_dirs  = count of remaining entries that look like directories   # unchanged
remaining_files = len(remaining) - remaining_dirs                          # unchanged
total = len(lines)
return kept + [summary(len(remaining), remaining_dirs, remaining_files, total)]
```

The counting logic at lines 179-181 is untouched.

## DATA

Return value stays `List[str]` — `limit` entries plus one summary line. The summary line
becomes exactly:

```
... and {n} more entries ({d} dirs, {f} files) — {total} total. Narrow with path=<subdir> or dirs_only=True.
```

Example:

```
... and 50 more entries (0 dirs, 50 files) — 300 total. Narrow with path=<subdir> or dirs_only=True.
```

## TDD — tests first

In `tests/file_tools/test_tree_listing.py`:

1. **`test_summary_line_format` (line 326-331)** asserts full-string equality on the
   summary. Update the expected string to the new one:
   ```python
   assert summary == (
       "... and 50 more entries (0 dirs, 50 files) — 300 total. "
       "Narrow with path=<subdir> or dirs_only=True."
   )
   ```
2. **`test_dir_file_counts_in_summary` (line 333-347)** uses substring assertions
   (`"10 dirs"`, `"40 files"`, `"300 total"`) and still passes. Leave it.
3. **`test_truncation_in_dirs_only_mode` (line 357-363)** uses substring assertions and
   still passes. Leave it.
4. **`test_truncation_triggers` (line 320-324)** and
   `test_truncation_via_list_directory_tree` (line 365-370) assert on list length and the
   `"... and"` prefix. Both still pass. Leave them.

Run pytest, confirm the one failure, then implement.

## CHECKS

All three MCP checks must pass, then `./tools/format_all.sh`.

## COMMIT

One commit: `Name the narrowing options in the tree listing truncation summary`

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_7.md`.
>
> Implement step 7 only. Following TDD, first update
> `tests/file_tools/test_tree_listing.py::test_summary_line_format` to expect the new
> summary string given in the DATA section, and confirm it fails. Then in
> `src/mcp_workspace/file_tools/tree_listing.py`, extend the `summary` f-string in
> `_truncate` with the narrowing hint and add the code comment recording that the
> 250-line cap is deliberate and naming `path=`, `dirs_only=True` and `search_files`.
> Keep the `—` escape convention this file already uses for the em dash. Do not add
> a lift parameter to `list_directory`.
>
> Verify the other four truncation tests in that file still pass unchanged.
>
> Use MCP tools per `CLAUDE.md`, run all three checks until they pass, run
> `./tools/format_all.sh`, and make exactly one commit.
