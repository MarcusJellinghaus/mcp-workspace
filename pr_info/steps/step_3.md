# Step 3 — `ci_log_parser`: one marker, one spelling, name `max_log_lines`

Reference: [summary.md](./summary.md)

## Context

The CI truncation marker `[... truncated 20 lines ...]` is emitted from **two** places
that produce a byte-identical string today:

- `truncate_ci_details` (line 57)
- `build_ci_error_details` (line 347), which builds it inline and never calls
  `truncate_ci_details`

Changing only one would ship two spellings of one marker, so both move behind a single
helper.

Separately, line 371 heads the list of jobs whose logs were dropped **entirely**
(`remaining_budget <= 10`, line 335). "Truncated to save space" undersells that — those
jobs get no log lines at all.

**Constraint — no pasteable value here.** `build_ci_error_details` shares one budget
across up to three failed jobs (lines 331-352), so `max_log_lines={total}` would not
return that job's full log when several jobs failed. Name the parameter only. Do not
"fix" this back to the house style.

`max_log_lines` is a real parameter on the **build** path that reaches both marker sites:
`check_branch_status(max_log_lines=...)` (`server.py:885`) → `async_poll_branch_status`
(`branch_status_polling.py:100`) → `collect_branch_status` (`branch_status.py:479`) →
`build_ci_error_details` (`branch_status.py:248, 259`).

**The render path does not thread it today — this step fixes that.**
`async_poll_branch_status` calls `report.format_for_llm(...)`
(`branch_status_polling.py:124, 154`) *without* `max_lines`, so `format_report_for_llm`
falls back to its hard-coded default of 300 and the `truncate_ci_details` call at
`branch_status_rendering.py:228` applies a cap `max_log_lines` cannot lift. With
`max_log_lines=1000` the build stage keeps ~1000 lines and the render stage cuts them
back to 300 while the marker tells the reader to raise `max_log_lines` — exactly the
misdirection this issue exists to remove, and a breach of the acceptance criterion
"No notice names a parameter its caller does not accept". Passing
`max_lines=max_log_lines` at both `format_for_llm` call sites makes the parameter the
marker names the one that governs the cut. Defaults are unchanged: `max_log_lines` and
`format_report_for_llm`'s `max_lines` are both 300, so default-sized calls render
byte-identically.

The third caller, `truncate_ci_details` at `branch_status.py:204`, sits in
`get_failed_jobs_summary`, which is in `__all__` but has no production callers — only
tests — so naming the parameter is still safe.

## WHERE

- `src/mcp_workspace/github_operations/ci_log_parser.py` — new private helper; lines 55-57,
  344-352, 371
- `src/mcp_workspace/checks/branch_status_polling.py` — `format_for_llm` call sites,
  lines 124 and 154
- `tests/github_operations/test_ci_log_parser.py` — `test_truncation_marker_shows_count`
  (line 44)
- `tests/checks/test_branch_status_polling_orchestrator.py` — new test (models on the
  existing `format_for_llm.call_args.kwargs` assertions at lines 340-341, 425)

## WHAT

New module-private helper, placed above `truncate_ci_details`:

```python
def _truncation_marker(kept: int, total: int) -> str:
    """Build the one and only CI log truncation marker.

    Shared by `truncate_ci_details` and `build_ci_error_details` so the marker
    has a single spelling. Names `max_log_lines` without a pasteable value:
    `build_ci_error_details` shares one budget across up to three failed jobs,
    so `max_log_lines={total}` would not return this job's full log.
    """
```

**Two arguments, not three.** `omitted` is always `total - kept`; passing it separately
would reintroduce the drift the helper exists to prevent.

Do **not** add `_truncation_marker` to `__all__` — it is private.

## HOW

Call site 1 — `truncate_ci_details`, lines 52-57. Note `tail_lines = max_lines -
head_lines`, so `head_lines + tail_lines == max_lines` exactly. Pass `max_lines`
directly and **delete the now-unused `truncated_count` local** at line 55.

Call site 2 — `build_ci_error_details`, lines 344-350. Here
`kept == head_count + tail_count`.

Site 3 — line 371, a plain string literal replacement, no helper involved.

Site 4 — `branch_status_polling.py:124` and `:154`: pass `max_lines=max_log_lines` to
`report.format_for_llm(...)`. No signature changes anywhere — `format_for_llm`
(`branch_status.py:106`) and `format_report_for_llm` (`branch_status_rendering.py:166`)
already accept `max_lines`; only the two call sites gain the keyword.

## ALGORITHM

```
# helper
def _truncation_marker(kept, total):
    return f"[... {total - kept} lines omitted: showing {kept} of {total} — raise max_log_lines for more ...]"

# truncate_ci_details, replacing lines 55-57
return "\n".join(head + [_truncation_marker(max_lines, len(lines))] + tail)

# build_ci_error_details, replacing the inline marker at 346-348
truncated_log = (
    log_lines[:head_count]
    + [_truncation_marker(head_count + tail_count, len(log_lines))]
    + log_lines[-tail_count:]
)

# branch_status_polling.py:124 and :154 — the render-stage cap now honours
# the parameter the marker names.
return report.format_for_llm(max_lines=max_log_lines, fail_on_reviews=fail_on_reviews)
return report.format_for_llm(
    max_lines=max_log_lines, wait_context=wait_ctx, fail_on_reviews=fail_on_reviews
)
```

## DATA

Both marker sites now emit exactly:

```
[... {omitted} lines omitted: showing {kept} of {total} — raise max_log_lines for more ...]
```

Example (30 lines, `max_lines=10`, `head_lines=3`):

```
[... 20 lines omitted: showing 10 of 30 — raise max_log_lines for more ...]
```

Line 371 becomes exactly:

```
## Other failed jobs (logs omitted — raise max_log_lines to include them)
```

Return types are unchanged: `truncate_ci_details -> str`,
`build_ci_error_details -> Optional[str]`.

## TDD — tests first

In `tests/github_operations/test_ci_log_parser.py`:

1. **Update `test_truncation_marker_shows_count` (line 44-58).** Input is 30 lines,
   `max_lines=10`, `head_lines=3`. Replace line 49 with:
   ```python
   assert "[... 20 lines omitted: showing 10 of 30 — raise max_log_lines for more ...]" in result
   ```
   The blank-line assertions at lines 51-58 look up the marker by searching for
   `"truncated"` in the line — **update that predicate to `"omitted"`**, since the new
   marker no longer contains the word "truncated".
2. **`test_over_limit_truncated` (line 33-42) will break** at line 42
   (`assert "truncated" in result`). Change it to `assert "omitted" in result`.
3. **`test_truncates_long_output` (line 328-351) will break** at line 351
   (`assert "truncated" in result`). Change it to `assert "omitted" in result`.
4. **Add one new test** asserting both marker sites agree, which is the whole point of
   the helper:
   ```python
   def test_both_marker_sites_use_one_spelling(self) -> None:
       """`truncate_ci_details` and `build_ci_error_details` emit the same marker shape."""
   ```
   Assert that the output of each contains `"lines omitted: showing "` and
   `"raise max_log_lines for more"`.
5. **`test_per_job_line_budget_truncation` (line 373+)** exercises the line-371 path. No
   test asserts the `## Other failed jobs` header today, so add that assertion here:
   ```python
   assert "## Other failed jobs (logs omitted — raise max_log_lines to include them)" in result
   ```
6. **Add one test for the render-stage cap** in
   `tests/checks/test_branch_status_polling_orchestrator.py`, so the parameter the marker
   names really governs the cut:
   ```python
   async def test_max_log_lines_reaches_the_render_cap(self) -> None:
       """`max_log_lines` is forwarded to `format_for_llm`, not just to collection."""
   ```
   Model it on the existing `format_for_llm.call_args.kwargs` tests (lines 338-341, 421-425):
   patch `collect_branch_status` to return a `MagicMock(spec=BranchStatusReport)`, call
   `await async_poll_branch_status(project_dir, max_log_lines=500)`, and assert
   `mock_report.format_for_llm.call_args.kwargs["max_lines"] == 500`.

   The two `assert result == report.format_for_llm()` assertions (lines 79 and 490) keep
   passing untouched: both defaults are 300, so passing it explicitly changes nothing.

Run pytest, confirm failures, then implement.

## CHECKS

All three MCP checks must pass, then `./tools/format_all.sh`. Watch pylint for the
deleted `truncated_count` local.

## COMMIT

One commit: `Unify the CI log truncation marker and honour max_log_lines at the render cap`

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`.
>
> Implement step 3 only. Following TDD, first update
> `tests/github_operations/test_ci_log_parser.py` as described in the step file — the
> marker assertion at line 49, the two `"truncated" in result` assertions at lines 42 and
> 351, the marker-lookup predicate at lines 51-58, the new `## Other failed jobs` header
> assertion in `test_per_job_line_budget_truncation`, plus one new test that both marker
> sites emit the same shape. Then add
> `test_max_log_lines_reaches_the_render_cap` to
> `tests/checks/test_branch_status_polling_orchestrator.py` as described. Confirm they fail.
>
> Then in `src/mcp_workspace/github_operations/ci_log_parser.py`: add the private
> `_truncation_marker(kept: int, total: int) -> str` helper with the docstring given in
> the step file, call it from both `truncate_ci_details` (passing `max_lines` directly,
> and delete the now-unused `truncated_count` local) and `build_ci_error_details`
> (passing `head_count + tail_count`), and replace the `## Other failed jobs` header at
> line 371. Do not add the helper to `__all__`. Do not add a pasteable
> `max_log_lines={total}` value at any of these three sites — the step file explains why.
>
> Then in `src/mcp_workspace/checks/branch_status_polling.py`, pass
> `max_lines=max_log_lines` to `report.format_for_llm(...)` at lines 124 and 154, so the
> render-stage `truncate_ci_details` cap is the one the marker tells the reader to raise.
> Do not change any signature — `format_for_llm` already accepts `max_lines`.
>
> Use MCP tools per `CLAUDE.md`, run all three checks until they pass, run
> `./tools/format_all.sh`, and make exactly one commit.
