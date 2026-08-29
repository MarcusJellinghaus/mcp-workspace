# Implementation review log 2

Issue: [#255](https://github.com/MarcusJellinghaus/mcp-workspace/issues/255) — GitHub read tools: support reference projects for cross-repo reads

Branch: `255-github-read-tools-support-reference-projects-for-cross-repo-reads`

Supervised review run 2. Run 1 is in [implementation_review_log_1.md](./implementation_review_log_1.md);
its round 3 produced no code changes and was interrupted by a rebase hand-off.

## Round 1 — 2026-08-29

**Findings** (no critical issues; pytest 1917 passed / 15 skipped, mypy clean, pylint clean, vulture clean, lint-imports 9/9 kept):

- `tests/LLM_Test.md:144` — low — the smoke-test script uses `reference_name=<name>` but never tells the tester where `<name>` comes from.
- `docs/ARCHITECTURE.md:79` — low — §4 says lazy `github_operations` imports live "inside the relevant `@mcp.tool()` bodies"; the `IssueManager` import now lives in the private `_issue_manager()` helper.
- `src/mcp_workspace/server.py:625` vs `:639` — low — the same `protected-access` suppression written two ways within a few lines.
- `README.md:226` — low — the new Available Tools row names a category where every other row names one tool.
- `src/mcp_workspace/server.py:740` — low, speculative — a missing PR still surfaces a raw PyGithub 404 without naming the repository, unlike a missing issue.

**Decisions**:

- Accept the first four. All are wording or consistency defects this branch introduced, in documentation surfaces decision 5 puts in scope.
- Skip the `github_pr_view` 404 asymmetry: decision 4 scopes the diagnostic to "Could not access repository", and that path already reports correctly. Only a genuinely absent PR number is affected — speculative per the knowledge base.
- Round-3 dismissals from run 1 stay dismissed. `pr_info/steps/summary.md` staleness skipped — the knowledge base treats `pr_info/` as deleted later.

**Changes**:

- `tests/LLM_Test.md` — step 7 now says to pick a reference project from `get_reference_projects()` and to skip steps 8-10 when the count is 0 or the project has no URL.
- `docs/ARCHITECTURE.md` — the lazy-import bullet now covers tool bodies "and the private helpers they call".
- `src/mcp_workspace/server.py` — `_repo_access_error` uses the trailing suppression form, with the attribute access bound to a local to stay inside 88 columns. Both helpers are branch-introduced, so no pre-existing code was touched.
- `README.md` — the four GitHub read tools had no rows of their own, so the category row became four tool rows.

**Note**: `tests/test_startup_performance.py::test_server_startup_under_two_seconds` fails on this machine (2.4-4.3s across runs, serially as well as under `-n auto`). Not attributed to this branch: the assertions guarding against eager `github`/`git` imports pass, and the only module-level import added is under `TYPE_CHECKING`. Left for CI to confirm.

**Status**: committed
