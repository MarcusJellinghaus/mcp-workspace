# Summary: Surface the latest ❌-marked automated failure/handoff comment in check_branch_status

GitHub issue: #309

## Goal

`mcp-coder`'s workflows post a `❌`-marked GitHub issue comment on review-round-limit
handoffs and hard failures (review/implement/create_pr/create_plan), and surface the most
recent one into `.vscodeclaude_status.txt` (mcp-coder#1184). `check_branch_status` has no
equivalent signal. This feature adds one: the full body of the most recent `❌`-marked
comment (scanning the last 3 issue comments, most-recent-first), rendered as its own block
directly above `Recommendations` in both the human and LLM report formats.

## Architectural / design changes

- **New pure helper, `find_latest_marked_comment`**, added to
  `github_operations/formatters.py` (the existing home for pure, I/O-free functions over
  `CommentData`). It takes `List[CommentData]` and returns `Optional[str]` — no fetching,
  no manager dependency. This is deliberate: it lets `mcp-coder`'s own implementation of
  #1184 import the same scan rule later instead of duplicating it, and it respects
  `tach.toml`'s layering (`mcp_workspace.utils` sits in a bottom layer that cannot import
  `CommentData` from `github_operations.issues.types`, so the helper has to live in
  `github_operations`, not lower).
- **One new field on `BranchStatusReport`**: `last_automated_note: Optional[str] = None`,
  holding the full matched comment body (not a summary).
- **Collector change, no new abstraction**: the fetch-and-scan step is added as a sibling
  to the existing issue-fetch step inside `collect_branch_status`'s existing
  `IssueManager`/`issue_number` scope — not a separate `_collect_*` function, since the
  issue number is already derived there and both calls use the same `issue_manager`. It
  gets its own broad `try/except` (logged at `debug`, matching every other soft-fail
  collector in this file) so a comment-fetch failure never blocks the rest of the report.
- **Rendering**: one shared private helper, `_format_last_automated_note_lines`, used by
  both `format_report_for_human` and `format_report_for_llm` — following the file's existing
  pattern (`_format_linked_branch_line`, `_format_wait_line`) of one render decision shared
  between both formatters rather than duplicated. Renders nothing when the field is `None`;
  otherwise a blank line followed by the full multi-line comment text, placed directly
  before the `Recommendations` block (matching how `pr_feedback_text` is rendered).

No new files, modules, or directories. No change to any existing field, function signature,
or behavior other than the additions described above.

## Files touched

| File | Change |
|---|---|
| `src/mcp_workspace/github_operations/formatters.py` | add `find_latest_marked_comment` |
| `tests/github_operations/test_formatters.py` | add tests for the new helper |
| `src/mcp_workspace/checks/branch_status.py` | add `last_automated_note` field; add collector step in `collect_branch_status` |
| `tests/checks/test_branch_status.py` | extend `TestCollectBranchStatus` and `TestBranchStatusReport` |
| `src/mcp_workspace/checks/branch_status_rendering.py` | add `_format_last_automated_note_lines`; wire into both formatters |

## Steps

1. `step_1.md` — pure helper `find_latest_marked_comment` (TDD)
2. `step_2.md` — collector wiring in `collect_branch_status` + new `BranchStatusReport` field (TDD)
3. `step_3.md` — rendering in both formatters (TDD)

Each step is one commit: tests + implementation + passing pylint/pytest/mypy.
