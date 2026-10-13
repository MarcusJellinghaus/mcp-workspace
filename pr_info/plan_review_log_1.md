# review-plan review log 1

## Round 1 — 2026-10-13
**Findings**:
I'll gather the knowledge base, the issue, and the plan files to review.Now I have enough to compile findings.

**Findings:**

`pr_info/steps/step_1.md:100` — high — Step 1 types `_comment()` in `tests/checks/test_branch_status_pr_feedback.py` to return `dict[str, Any]`, but `PRFeedback["conversation_comments"]` is retyped to `list[ConversationCommentData]` in this same step. Under this project's `strict = true` mypy config, assigning a `dict[str, Any]`-returning helper's output (`feedback["conversation_comments"] = [_comment(...)]`) into a `list[ConversationCommentData]` field is a type error, not a pass. The helper must be typed to return `ConversationCommentData` (or the assignment cast), or mypy will fail — contradicting the step's own "all checks must pass" exit criterion.

`pr_info/steps/step_2.md:80` — high — `_make_comment()` in `tests/github_operations/test_formatters.py` is shared between `TestFormatIssueView` (`test_format_issue_view_with_comments`, calling `_make_comment(user="alice", ...)`, consumed by `format_issue_view()` which still reads `comment['user']`) and `TestFormatPrView`. Step 2 retypes this single shared helper to build `ConversationCommentData` with an `author` kwarg (no `user` key), which breaks the untouched, out-of-scope `format_issue_view` test (wrong kwarg name and missing `user` key). The step only anticipates `_make_issue`/`format_issue_view` needing the `CommentData` import, not that `_make_comment` itself is reused there — needs a separate helper (e.g. `_make_conversation_comment`) for the PR-view tests instead of mutating the shared one.

`pr_info/steps/step_3.md:40` — medium — Gives a first code block importing `ConversationCommentData` from `formatters` (which does not re-export it) with a comment admitting uncertainty, then immediately contradicts it with a second, correct block importing from `pr_manager`. Two conflicting code examples in the same step risks the wrong one being copied; should state the single correct import only.

`pr_info/steps/step_1.md:67` — low — ALGORITHM pseudocode (`yield {author, body, id, created_at}`) is invalid Python (set literal, not dict; `yield` in a non-generator) and names a local variable `id`, shadowing the builtin (pylint `redefined-builtin`). Harmless as illustrative pseudocode, but risks being copied literally and triggering a pylint failure or genuinely wrong code.
**Decisions**:
Verdict(decision='tasks', tasks=["In step_1.md, type the `_comment()` helper in tests/checks/test_branch_status_pr_feedback.py to return `ConversationCommentData` (not `dict[str, Any]`), matching the retyped `PRFeedback['conversation_comments']` field, so mypy strict mode passes.", "In step_2.md, do not retype the shared `_make_comment()` helper in tests/github_operations/test_formatters.py to use an `author` kwarg. Add a separate helper (e.g. `_make_conversation_comment()`) for the PR-view tests needing `ConversationCommentData`, and leave `_make_comment()`/`format_issue_view()`'s `user` key untouched.", "In step_3.md, remove the first code block that imports `ConversationCommentData` from `formatters` (which doesn't re-export it); keep only the correct import from `pr_manager` so there's a single unambiguous example."], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-10-13
**Findings**:
I'll gather context: knowledge base files, issue #310, and the plan files.Good — existing direct tests confirm the plan's instruction to add a focused unit test is buildable and consistent with existing test patterns. No further substantive issues found beyond the pre-existing low-severity pseudocode nit from round 1 that remains unfixed.

**Findings:**

`pr_info/steps/step_1.md:67` — low — ALGORITHM pseudocode (`yield {author, body, id, created_at}`) is invalid Python (set literal, not dict; `yield` in a function that returns a list, not a generator) and names a local `id`, shadowing the builtin. Flagged in round 1 but not included in the applied fix list — still present.

`pr_info/steps/step_3.md:33` — low — Same pseudocode pattern here: `for c in ...: yield ConversationCommentData(...)` describes a generator, but the precondition/DATA sections establish the actual code is a list comprehension. Risk of being copied literally into non-generator code.
**Decisions**:
Verdict(decision='dismiss', tasks=[], escalate_reason=None)
**Changes**:
dismiss
