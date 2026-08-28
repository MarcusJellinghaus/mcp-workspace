# Step 6 — `pr_feedback`: reorder sections, restyle notices, add a conditional footer

Reference: [summary.md](./summary.md)

## Context

Three coupled changes in one function, hence one step:

1. **Render order.** Current order is unresolved threads → conversation comments →
   changes-requested → alerts (lines 60-90) under a single 20-item cap. Conversation
   comments never drain — they accumulate and nothing removes them — yet they sit ahead
   of the two sections that decide the merge verdict. On a PR with 25 comments the budget
   fills with threads plus comments and **alerts never render at all**.
2. **Notice wording** for the per-body cut (line 37) and the item cap (line 95).
3. **A conditional footer** that must render only when something was actually cut. Its
   condition depends on the body-truncation change, so it cannot be split off.

New order: **unresolved threads → changes-requested → alerts → conversation comments.**
The 20-item cap stays; only the non-draining section moves.

Two things this deliberately does **not** do:

- It does not add per-section budgets. With the single shared cap kept, more than 20
  unresolved threads still starve alerts. That case is accepted; the fix targets the
  non-draining section, which is the one that occurs in practice.
- It does not change any verdict. `blocks_merge` is computed from the feedback data
  (lines 126-130), not from the rendered text.

## WHERE

- `src/mcp_workspace/checks/pr_feedback.py` — `_truncate_body` (line 28), new footer
  constant, `format_pr_feedback` (lines 40-107)
- `tests/checks/test_branch_status_pr_feedback.py` — lines 189-212, 361-373, plus new tests

## WHAT

`_truncate_body` keeps its signature and stays **pure**:

```python
def _truncate_body(body: str) -> str:
```

`format_pr_feedback` keeps its signature:

```python
def format_pr_feedback(feedback: PRFeedback) -> str:
```

New module-level constant next to `_MAX_FEEDBACK_ITEMS` / `_MAX_LINES_PER_COMMENT`:

```python
_FULL_TEXT_HINT = "Full comment text: github_pr_view(include_comments=True)"
```

`include_comments=True` is spelled out because it defaults to `False` on `github_pr_view`
(`server.py:662`), unlike `github_issue_view`. Without it the reader lands on an empty
result.

## HOW

**Footer condition, without changing `_truncate_body`.** `_truncate_body` returns its
input unchanged when it does not cut, so the caller can detect a cut by comparing. There
are exactly three call sites (threads, comments, changes-requested — alerts render no
body). At each:

```python
raw = thread.get("body", "")
body = _truncate_body(raw)
body_cut = body_cut or body != raw
```

No tuple return, no marker-substring sniffing, no threshold duplicated in two places.

**Section move.** Physically move the `for comment in comments:` block (lines 74-77) to
sit after the `for alert in alerts:` block (lines 84-90). Nothing else about the loops
changes.

**Footer placement.** Append `_FULL_TEXT_HINT` as the **last** line, after the
`[unavailable]` lines and the resolved-thread count.

**On the two mentions of `github_pr_view`.** When the item cap fires, both the cap line
and the footer name the tool. This is intentional, not redundant: the cap line offers the
**full list of items**, the footer offers the **full text of a body that was cut**.

## ALGORITHM

```
body_cut = False
rendered = []
for thread in unresolved:        body = _truncate_body(raw); body_cut |= body != raw; rendered.append(...)
for review in changes_requested: body = _truncate_body(raw); body_cut |= body != raw; rendered.append(...)
for alert in alerts:             rendered.append(...)          # no body, no flag
for comment in comments:         body = _truncate_body(raw); body_cut |= body != raw; rendered.append(...)

total = len(rendered)
cap_fired = total > _MAX_FEEDBACK_ITEMS
if cap_fired: rendered = rendered[:_MAX_FEEDBACK_ITEMS] + [cap_notice(total)]

lines = ["PR Reviews:"] + rendered + unavailable_lines + resolved_line
if body_cut or cap_fired: lines.append(_FULL_TEXT_HINT)
return "\n".join(lines)
```

Note `body_cut |= ...` is written as `body_cut = body_cut or ...` in the source; `|=` is
shorthand for the pseudocode only.

## DATA

Return value stays `str`. Three strings change:

**Per-body cut** (`_truncate_body`, replacing `"\n... (truncated)"`):

```
\n... (truncated: showing {_MAX_LINES_PER_COMMENT} of {total} lines)
```

e.g. `... (truncated: showing 10 of 20 lines)`

**Item cap** (replacing `f"... and {total - _MAX_FEEDBACK_ITEMS} more"`):

```
... and {total - _MAX_FEEDBACK_ITEMS} more of {total} items — full list via github_pr_view(include_comments=True)
```

e.g. `... and 10 more of 30 items — full list via github_pr_view(include_comments=True)`

**Footer** — the `_FULL_TEXT_HINT` constant, appended only when
`body_cut or cap_fired`.

The clean-PR early return at line 56 (`"Reviews: clean (0 unresolved threads, 0 alerts)"`)
is unaffected — it returns before any of this.

## TDD — tests first

1. **`test_long_comment_body_truncated` (line 192-199).** Line 199 asserts
   `"... (truncated)" in result`; the 20-line body is cut at 10. Replace with:
   ```python
   assert "... (truncated: showing 10 of 20 lines)" in result
   ```
   Add an assertion that the footer now renders:
   ```python
   assert "github_pr_view(include_comments=True)" in result
   ```

2. **`test_thirty_items_capped_at_twenty` (line 205-212)** still passes as written — the
   new cap message contains `"... and 10 more"` as a prefix — but strengthen it:
   ```python
   assert "... and 10 more of 30 items" in result
   assert "github_pr_view(include_comments=True)" in result
   ```

3. **`TestCapOrdering` (line 361-373).** The test body still passes (25 threads fill the
   cap; comment and alert are dropped either way; `"... and 7 more"` is still a prefix of
   the new message), but its class docstring at line 362 documents the **old** order.
   Update it to `unresolved → changes_requested → alerts → comments` and add a comment
   noting that thread-heavy overflow still starves alerts by design.

4. **`test_mixed_full_example` (line 264-296) needs no change.** It has 4 short-bodied
   items, so neither the cap nor any body cut fires, the footer does not render, and
   `lines[-1] == "12 resolved threads"` still holds. This is the regression guard proving
   the footer really is conditional.

5. **Add the acceptance-criterion test — alerts survive comment-heavy overflow:**
   ```python
   def test_alerts_survive_comment_heavy_overflow(self) -> None:
       """Alerts render even when conversation comments overflow the cap."""
   ```
   Build feedback with 1 unresolved thread, 1 changes-requested, 1 alert and 30
   conversation comments. Assert `"[alert]" in result` and
   `"[changes_requested]" in result`, and that the alert line appears *before* the first
   `[comment]` line (compare indices in `result.split("\n")`). Under the old order this
   test fails; that is the point.

6. **Add a footer-absence test:**
   ```python
   def test_footer_absent_when_nothing_was_cut(self) -> None:
       """No footer on a PR with feedback that fits."""
   ```
   A couple of short-bodied comments; assert `"github_pr_view"` is not in the result.

Run pytest, confirm failures, then implement.

## CHECKS

All three MCP checks must pass, then `./tools/format_all.sh`.

## COMMIT

One commit: `Reorder PR feedback sections and make the truncation footer conditional`

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_6.md`.
>
> Implement step 6 only. Following TDD, first update
> `tests/checks/test_branch_status_pr_feedback.py` as described in the step file: the
> body-truncation assertion at line 199, the item-cap assertions at line 212, the
> `TestCapOrdering` docstring at line 362, plus two new tests
> (`test_alerts_survive_comment_heavy_overflow` and
> `test_footer_absent_when_nothing_was_cut`). Confirm the new tests fail.
>
> Then in `src/mcp_workspace/checks/pr_feedback.py`:
> - add the `_FULL_TEXT_HINT` module constant;
> - change `_truncate_body`'s marker to the exact string in the DATA section, keeping its
>   signature and purity;
> - in `format_pr_feedback`, move the conversation-comments loop to run **after** the
>   alerts loop, track a `body_cut` flag at the three `_truncate_body` call sites by
>   comparing output against input, replace the item-cap message, and append
>   `_FULL_TEXT_HINT` as the last line only when `body_cut or cap_fired`.
>
> Do not add per-section budgets and do not change `collect_pr_feedback` or the
> `blocks_merge` computation — the step file explains why. Verify
> `test_mixed_full_example` still passes unchanged; it proves the footer is conditional.
>
> Use MCP tools per `CLAUDE.md`, run all three checks until they pass, run
> `./tools/format_all.sh`, and make exactly one commit.
