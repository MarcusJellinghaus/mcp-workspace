# Implementation review log 3

Issue: #310 — Add id/created_at to PRFeedback.conversation_comments

## Round 1 — 2026-10-14
**Findings**:
- `formatters.py` module docstring still says "No API calls or manager dependencies," but the file now imports `ConversationCommentData` from `pr_manager.py` at top level (per design `step_2.md`).
- `tests/github_operations/test_github_read_tools_pr_search.py::test_github_pr_view_with_comments` still sets `conv_comment.updated_at = None` on a mock — a field `ConversationCommentData` no longer has; unused but harmless.

**Decisions**: Skip both — pre-existing stale comment (not introduced incorrectly by this change) and a harmless unused test line. Cosmetic, out of scope per knowledge base.

**Changes**: None.
**Status**: No changes needed.

## Final Status

- Review loop: 1 round, zero findings accepted, zero code changes.
- `run_vulture_check`: clean, no output.
- `run_lint_imports_check`: PASSED — 9 contracts kept, 0 broken.
- `check_branch_status`: CI PASSED; all implementation tasks complete; no open PR yet; branch is BEHIND `origin/main` (rebase recommended before PR creation); label `status-07:code-review`.
- Implementation review for issue #310 is complete. No code changes were required in this run.
