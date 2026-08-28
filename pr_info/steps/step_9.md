# Step 9 — `file_operations`: document the deliberate deleted-path cap

Reference: [summary.md](./summary.md)

## Context

`_format_deleted_paths` caps the deleted-path list at 20 and appends
`... and {n} more ({n_files} files, {n_dirs} dirs deleted total)`.

**The message is correct as-is and must not change.** This site differs from every other
truncation in the codebase: the action is already complete — the files are deleted — so
there is nothing for the reader to re-request, and the summary already carries the
totals. There is no cap to lift and no alternative to name.

The only thing missing is the record that this was a decision rather than an oversight,
so the next person auditing truncation notices does not "fix" it into the house style.

This is the one step with no test change and no behavioural change. It exists as its own
commit because the acceptance criterion "Each internal-cap site carries a code comment
stating the cap is deliberate and naming the alternative where one exists" covers three
sites, and this is the third.

## WHERE

- `src/mcp_workspace/file_tools/file_operations.py` — `_format_deleted_paths`, lines 372-389

## WHAT

Nothing. No signature change, no string change:

```python
def _format_deleted_paths(paths: list[str], n_files: int, n_dirs: int) -> list[str]:
```

## HOW

Add a code comment inside the function, above the `if len(paths) <= 20:` guard, e.g.:

```python
# The 20-path cap is deliberate and has no lift parameter — unlike the read
# tools, the deletion has already happened, so there is nothing to re-request.
# The summary line carries the true file and directory totals.
```

Do not add a parameter. Do not restyle the message into `showing X of Y`.

## ALGORITHM

None — no logic changes.

## DATA

Unchanged: returns `list[str]`, either the original paths when there are 20 or fewer, or
the first 20 plus the existing summary line as entry #21.

## TDD — tests first

None. There is no behavioural change to test, and the existing tests for
`_format_deleted_paths` (if any) must keep passing untouched. Before committing, run the
suite once to confirm nothing regressed.

If the repository has no existing coverage of `_format_deleted_paths`, do **not** add
some here — that would be scope this issue did not ask for.

## CHECKS

All three MCP checks must pass, then `./tools/format_all.sh`. Pylint is the one that
matters here (comment formatting / line length).

## COMMIT

One commit: `Document the deliberate 20-path cap in the delete summary`

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_9.md`.
>
> Implement step 9 only. This is a comment-only change with no test and no behavioural
> change. In `src/mcp_workspace/file_tools/file_operations.py`, add a code comment inside
> `_format_deleted_paths` recording that the 20-path cap is deliberate, that there is no
> lift parameter because the deletion has already happened, and that the summary line
> already carries the totals.
>
> Do not change the returned message, do not add a parameter, and do not add tests.
>
> Use MCP tools per `CLAUDE.md`, run all three checks to confirm nothing regressed, run
> `./tools/format_all.sh`, and make exactly one commit.
