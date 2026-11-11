# review-implementation review log 1

## Round 1 — 2026-11-11
**Findings**:
Diff collected; now checking the security path rules for `body_file` against `save_file`, plus the git helpers.Implementation and round-trip tests check out; last check is the rewritten legacy CRLF tests.`tests/github_operations/test_github_issue_view_body_file.py:34` — low — The tests for `check_body_target`, `save_body` (in `src/mcp_workspace/toolset/_github_write_helpers.py`) and the `github_issue_view` `body_file` behaviour (in `src/mcp_workspace/toolset/github_read.py`) are under `tests/github_operations/`. They should be under `tests/toolset/`, because `planning_principles.md` says tests mirror the src structure.
**Decisions**:
Verdict(decision='tasks', tasks=["Move tests/github_operations/test_github_issue_view_body_file.py to tests/toolset/ so tests mirror the src structure. The tests for check_body_target, save_body (src/mcp_workspace/toolset/_github_write_helpers.py) and github_issue_view body_file (src/mcp_workspace/toolset/github_read.py) belong there. If the file also tests format_issue_view's body_note (src/mcp_workspace/github_operations), leave those tests under tests/github_operations/. Update any imports or fixtures that depend on the file's location, then re-run pytest."], escalate_reason=None)
**Changes**:
applied
