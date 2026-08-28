# Step 1 — `formatters.truncate_output`: name the cap and `max_lines`

Reference: [summary.md](./summary.md)

## Context

`truncate_output` in `github_operations/formatters.py` is the notice behind
`github_issue_view` and `github_pr_view`. It prints `... truncated, 290 lines total`,
where `290` is the length of the issue, not the limit — but it sits in the slot where a
reader expects the limit. Both callers accept `max_lines`, so naming it with a pasteable
value is valid by construction.

## WHERE

- `src/mcp_workspace/github_operations/formatters.py` — `truncate_output`, line 43
- `tests/github_operations/test_formatters.py` — `TestTruncateOutput` (line 60+)

## WHAT

Signature unchanged:

```python
def truncate_output(text: str, max_lines: int) -> str:
```

Only the returned notice string changes. Both callers (`format_issue_view:76`,
`format_pr_view:161`) are untouched and inherit the new wording.

## HOW

No new imports, no new symbols, no decorator changes. A pure string edit inside the
existing early-return structure — the `len(lines) <= max_lines` guard at line 40 already
means the notice only ever renders when a cut actually happened.

## ALGORITHM

```
lines = text.splitlines()
if len(lines) <= max_lines:        # unchanged guard
    return text
total = len(lines)
# shown is always exactly max_lines here, because we only reach this
# branch when len(lines) > max_lines — no min() needed
return "\n".join(lines[:max_lines]) + notice(max_lines, total)
```

## DATA

Return value stays `str`. The appended notice becomes exactly:

```
\n\n... truncated: showing {max_lines} of {total} lines. Pass max_lines={total} for the full output.
```

Example for a 290-line issue at the default cap:

```
... truncated: showing 200 of 290 lines. Pass max_lines=290 for the full output.
```

## TDD — tests first

In `tests/github_operations/test_formatters.py`:

1. **Update `test_truncate_output_truncation` (line 69-77).** The input is
   `"\n".join(f"line{i}" for i in range(10))` with `max_lines=3`, so the cut is 3 of 10.
   Replace line 77 with assertions covering the acceptance criterion "both numbers and
   `max_lines`":
   ```python
   assert "showing 3 of 10 lines" in result
   assert "max_lines=10" in result
   ```
2. **Leave `test_truncate_output_no_truncation` and `test_truncate_output_exact_limit`
   alone.** The latter asserts `"truncated" not in result`; the new wording keeps the
   word only on the cut path, so it still passes.
3. **Leave `test_format_issue_view_truncation` (line 139-143) and
   `test_format_pr_view_truncation` (line 296-300) alone.** Both assert
   `"truncated" in result`, which the new wording preserves. They are the regression
   guard that both callers still inherit the notice.

Run pytest and confirm the updated assertions fail, then implement.

## CHECKS

`mcp__mcp-tools-py__run_pylint_check`, `mcp__mcp-tools-py__run_pytest_check`,
`mcp__mcp-tools-py__run_mypy_check` — all must pass. Then `./tools/format_all.sh`.

## COMMIT

One commit: `Name the applied cap and max_lines in the issue/PR view truncation notice`

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`.
>
> Implement step 1 only. Following TDD, first update
> `tests/github_operations/test_formatters.py::TestTruncateOutput::test_truncate_output_truncation`
> to assert the notice contains both `showing 3 of 10 lines` and `max_lines=10`, and
> confirm it fails. Then change the notice returned by `truncate_output` in
> `src/mcp_workspace/github_operations/formatters.py` to the exact string given in the
> DATA section of the step file. Do not change the function signature, the
> `len(lines) <= max_lines` guard, or either caller.
>
> Use the MCP tools per `CLAUDE.md`: `mcp__workspace__read_file` / `edit_file` for files,
> and run all three checks (`run_pylint_check`, `run_pytest_check` with
> `extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration
> and not claude_api_integration and not formatter_integration and not
> github_integration and not langchain_integration"]`, `run_mypy_check`) until they pass.
> Then run `./tools/format_all.sh` and make exactly one commit.
