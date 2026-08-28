# Step 8 — `file_tools` internal caps: state the cap in `search.py`, document both

Reference: [summary.md](./summary.md)

## Context

Two `file_tools` sites, merged into one step because the second is a comment-only change
with no test and no behavioural change — too small to justify its own commit.

**`search.py`.** `search_files` caps individual result lines at `_MAX_LINE_CHARS = 500`
and reports `... [truncated, line has 1000 chars]` — again the total in the slot where the
cap belongs. `_MAX_LINE_CHARS` is an internal constant with no tool parameter behind it
and is not getting one (Decisions: "`search.py:64` — Internal cap, accepted. Message
improved, no parameter added"), so the message states both numbers and names nothing.

**`file_operations.py`.** `_format_deleted_paths` caps the deleted-path list at 20 and
appends `... and {n} more ({n_files} files, {n_dirs} dirs deleted total)`. **That message
is correct as-is and must not change.** This site differs from every other truncation in
the codebase: the action is already complete — the files are deleted — so there is nothing
for the reader to re-request, and the summary already carries the totals. There is no cap
to lift and no alternative to name. The only thing missing is the record that this was a
decision rather than an oversight, so the next person auditing truncation notices does not
"fix" it into the house style.

Together these are the last two of the internal-cap sites covered by the acceptance
criterion "Each internal-cap site carries a code comment stating the cap is deliberate and
naming the alternative where one exists" (the others are handled in steps 6 and 7).

Out of scope: the `truncated: true` flag in the structured `search_files` result. The
structured output already carries `total_matches`, so it is not misleading in the same
way.

## WHERE

- `src/mcp_workspace/file_tools/search.py` — line 61-65 (inside the context-line loop),
  and the `_MAX_LINE_CHARS = 500` declaration at line 13
- `src/mcp_workspace/file_tools/file_operations.py` — `_format_deleted_paths`,
  lines 372-389
- `tests/file_tools/test_search.py` — `TestSearchFilesLineTruncation` (line 268+)

## WHAT

No signature changes anywhere. In `search.py` this is a string edit plus a code comment
inside the existing `if len(stripped) > _MAX_LINE_CHARS:` branch:

```python
def _format_deleted_paths(paths: list[str], n_files: int, n_dirs: int) -> list[str]:
```

is likewise untouched — `file_operations.py` gets a comment and nothing else.

## HOW

**`search.py`.** Add a comment at the `_MAX_LINE_CHARS = 500` declaration (line 13) or at
the branch recording that the cap is deliberate and that there is no lift, e.g.:

```python
# Deliberate internal cap with no lift parameter: search_files returns many
# lines and a single pathological line must not crowd out the rest. Callers
# who need a full line read the file at the reported line number.
```

The existing marker is built with string concatenation across lines 62-65; keep that
shape and change only the f-string.

**`file_operations.py`.** Add a code comment inside `_format_deleted_paths`, above the
`if len(paths) <= 20:` guard, e.g.:

```python
# The 20-path cap is deliberate and has no lift parameter — unlike the read
# tools, the deletion has already happened, so there is nothing to re-request.
# The summary line carries the true file and directory totals.
```

Do not add a parameter. Do not restyle that message into `showing X of Y`.

## ALGORITHM

```
# search.py — context-line loop
for raw in raw_lines:
    stripped = raw.rstrip("\n")
    if len(stripped) > _MAX_LINE_CHARS:
        stripped = stripped[:_MAX_LINE_CHARS] + marker(_MAX_LINE_CHARS, len(stripped))
    capped.append(stripped)
```

The truncation condition, the slice, and the surrounding budget logic at lines 69-74 are
all untouched. `_format_deleted_paths` has no logic change at all.

## DATA

The marker appended to an over-long search line becomes exactly:

```
 ... [line truncated: showing 500 of {n} chars]
```

(with the same leading space the current code emits). Example:

```
xxxxx… ... [line truncated: showing 500 of 1000 chars]
```

The `search_files` result dict shape — `mode`, `details`, `total_matches`, `truncated`,
`matched_files` — is unchanged.

`_format_deleted_paths` is unchanged: it still returns `list[str]`, either the original
paths when there are 20 or fewer, or the first 20 plus the existing summary line as
entry #21.

## TDD — tests first

In `tests/file_tools/test_search.py`:

1. **`test_long_line_truncated_at_500_chars` (line 271-281).** Replace line 280:
   ```python
   assert "... [line truncated: showing 500 of 1000 chars]" in detail["text"]
   ```
   Keep the `len(detail["text"]) < 1000` and `startswith("x" * 500)` assertions.
2. **`test_context_lines_also_truncated` (line 293-305).** Replace line 303:
   ```python
   assert "... [line truncated: showing 500 of 800 chars]" in lines[0]
   ```
   Keep the `lines[1] == "MATCH"` assertion.
3. **`test_short_line_not_truncated` (line 283-291) survives unchanged.** Its
   `assert "truncated" not in result["details"][0]["text"]` still holds because a
   499-char line is never marked, and the new wording keeps the word "truncated" only on
   the marked path.
4. Every `result["truncated"] is True/False` assertion elsewhere in the file is about the
   structured flag, not the message. Leave them all alone.

**No test change for `file_operations.py`** — there is no behavioural change to test, and
the existing tests for `_format_deleted_paths` (if any) must keep passing untouched. If
the repository has no existing coverage of `_format_deleted_paths`, do **not** add some
here; that would be scope this issue did not ask for.

Run pytest, confirm the two failures, then implement.

## CHECKS

All three MCP checks must pass, then `./tools/format_all.sh`. Pylint is the one to watch
for the comment formatting and line length.

## COMMIT

One commit: `State the 500-char cap in the search_files marker and document both file_tools caps`

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_8.md`.
>
> Implement step 8 only. Following TDD, first update the two marker assertions in
> `tests/file_tools/test_search.py` (`test_long_line_truncated_at_500_chars` line 280 and
> `test_context_lines_also_truncated` line 303) to the new marker in the DATA section, and
> confirm they fail. Then:
>
> - in `src/mcp_workspace/file_tools/search.py`, change the marker f-string at lines 62-65
>   and add the code comment recording that `_MAX_LINE_CHARS` is a deliberate internal cap
>   with no lift parameter;
> - in `src/mcp_workspace/file_tools/file_operations.py`, add a code comment inside
>   `_format_deleted_paths` recording that the 20-path cap is deliberate, that there is no
>   lift parameter because the deletion has already happened, and that the summary line
>   already carries the totals.
>
> Do not add a parameter to `search_files`, do not touch the `truncated` flag in the
> result dict, and do not change the `_format_deleted_paths` message or add tests for it —
> all are explicitly out of scope. Verify `test_short_line_not_truncated` still passes
> unchanged.
>
> Use MCP tools per `CLAUDE.md`, run all three checks until they pass, run
> `./tools/format_all.sh`, and make exactly one commit.
