# Step 6 — `format_issue_view(body_note=…)`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_6.md`: add the keyword-only
> `body_note` parameter to `format_issue_view`. Write the tests first. Run pylint, pytest
> (`-n auto`) and mypy, all green. Run `run_format_code`, then make one commit.

## WHERE

- `src/mcp_workspace/github_operations/formatters.py` — `format_issue_view` (`:141`)
- `tests/github_operations/test_formatters_body_note.py` — new (`test_formatters.py` is at
  690/750 lines)

## WHAT

```python
def format_issue_view(
    issue, comments, max_lines=200, *, trusted, fence_id,
    linked_branches=None, include_linked_branches=False,
    body_note: str | None = None,
) -> str:
```

Add to the docstring Args: "body_note: Replaces the body text (e.g. a pointer to a file holding
the raw body). For an untrusted author only the title stays fenced and the note follows outside
the fence. None keeps today's output."

## ALGORITHM (replaces `:207-218`)

```
shown = body_note if body_note is not None else (issue["body"] or "(no description)")
if author_ok:              parts.append(shown)
elif body_note is None:    parts.append(_fence(f"Title: {title}\n\n{shown}", user, association, fence_id))
else:                      parts.append(_fence(f"Title: {title}", user, association, fence_id))
                           parts.append(body_note)
```

## DATA

Same string layout as today. Only the body block differs when `body_note` is set.

## Tests (`test_formatters_body_note.py`; build the data as `test_formatters.py` does)

- **Trusted author + note:**
  - the note appears where the body was;
  - the body text is absent;
  - header, labels and comments are unchanged.
- **Untrusted author + note:**
  - the fence contains `Title: …` and not the note;
  - the note appears after the closing `</untrusted id=…>`;
  - the summary line still reads `title/body`.
- **Empty body + note:** the note is shown, not `(no description)`.
- **`body_note=None`:** output equals the call without the argument, for both trusted and
  untrusted authors.
- **`max_lines`** still truncates the reply.
