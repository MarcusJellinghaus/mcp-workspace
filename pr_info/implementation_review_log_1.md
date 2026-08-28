# review-implementation review log 1

## Round 1 — 2026-08-28
**Findings**:
I'll start by loading the tools I need and gathering context.Checks run on the branch: pytest 1893 passed / 2 skipped, mypy clean, pylint clean, ruff clean, vulture clean.

`src/mcp_workspace/github_operations/issues/comments_mixin.py:83` — medium — `add_comment` is the cross-repo *write* the issue names as the primary danger, but no test asserts the guard fires before `create_comment`; routing tests exist only for `manager.get_issue`, `labels_mixin.set_labels` and `_pr_feedback_sources`, leaving `comments_mixin` (4 sites), `events_mixin` (1) and `branch_manager` (1) covered only by mocks that would still pass if the routing were reverted.
`src/mcp_workspace/github_operations/issues/cache.py:337` — low — the new exception lands in the broad catch and `_fetch_additional_issues` returns the pre-fix cached wrong-repository `IssueData` under the requested number (warning only); accepted in `pr_info/steps/summary.md` but the cross-repo data is still served to callers.
`pyproject.toml:120` — low — six new blanket per-file `DOC502` waivers disable exception-doc checking for whole modules (incl. `manager.py`, `labels_mixin.py`); per-function `# noqa: DOC502` on the routed methods would keep the rule live for the rest of each file.
`tests/github_operations/test_pr_manager_feedback.py:441` — low — the routing test calls `fetch_conversation_comments` directly; via the public `get_pr_feedback` the exception is captured into `unavailable["comments"]`, so the guard is not observable through the public API and that swallow path is untested.
**Decisions**:
Verdict(decision='tasks', tasks=['Add tests asserting the cross-repo guard raises before the underlying GitHub write is attempted for the currently untested routed call sites: all 4 sites in src/mcp_workspace/github_operations/issues/comments_mixin.py (including add_comment at line 83), the site in events_mixin.py, and the site in branch_manager.py. Each test must fail if the routing guard is reverted (e.g. assert the exception type/message and assert the underlying client method such as create_comment was never called), not merely pass against a mock.', 'Replace the six blanket per-file DOC502 waivers added in pyproject.toml:120 with per-function `# noqa: DOC502` comments on the specific routed methods that need them (including in manager.py and labels_mixin.py), so DOC502 stays active for the rest of each module.', 'Add a test that exercises the cross-repo guard through the public API in tests/github_operations/test_pr_manager_feedback.py: call get_pr_feedback (not fetch_conversation_comments directly) and assert the guard\'s exception is surfaced as unavailable["comments"] with the expected reason, covering the currently untested swallow path.'], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-08-28
**Findings**:
I'll gather context first.NO FINDINGS
**Decisions**:
Verdict(decision='dismiss', tasks=[], escalate_reason=None)
**Changes**:
dismiss
