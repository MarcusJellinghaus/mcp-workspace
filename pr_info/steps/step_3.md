# Step 3: render `last_automated_note` in both report formats

Reference: `pr_info/steps/summary.md` (issue #309). This is step 3 of 3 — depends on step 2
(`BranchStatusReport.last_automated_note` already populated by the collector).

## Precondition

`format_report_for_human` and `format_report_for_llm` in
`src/mcp_workspace/checks/branch_status_rendering.py` must still each build their output via
a `lines: List[str]` list ending in a `Recommendations` section (a `lines.extend(["",
"Recommendations:"])` block in the human formatter; a `lines.append(f"Recommendations:
{recommendations_text}")` line in the LLM formatter). If either formatter's structure has
changed, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/checks/branch_status_rendering.py` — add the helper, wire it into both
  formatters.
- `tests/checks/test_branch_status.py` — extend `TestBranchStatusReport` (existing class;
  it already exercises `format_for_human`/`format_for_llm` and asserts on `"Recommendations:"`
  presence/position).

## WHAT

```python
def _format_last_automated_note_lines(report: "BranchStatusReport") -> List[str]:
    """Build the ❌-marked-comment block, or [] when nothing to render.

    Returns:
        [] when report.last_automated_note is None, else a blank line followed
        by the full multi-line comment text — matching how pr_feedback_text
        is rendered.
    """
    if report.last_automated_note is None:
        return []
    return ["", report.last_automated_note]
```

Place it next to `_format_linked_branch_line` and `_format_wait_line` (same pattern: one
private helper shared by both formatters).

## HOW

- In `format_report_for_human`: call
  `lines.extend(_format_last_automated_note_lines(report))` immediately before the existing
  `lines.extend(["", "Recommendations:"])` block.
- In `format_report_for_llm`: call
  `lines.extend(_format_last_automated_note_lines(report))` immediately before the existing
  `lines.append(f"Recommendations: {recommendations_text}")` line.
- No new imports needed (`List` is already imported in this module).

## ALGORITHM

See `_format_last_automated_note_lines` above — a single conditional, no loop.

## DATA

No new data structures. Both formatters gain, conditionally, two extra lines (`""` +
`report.last_automated_note`) directly before their respective `Recommendations` section.
Output is byte-identical to before when `last_automated_note is None`.

## Tests (write first)

In `TestBranchStatusReport` (`tests/checks/test_branch_status.py`), for both
`format_for_human` and `format_for_llm` (parametrize over the two, mirroring the
`_FORMATTERS` list pattern already used in `tests/checks/test_branch_status_linked_branch.py`
if convenient — otherwise two plain tests):

- Build a report with `last_automated_note="## ❌ Implementation Failed\n\nDetails here."`
  (all other fields as in the existing clean-report fixtures). Assert the full note text
  appears in the output, and that its first line's index precedes the line containing
  `"Recommendations"`.
- Build a report with `last_automated_note=None` (the default — no change needed to
  existing fixtures). Assert the note text does not appear, and that output is unchanged
  from before this step (e.g. compare against the pre-existing golden assertions already in
  this test class, if any still hold).

## Commit

One commit: new/extended tests + the helper + the two call sites + passing
pylint/pytest/mypy.

## Prompt

> Implement step 3 of `pr_info/steps/summary.md` (GitHub issue #309) exactly as specified
> in `pr_info/steps/step_3.md`, building on step 2's `last_automated_note` field. Extend
> `tests/checks/test_branch_status.py` first, confirm the new assertions fail, then add
> `_format_last_automated_note_lines` to
> `src/mcp_workspace/checks/branch_status_rendering.py` and wire it into both
> `format_report_for_human` and `format_report_for_llm`, and confirm the tests pass. Run
> pylint, pytest (`-n auto`), and mypy; all must pass. Make exactly one commit containing
> tests + implementation. This is the final step — after this commit, issue #309 is fully
> implemented.
