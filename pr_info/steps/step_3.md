# Step 3 — Render `submitted_at` in `format_pr_feedback()`

See `pr_info/steps/summary.md` for full architecture and context. Depends on step 2 (`ChangesRequestedData` must exist).

## WHERE

- `src/mcp_workspace/checks/pr_feedback.py` — `format_pr_feedback()`, the `for review in changes_requested:` block.
- `tests/checks/test_branch_status_pr_feedback.py` — `_changes_requested()` helper and `TestChangesRequested`.

## WHAT

No new functions. Modify the existing loop body in `format_pr_feedback()`:

```python
for review in changes_requested:
    author = review.get("author", "")
    submitted_at = review.get("submitted_at")
    ...
    rendered.append(f"[changes_requested] {author}{suffix}: {body}")
```

## HOW

- `_changes_requested()` test helper in `tests/checks/test_branch_status_pr_feedback.py` changes its return type from an ad-hoc `dict[str, Any]` to `ChangesRequestedData` (import from `mcp_workspace.github_operations.pr_types`, alongside the existing `ConversationCommentData`/`PRFeedback` import), and gains a `submitted_at: Optional[str] = None` parameter — `submitted_at` is a required key on the TypedDict, so every call site must supply it even when the value is `None`.
- No change to `PRFeedback`, `_MAX_FEEDBACK_ITEMS`, `_MAX_LINES_PER_COMMENT`, or any other section's rendering.

## ALGORITHM

```
suffix = f" ({submitted_at})" if submitted_at else ""
line = f"[changes_requested] {author}{suffix}: {body}"
```

## DATA

Rendered line: `"[changes_requested] carol (2025-01-01T00:00:00+00:00): Needs work"` when `submitted_at` is set, `"[changes_requested] carol: Needs work"` when it is `None`. No change to any other `PRFeedback` field's rendering, to `format_pr_feedback`'s return type (`str`), or to the item cap / truncation logic.

## Tests (write first)

In `tests/checks/test_branch_status_pr_feedback.py`:

- Update `_changes_requested()` to build `ChangesRequestedData(author=..., body=..., submitted_at=submitted_at)`.
- Update the existing `test_changes_requested_rendered` to pass `submitted_at=None` explicitly and assert the rendered line has no parenthetical (e.g. `"[changes_requested] carol: Needs work" in result` and `"(" not in result.split("[changes_requested]")[1].split(":")[0]` or an equivalent direct substring check).
- New: `test_changes_requested_with_submitted_at_rendered` — `submitted_at="2025-01-01T00:00:00+00:00"` → assert `"[changes_requested] carol (2025-01-01T00:00:00+00:00): Needs work" in result`.
- `TestMixedFullExample.test_mixed_full_example` keeps working unchanged (it only asserts `"[changes_requested]" in line`, not the exact text), since `_changes_requested()`'s default `submitted_at=None` keeps that call passing.

## Commit

One commit: `format_pr_feedback()` change + helper retype + tests above.

## LLM Prompt

> Implement `pr_info/steps/step_3.md` for issue #324 (architecture in `pr_info/steps/summary.md`; depends on step 2's `ChangesRequestedData`). Follow TDD: update `_changes_requested()` and the rendering tests first, confirm they fail against the current `format_pr_feedback()`, then add the `submitted_at` suffix logic until green. Do not touch `_pr_feedback_sources.py` in this step. Run `mcp__mcp-tools-py__run_ruff_check`, `run_pylint_check`, `run_pytest_check` (`extra_args: ["-n", "auto"]`), and `run_mypy_check` until clean, then make exactly one commit.
