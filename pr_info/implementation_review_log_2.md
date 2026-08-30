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
