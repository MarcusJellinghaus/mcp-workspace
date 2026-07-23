# Plan Review Log — Issue #231

## Round 1 — 2026-07-23
**Findings**:
- A1: Inner try/except blocks left ambiguous in Step 1 (redundant vs. decorator @_handle_github_errors).
- A2: Step 1 verification asserted `assignees` on only one method's return.
- A3: `create_pull_request` docstring omits `assignees` (and possibly `mergeable_state`).
- B1: Failure paths (`{}`) vs empty-logins no-op distinguishability — matches approved decisions.
- B2: Empty-logins no-op still does one read API call — matches approved decision D2/D3 wording.
**Decisions**:
- A1: ACCEPTED — made inner try/except handling explicit in Step 1 (redundant-remove case applied). Verified against `pr_manager.py`: each inner `try/except GithubException` in `create_pull_request`, `get_pull_request`, and `close_pull_request` logs and returns `cast(PullRequestData, {})`, which is exactly the `default_return` the `@_handle_github_errors(lambda: cast(PullRequestData, {}))` decorator already produces for non-auth GithubExceptions. The inner block is redundant (and inconsistent with the mirrored `issues/manager.py`, which uses no inner try/except; it also masks 401/403 that the decorator is meant to re-raise). Step 1 now instructs deleting the inner try/except and returning `_pr_to_data(...)` directly.
- A2: ACCEPTED — broadened Step 1 verification to assert `assignees` across multiple routed sites (parameterized, or both `get_pull_request` and `list_pull_requests`).
- A3: ACCEPTED — added docstring update to Step 1. Verified against source: `create_pull_request`'s "Success response includes" list omits BOTH `assignees` and `mergeable_state`; Step 1 now adds both.
- B1: SKIP (no change) — recommended option matches already-approved issue decision; no scope/architecture impact.
- B2: SKIP (no change) — matches approved decision D2/D3; a read is not the write the issue excludes.
**User decisions**: None — all findings were straightforward improvements or confirmations of already-approved decisions; nothing escalated.
**Changes**: `pr_info/steps/step_1.md` only. (1) Added a new "Inner `try/except GithubException`" subsection under HOW documenting the redundant-remove verification and the explicit removal instruction for the 3 dict-returning methods. (2) Added WHAT item 4: docstring Boy-Scout instruction to add `assignees` and `mergeable_state` to `create_pull_request`'s "Success response includes" list. (3) Rewrote TDD-order item 3 to require asserting `assignees` on more than one routed method (`get_pull_request` and `list_pull_requests`). (4) Updated the LLM Prompt to cover all three refinements (inner try/except removal, docstring update, multi-site assertion). No other step files changed; scope and approved decisions unchanged.
**Status**: committed

## Round 2 — 2026-07-23
**Findings**:
- Re-review of the Round 1 edits (A1/A2/A3) for correctness, consistency, and regressions.
- A1 verified safe: for non-auth GithubExceptions the removed inner handlers returned `{}`, identical to the decorator default `@_handle_github_errors(lambda: cast(PullRequestData, {}))`. The only behavior change is 401/403 now re-raise instead of being swallowed — a deliberate, documented decision aligning pr_manager with issues/manager.py. No test regression (`test_github_api_error_returns_empty` uses a 404, still returns `{}`).
- A2 verified: Step 1 asserts `assignees` across `get_pull_request` and `list_pull_requests`.
- A3 verified: `create_pull_request` docstring omitted both `assignees` and `mergeable_state`; both now added.
- Noted (cosmetic, skipped): A1 scopes inner try/except removal to the 3 dict-returning methods only; `list_pull_requests` keeps its own inner handler (returns default `[]`, not part of A1's argument), so the `GithubException` import stays in use and Step 1's conditional "drop if unused" clause correctly won't fire.
**Decisions**: All Round 1 edits confirmed correct. No new findings requiring plan changes. Cosmetic note skipped (within Boy-Scout limits).
**User decisions**: None.
**Changes**: None — no plan files modified this round.
**Status**: no changes needed

## Final Status
- **Rounds run**: 2
- **Round 1**: applied 3 straightforward refinements to `pr_info/steps/step_1.md` (A1 explicit inner try/except removal, A2 broader assignees verification, A3 docstring fix). Committed as `76501d0`.
- **Round 2**: re-review confirmed the plan is internally consistent, faithful to the approved issue decisions, and correct. Zero plan changes.
- **Escalations to user**: none (B1/B2 were confirmations of already-/approve-d decisions, not open questions).
- **Result**: Plan is READY FOR APPROVAL.
