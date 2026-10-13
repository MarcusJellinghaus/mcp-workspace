# review-plan review log 1

## Round 1 — 2026-10-13
**Findings**:
I'll start by loading the MCP tool schemas I need, then gather the knowledge base, issue, and plan files.Based on the plan, issue, knowledge-base principles, and the actual source files, here are my findings.

NO additional findings beyond the following:

pr_info/steps/step_2.md:~70 (ALGORITHM block) — high — The new `get_comments` try/except catches `Exception` generically and logs at `debug` only. But `get_comments` can raise `IssueIdentityMismatchError` (a `ValueError` subclass, re-raised by `_handle_github_errors`) or a 401/403 `GithubException` (also re-raised) — exactly the two cases the generic `except Exception` actually has to handle, since everything else is already swallowed by the decorator. The sibling `get_issue` call in the same function (`src/mcp_workspace/checks/branch_status.py`) treats `IssueIdentityMismatchError` specially with `logger.warning`, precisely because it signals an issue transfer. The plan's own stated rationale ("matches this file's existing convention [of `debug`]") is incomplete: the file's convention for this specific exception is `warning`, not `debug`. The plan should either add the same `except IssueIdentityMismatchError` branch as the `get_issue` call, or explicitly justify why it's fine to lose that signal here.

pr_info/steps/step_1.md:~45 (Tests section) — medium — The step instructs creating "a small local `_make_comment(body: str) -> CommentData` helper (mirror `_make_issue`'s style)" in `tests/github_operations/test_formatters.py`, implying it doesn't exist yet. It already exists at line 43 of that file with that exact signature. Following the step literally produces a duplicate module-level `def _make_comment`, which pylint will flag (function redefined) and which — because Python resolves the name at call time — would silently change the helper used by every *pre-existing* test in the file that calls `_make_comment()`, not just the new ones. The step's precondition check doesn't cover this, so nothing flags it before implementation starts. The step should say "reuse the existing `_make_comment` helper" instead.
**Decisions**:
Verdict(decision='tasks', tasks=["In step_2.md's ALGORITHM block, change the generic `except Exception` handling around `get_comments` to match the file's actual convention: add an explicit `except IssueIdentityMismatchError` branch that logs at `warning` (as the sibling `get_issue` call does), keeping `debug`-level only for other exceptions. Update the rationale text accordingly.", "In step_1.md's Tests section, remove the instruction to create a new `_make_comment(body: str) -> CommentData` helper in tests/github_operations/test_formatters.py, and instead state that the existing `_make_comment` helper (already defined at line 43) should be reused by the new tests."], escalate_reason=None)
**Changes**:
applied
