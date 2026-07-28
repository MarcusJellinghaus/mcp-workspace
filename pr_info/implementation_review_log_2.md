# review-implementation review log 2

Issue #236 — Branch status: missing-token degradation + opt-in fail-on-reviews.

Supervisor run {n}=2. Rounds appended below.

## Round 1 — 2026-07-28
**Findings** (from `/implementation_review`; all checks green, 1881 passed/2 skipped):
- MEDIUM — partial-PR-feedback fail-open: `collect_pr_feedback` drops the `unavailable` signal from `get_pr_feedback`, so when a blocking-relevant source (`threads`/`alerts`) degrades gracefully (token present, CI PASSED, no exception), the review gate renders `Review Gate: clean` despite undeterminable review state — the exact fail-open the three-state design forbids.
- LOW — `_review_gate_header` always renders `(no token)` for every UNKNOWN cause, even when a token is present (CI `UNKNOWN` collection-failure / branch-undeterminable), contradicting commit 67848f2's neutral CI-line intent.
- LOW — stale `branch_status_rendering.py` module docstring claiming `branch_status` re-exports symbols for backward compat (shim removed in prior round).
- (Prior-round fixes confirmed in place: branch-undeterminable → UNKNOWN, shim removed, catch-all handler → UNKNOWN.)

**Decisions**:
- MEDIUM (fail-open): **ACCEPT** — escalated to user (spec self-contradiction: design guarantee "never clean on collection failure" vs Decision #1 "feedback keeps current fallbacks / CI-only"). User chose the solid fix. Reads as scope-refinement, not scope-creep: the guarantee names "collection failure" verbatim, and this is the review-blocking data itself failing.
- LOW (parenthetical): **ACCEPT** — folded into the fix; render `(no token)` only for genuine no-token (`UNAVAILABLE`), else `(undeterminable)`. Keeps the header truthful now that token-present UNKNOWN causes exist. Contract note: #1068's merge-gate parser should match the `UNKNOWN` verdict token, not the exact parenthetical.
- LOW (docstring): **ACCEPT** — trivial Boy Scout fix.

**Changes**:
- `pr_feedback.py`: `_BLOCKING_RELEVANT_SECTIONS = {"threads","alerts"}`; `collect_pr_feedback` returns `(text, blocks_merge, undeterminable)`; total-failure path fails closed `(None, False, True)`.
- `branch_status.py`: new `BranchStatusReport.pr_feedback_undeterminable: bool = False`, threaded from the collect call site (False when no PR).
- `branch_status_rendering.py`: `_review_gate_header` truthful parenthetical + `pr_feedback_undeterminable` as UNKNOWN trigger; docstring corrected.
- Tests: `test_branch_status_review_gate.py`, `test_branch_status_pr_feedback.py`, `test_branch_status.py` (updated token-present assertions + new undeterminable coverage).

**Status**: pylint/mypy clean, pytest 1881 passed/2 skipped, format applied. Committed via commit agent (see below).

Round 1 commit: `62a3a92` (fix(branch-status): close partial-PR-feedback fail-open in review gate).

## Round 2 — 2026-07-28
**Findings** (follow-up `/implementation_review` on HEAD 62a3a92; all checks green, 1881 passed/2 skipped; round-1 fixes verified correct):
- MEDIUM — sibling PR-lookup fail-open: `_collect_pr_info` returns `pr_found=None` on lookup/manager-init failure (distinct from `False` = confirmed no PR), but step 10's `else` sets `pr_feedback_undeterminable=False` for both, so a PR-lookup failure with gate on + CI PASSED/NOT_CONFIGURED renders `Review Gate: clean` despite undeterminable review state.
- LOW — `_collect_ci_status` outer `except` maps CI-fetch exceptions to `NOT_CONFIGURED` (clean-eligible), a second fail-open avenue.
- LOW — no end-to-end test asserts step-10 threads `collect_pr_feedback`'s undeterminable into `report.pr_feedback_undeterminable`.

**Decisions**:
- MEDIUM (PR-lookup fail-open): **ACCEPT** — same fail-open class already approved; fix is `pr_feedback_undeterminable = pr_found is None` (gate-only, pure-additive preserved; `pr_found is False` stays clean-eligible). No re-escalation — applies the principle the user already set.
- LOW (CI-exception → NOT_CONFIGURED): **SKIP** — pre-existing (the `except` predates this issue); fixing it (`→ UNKNOWN`) would change the token-present, gate-OFF CI line/recommendation, breaking the pure-additive guarantee, and conflates "no CI" with "fetch failed." Noted for a possible follow-up.
- LOW (test gap): **ACCEPT** — folded into the MEDIUM's end-to-end test.

**Changes**:
- `branch_status.py` step 10 `else`: `pr_feedback_undeterminable = pr_found is None` (+ explanatory comment).
- Tests: end-to-end `collect_branch_status` coverage for lookup-failure (`pr_found is None` → undeterminable True) and confirmed-no-PR (`False` → undeterminable False).

**Status**: committed via commit agent (see below).

Round 2 commit: `72f2e00` (fix(branch-status): close PR-lookup-failure fail-open in review gate).

## Round 3 — 2026-07-28
**Findings**: None. Follow-up `/implementation_review` on HEAD 72f2e00 verified the round-2 fix correct and complete; every in-scope undeterminable avenue (missing token, whole-report collection failure, branch-undeterminable, partial PR-feedback section, PR-lookup failure) maps to an UNKNOWN trigger; pure-additive preserved; tri-state resolved at one boundary; tests complete. Branch green (pylint/mypy clean, pytest 1883 passed/2 skipped).
**Decisions**: Loop ends — zero code changes this round.
**Status**: no changes needed.

## Final Status

**Rounds run**: 3 (2 with code changes, round 3 clean).

**Commits produced this run**:
- `62a3a92` — fix(branch-status): close partial-PR-feedback fail-open in review gate (Round 1)
- `72f2e00` — fix(branch-status): close PR-lookup-failure fail-open in review gate (Round 2)
- `chore(vulture)` — whitelist issue #236 review-gate test fixtures (post-loop step 8)

**Post-loop checks (supervisor)**:
- `run_lint_imports_check`: PASSED — 9 contracts kept, 0 broken (no architecture/import-contract violations).
- `run_vulture_check`: clean after whitelisting three autouse pytest fixtures (`_github_token`, `_reset_global`, `_setup`) — all false positives.

**Net review outcome**: The three-state review-gate design guarantee ("never render `clean` when review state is undeterminable") is now closed on all in-scope avenues. One fail-open avenue — `_collect_ci_status`'s outer `except → NOT_CONFIGURED` — is deliberately left as-is: it is pre-existing and fixing it would break the issue's pure-additive guarantee (it would change the token-present, gate-OFF CI line/recommendation). Recommend a separate follow-up issue if that path matters.

**Contract note for mcp-coder #1068**: the review-gate parser should key on the `UNKNOWN` verdict token, not the exact parenthetical — `UNKNOWN (no token)` (genuine missing token) and `UNKNOWN (undeterminable)` (token present, state undeterminable) are both non-mergeable UNKNOWN states.
