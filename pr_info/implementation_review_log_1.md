# review-implementation review log 1

## Round 1 — 2026-11-11
**Findings**:
Diff collected; now checking the security path rules for `body_file` against `save_file`, plus the git helpers.Implementation and round-trip tests check out; last check is the rewritten legacy CRLF tests.`tests/github_operations/test_github_issue_view_body_file.py:34` — low — The tests for `check_body_target`, `save_body` (in `src/mcp_workspace/toolset/_github_write_helpers.py`) and the `github_issue_view` `body_file` behaviour (in `src/mcp_workspace/toolset/github_read.py`) are under `tests/github_operations/`. They should be under `tests/toolset/`, because `planning_principles.md` says tests mirror the src structure.
**Decisions**:
Verdict(decision='tasks', tasks=["Move tests/github_operations/test_github_issue_view_body_file.py to tests/toolset/ so tests mirror the src structure. The tests for check_body_target, save_body (src/mcp_workspace/toolset/_github_write_helpers.py) and github_issue_view body_file (src/mcp_workspace/toolset/github_read.py) belong there. If the file also tests format_issue_view's body_note (src/mcp_workspace/github_operations), leave those tests under tests/github_operations/. Update any imports or fixtures that depend on the file's location, then re-run pytest."], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-11-11
**Findings**:
Source diff reviewed; now checking the tests against the acceptance criteria.`src/mcp_workspace/toolset/github_read.py:117` — low — No test covers a failed `save_body` write, such as an `OSError` or a target that is read-only or locked. The issue requires that this case returns only `tool_error`, with no partial view. The code handles it through the outer `except`, but nothing guards that behaviour.
**Decisions**:
Verdict(decision='tasks', tasks=['Add a test for github_issue_view with body_file where save_body fails. Mock save_body (or the underlying write) to raise OSError, for example simulating a read-only or locked target. Assert that the tool returns only the tool_error, with no partial issue view in the output. This covers the failure path through the outer except at src/mcp_workspace/toolset/github_read.py:117.'], escalate_reason=None)
**Changes**:
applied

## Round 3 — 2026-11-11
**Findings**:
Source diff reviewed; checking whether `body_file` writes get the same path guards as `save_file` (e.g. `.git/` protection).Tests cover the acceptance criteria; a last look at the docs diff.NO FINDINGS
**Decisions**:
Verdict(decision='dismiss', tasks=[], escalate_reason=None)
**Changes**:
dismiss
