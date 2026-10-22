# review-plan review log 1

## Round 1 — 2026-10-22
**Findings**:
Plan files and issue are read; checking a few code facts the plan depends on before I write the report.pr_info/steps/step_5.md:95 — high — The test can't pass: `truncate_output` keeps the first `max_lines` lines, which with `max_lines=4` are heading, blank, State, summary. `Linked branches` is line 5, so it gets cut. The issue only requires the summary line to survive. Change the test to: summary present, `Linked branches` truncated.
pr_info/steps/step_5.md:49 — medium — "both survive any `max_lines >= 4`" is wrong once the summary line exists. The issue says `Linked branches` moves to line 5, so it needs `max_lines >= 5`. The comment at formatters.py ~135 should say this, or the implementer may reorder lines to make the step_5.md:95 test pass, putting the summary after `Linked branches`.
pr_info/steps/step_6.md:19 — medium — Only `test_formatters.py` fixtures are told to carry an association. The existing `MagicMock` search items and sub-issue children in `test_github_search_tool.py` and `test_github_write_tools_subissues.py` normalise to `None`, which means untrusted. Every existing row assertion there would then gain `[untrusted @…]` and fail. Tell the step to set `author_association="OWNER"` on those existing mocks.
pr_info/steps/step_2.md:17 — low — The test location is left open ("e.g. … or a test module for `types.py` if one exists"). Planning principles want tests to mirror src, so name `tests/github_operations/issues/test_types.py` for the `issue_to_data` / `create_empty_issue_data` tests.
**Decisions**:
Verdict(decision='tasks', tasks=['pr_info/steps/step_5.md:95 — Rewrite the max_lines=4 truncation test. It should assert that the summary line survives and that `Linked branches` (now line 5) is truncated. It should not expect both to survive.', 'pr_info/steps/step_5.md:49 — Correct the claim "both survive any `max_lines >= 4`". The summary line keeps its place before `Linked branches`, and `Linked branches` needs `max_lines >= 5` to survive. Have the comment near formatters.py ~135 say this, and state that lines must not be reordered to satisfy the test.', 'pr_info/steps/step_6.md:19 — Add `author_association="OWNER"` to the existing MagicMock search items in `test_github_search_tool.py` and to the sub-issue children in `test_github_write_tools_subissues.py`. Without it, their existing row assertions will fail once untrusted labelling is added.', 'pr_info/steps/step_2.md:17 — Put the `issue_to_data` / `create_empty_issue_data` tests in `tests/github_operations/issues/test_types.py`, so the test location mirrors src.'], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-10-22
**Findings**:
Plan files and issue read; now verifying a few code facts the plan depends on (config import layering, `_malformed_first_line`).pr_info/steps/step_4.md:103 — medium — The allowlist-laziness test is vacuous as written. `allowlist()` is only called for untrusted authors whose body has a `### Base Branch` section, so three untrusted issues without one give zero reads and "at most once" passes even if the per-call cache is missing. Require all three bodies to contain a valid section, mock `fetch_body_editor`, and assert exactly one read.
**Decisions**:
Verdict(decision='tasks', tasks=['pr_info/steps/step_4.md:103 — Change the allowlist-laziness test so it can fail. Give all three untrusted issue bodies a valid `### Base Branch` section and mock `fetch_body_editor`. Then assert the allowlist is read exactly once, not "at most once".'], escalate_reason=None)
**Changes**:
applied
