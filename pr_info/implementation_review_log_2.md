# review-implementation review log 2

Issue #250 — GraphQL errors render as a bare "GithubException 400" with the reason discarded.

Continues from `implementation_review_log_1.md` (4 rounds, ended on a rebase handoff).

## Round 1 — 2026-08-30

**Findings**:
- `src/mcp_workspace/server.py:37-39` — high — out-of-scope import reformat (single-name import
  expanded to a parenthesized block) failing CI's isort job. Raised as low in log 1 rounds 1 and 3
  and dismissed twice; re-raised because the predicted CI churn had now materialised as a hard
  build failure.
- `src/mcp_workspace/github_operations/exception_renderer.py:55-60` — low — a GraphQL error
  carrying a `type` but no `message` (e.g. `{"type": "RATE_LIMITED"}`) was dropped by
  `extract_graphql_errors`, so the GraphQL arm was skipped and the renderer emitted a bare
  `GithubException 400` — issue #250's reported symptom verbatim, with a known error type
  discarded. Inconsistent with `_has_permanent_error`, which log 1 round 1 re-keyed to the raw
  `errors` list for exactly this reason.

**Decisions**:
- Accept (server.py) — unrelated to #250 and breaking the build. Revert to `main`'s form.
- Accept (renderer) — borderline. The issue's Decisions row sanctions falling through for
  *unparseable* `errors`, but a well-formed entry carrying only a `type` is not unparseable; it
  reproduces the exact symptom the issue exists to eliminate, and contradicts the retry
  classifier. Bounded fix.
- Deferred (process) — `Rebase=BEHIND` / `PR=NOT_FOUND` carried to the completion message.

**Changes**:
- Rebased onto `origin/main` — 13 commits, zero conflicts, force-pushed (`b6dc0f3...2ae1eb2`).
  This settles the "could not be rebased cleanly" handoff on the issue. The rebase did **not**
  absorb the isort churn: it was branch-local, not a divergence from main, so it needed a direct
  revert. `git diff origin/main -- src/mcp_workspace/server.py` is now empty.
- Verified the isort failure was not environment drift — local and CI both resolve isort 9.0.1,
  so `run_format_code` had simply not been run after that import was reformatted.
- `_diagnostics.py` — `_usable_str` helper; return type widened to
  `list[tuple[str | None, str | None]]`; an entry is kept when *either* field is usable.
- `exception_renderer.py` — `label` split so a `None` message renders the type alone
  (`GraphQL RATE_LIMITED`); `total`-based `(+N more)` and the per-message 200-char cap preserved.
- `_pr_feedback_sources.py` — docstrings re-worded; the old rationale for `_has_permanent_error`
  reading the raw `errors` cited parser behaviour that no longer exists.
- Tests — three renderer cases (type-only renders the type, mixed entries, neither-usable falls
  through to REST), extended `test_message_less_permanent_error_not_retried` to assert the
  rendered string, new `TestExtractGraphqlErrors` cases,
  `test_unparseable_entries_are_still_counted` adjusted `(+3 more)` → `(+2 more)`.
- `pr_info/steps/{summary,step_1,step_2,step_4}.md` — corrected statements the new parser
  semantics falsified: the "two consumers" claim (the retry classifier no longer uses the
  parser), the dead `{"type": "OTHER"}` dropped-entry example, retry pseudo-code still calling
  `extract_graphql_errors`, and the helper signature/render pseudo-code missing `str | None` and
  `total`.

**Checks**: pylint clean; pytest 2171 passed / 2 skipped (`-n auto`) and 381 passed / 1 skipped
(`git_integration`); mypy clean; ruff clean; `run_format_code` no changes.

**Status**: committed

## Round 2 — 2026-08-30

**Findings**:
- `src/mcp_workspace/github_operations/pr_manager.py:658-660` — low — the explicit WARNING log is
  the only remaining carrier of the HTTP status and the raw GraphQL body once the renderer drops
  the synthetic status (issue #250's "WARNING log for GraphQL errors" decision row and its "the
  number stays reachable in the WARNING log" constraint). Its test
  (`test_pr_manager_feedback.py:929`) asserted only the prefix
  `"Failed to fetch review data for PR #42"`, so deleting `{review_error}` from the f-string
  would leave the test green while silently falsifying that constraint.

**Decisions**:
- Accept — test-only, one bounded change, and it guards a documented Decisions-table invariant
  that nothing else pins.

**Changes**:
- `tests/github_operations/test_pr_manager_feedback.py` — `test_returned_graphql_error_logged_at_warning`
  now also asserts `"400"`, `"FORBIDDEN"` and `"Resource not accessible"` appear in `caplog.text`.
  The values come from the fixture the test already builds
  (`_null_pr_body({"type": "FORBIDDEN", "message": "Resource not accessible"})` →
  `createException(400, ...)`); substring checks, so rewording the prefix will not break them.
- Mutation-verified: reducing the log to `f"Failed to fetch review data for PR #{pr_number}"`
  makes the test fail (`assert '400' in ...`), where the old prefix-only assertion passed.
  `pr_manager.py` restored verbatim — `git diff` on it is empty. No source files changed.

**Checks**: pylint clean; pytest 381 passed / 1 skipped (`git_integration`, `-n auto`); mypy
clean; ruff clean; `run_format_code` no changes.

**Status**: committed

## Round 3 — 2026-08-30

**Findings**: NO FINDINGS

**Decisions**: none — loop terminates on a round with zero code changes.

**Changes**: none.

**Status**: no changes needed

The reviewer re-checked the blast radius of both prior rounds rather than re-auditing settled
ground: `extract_graphql_errors`'s widened return type cannot reach `_has_permanent_error` or
`_build_graphql_exception` (both key on the raw `errors` list, one consumer only); the dispatch
guard still separates GraphQL from REST 422 bodies; `extra = total - len(parts)` stays honest
after the `message is None` early-`continue`; and `server.py` remains byte-identical to
`origin/main`.

Items explicitly considered and left below the bar, recorded so a future round need not re-derive
them: `err_type` is interpolated without whitespace-collapsing or capping (GraphQL `type` is an
enum-like token that cannot carry a newline, and the code predates round 1); a non-dict
`requestJsonAndCheck` result would `AttributeError` at `_pr_feedback_sources.py:151` (not
reachable — the GraphQL endpoint always answers with a JSON object); the WARNING log json-dumps
the whole recovered body (explicitly sanctioned by the issue's constraint);
`test_mixed_valid_and_invalid_entries_returns_only_valid` now also returns a type-only pair, so
its name reads slightly stale (naming only).

## Final Status

**Rounds run**: 3 (this log) — following 4 rounds in `implementation_review_log_1.md`.

**Commits produced**:
- `c4e8553` — `fix(github_operations): render GraphQL errors carrying only a type`
- `d779f05` — `test(github_operations): pin GraphQL error detail in WARNING log`

Plus a clean rebase onto `origin/main` (13 commits, zero conflicts, force-pushed
`b6dc0f3...2ae1eb2`), which resolved the outstanding "could not be rebased cleanly" handoff
recorded on the issue.

**Supervisor checks**:
- `run_vulture_check` — no output (no unused code).
- `run_lint_imports_check` — PASSED, 9 contracts kept / 0 broken across 249 files and 1145
  dependencies, including Layered Architecture and PyGithub Library Isolation.

**Quality gates**: pylint clean; pytest 2171 passed / 2 skipped (`-n auto`) and 381 passed /
1 skipped (`git_integration`); mypy clean; ruff clean; `run_format_code` no changes.

**Branch status**: CI=PASSED, Rebase=UP_TO_DATE, Tasks=COMPLETE (all 4), label
`status-07:code-review`. `PR=NOT_FOUND` — no pull request has been opened yet; that is a separate
tracker task outside this skill's scope.

**Open issues**: none.
