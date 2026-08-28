# Step 2 — `output_filtering.truncate_output`: restyle to the house pattern

Reference: [summary.md](./summary.md)

## Context

This is the notice behind the `git` tool. It currently reads
`[truncated — 47 more lines]`, which is already unambiguous — it says "more", not
"total". It is restyled anyway so there is **one pattern for the next person to copy**.
All seven callers in `read_operations.py` thread `max_lines` down from the `git` tool
(`server.py:581`), so naming the parameter is valid.

Per the summary's design note, this function stays **separate** from the identically
named one in `github_operations/formatters.py`. Do not extract a shared helper — they
sit in different architecture layers and sharing would cost a new module plus
`.importlinter` / `tach.toml` churn for a one-line string.

## WHERE

- `src/mcp_workspace/git_operations/output_filtering.py` — `truncate_output`, line 187
- `tests/git_operations/test_output_filtering.py` — truncation tests (line 178+)

## WHAT

Signature unchanged:

```python
def truncate_output(text: str, max_lines: int) -> str:
```

Only the appended notice line changes.

## HOW

No new imports or symbols. The `remaining` local at line 186 becomes unused once the
message stops reporting a remaining count — replace it with a `total` local rather than
leaving a dead variable (pylint will flag it otherwise).

The docstring goes stale with it: lines 175-176 promise "a notice showing how many lines
were omitted", which the new notice no longer does. Reword that `Returns:` line to
describe the applied cap and total instead.

This file uses a **literal** em dash (`—`) at line 187. Keep the literal form.

## ALGORITHM

```
if not text: return text                  # unchanged
lines = text.splitlines()
if len(lines) <= max_lines: return text   # unchanged guard
kept = lines[:max_lines]
total = len(lines)                        # replaces the `remaining` local
kept.append(notice(max_lines, total))
return "\n".join(kept)
```

## DATA

Return value stays `str`. The appended line becomes exactly:

```
[truncated: showing {max_lines} of {total} lines — pass max_lines={total} for the full output]
```

Example:

```
[truncated: showing 200 of 512 lines — pass max_lines=512 for the full output]
```

Note the notice still **starts with `[truncated`**, which is what keeps the four
assertions in `tests/git_operations/test_read_operations.py` (lines 112, 231, 414, 568)
passing untouched.

## TDD — tests first

In `tests/git_operations/test_output_filtering.py`:

1. **`test_over_limit_truncated_with_notice` (line 184-190)** — the `[truncated` assertion
   at line 190 survives. Strengthen it to cover the criterion by adding:
   ```python
   assert "showing 3 of 5 lines" in result
   assert "max_lines=5" in result
   ```
2. **`test_notice_shows_remaining_count` (line 196-199) will break.** It asserts
   `"3 more lines" in result`, and the new notice no longer reports a remaining count.
   Rename it to `test_notice_shows_cap_and_total` and replace the assertion — with
   `max_lines=2` over 5 lines:
   ```python
   assert "showing 2 of 5 lines" in result
   assert "max_lines=5" in result
   ```
   (This test is **not** in the issue's test-churn table but does fail; it was found by
   reading the file.)
3. Leave `test_within_limit_unchanged` and `test_exact_limit_unchanged` alone.

Run pytest, confirm failures, then implement.

## CHECKS

All three MCP checks must pass, then `./tools/format_all.sh`.

## COMMIT

One commit: `Restyle the git output truncation notice to the house showing-X-of-Y pattern`

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`.
>
> Implement step 2 only. Following TDD, first update
> `tests/git_operations/test_output_filtering.py`: strengthen
> `test_over_limit_truncated_with_notice` and rewrite `test_notice_shows_remaining_count`
> (rename to `test_notice_shows_cap_and_total`) as described in the step file, and confirm
> they fail. Then change the notice in `truncate_output` in
> `src/mcp_workspace/git_operations/output_filtering.py` to the exact string in the DATA
> section, replacing the now-unused `remaining` local with `total`, and reword the
> docstring `Returns:` line at lines 175-176 (it still promises a notice "showing how many
> lines were omitted"). Keep the literal em dash character already used in that file. Do
> not extract a shared helper with `github_operations/formatters.py` — the summary
> explains why.
>
> Verify `tests/git_operations/test_read_operations.py` still passes unchanged (its
> assertions check the `[truncated` prefix, which the new message preserves).
>
> Use MCP tools per `CLAUDE.md`, run all three checks until they pass, run
> `./tools/format_all.sh`, and make exactly one commit.
