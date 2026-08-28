# Step 8 — `search.py`: state the cap in the per-line truncation marker

Reference: [summary.md](./summary.md)

## Context

`search_files` caps individual result lines at `_MAX_LINE_CHARS = 500` and reports
`... [truncated, line has 1000 chars]` — again the total in the slot where the cap
belongs. `_MAX_LINE_CHARS` is an internal constant with no tool parameter behind it and
is not getting one (Decisions: "`search.py:64` — Internal cap, accepted. Message
improved, no parameter added"), so the message states both numbers and names nothing.

Out of scope: the `truncated: true` flag in the structured result. The structured output
already carries `total_matches`, so it is not misleading in the same way.

## WHERE

- `src/mcp_workspace/file_tools/search.py` — line 61-65 (inside the context-line loop)
- `tests/file_tools/test_search.py` — `TestSearchFilesLineTruncation` (line 268+)

## WHAT

No signature changes anywhere. This is a string edit plus a code comment inside the
existing `if len(stripped) > _MAX_LINE_CHARS:` branch.

## HOW

Add a comment at the `_MAX_LINE_CHARS = 500` declaration (line 13) or at the branch
recording that the cap is deliberate and that there is no lift, e.g.:

```python
# Deliberate internal cap with no lift parameter: search_files returns many
# lines and a single pathological line must not crowd out the rest. Callers
# who need a full line read the file at the reported line number.
```

The existing marker is built with string concatenation across lines 62-65; keep that
shape and change only the f-string.

## ALGORITHM

```
for raw in raw_lines:
    stripped = raw.rstrip("\n")
    if len(stripped) > _MAX_LINE_CHARS:
        stripped = stripped[:_MAX_LINE_CHARS] + marker(_MAX_LINE_CHARS, len(stripped))
    capped.append(stripped)
```

The truncation condition, the slice, and the surrounding budget logic at lines 69-74 are
all untouched.

## DATA

The marker appended to an over-long line becomes exactly:

```
 ... [line truncated: showing 500 of {n} chars]
```

(with the same leading space the current code emits). Example:

```
xxxxx… ... [line truncated: showing 500 of 1000 chars]
```

The result dict shape — `mode`, `details`, `total_matches`, `truncated`,
`matched_files` — is unchanged.

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

Run pytest, confirm the two failures, then implement.

## CHECKS

All three MCP checks must pass, then `./tools/format_all.sh`.

## COMMIT

One commit: `State the 500-char cap in the search_files line truncation marker`

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_8.md`.
>
> Implement step 8 only. Following TDD, first update the two marker assertions in
> `tests/file_tools/test_search.py` (`test_long_line_truncated_at_500_chars` line 280 and
> `test_context_lines_also_truncated` line 303) to the new marker in the DATA section, and
> confirm they fail. Then in `src/mcp_workspace/file_tools/search.py`, change the marker
> f-string at lines 62-65 and add the code comment recording that `_MAX_LINE_CHARS` is a
> deliberate internal cap with no lift parameter.
>
> Do not add a parameter to `search_files`, and do not touch the `truncated` flag in the
> result dict — both are explicitly out of scope. Verify `test_short_line_not_truncated`
> still passes unchanged.
>
> Use MCP tools per `CLAUDE.md`, run all three checks until they pass, run
> `./tools/format_all.sh`, and make exactly one commit.
