# plan-review-supervisor log 2 — issue #327

Continuation of `plan_review_log_1.md`, which ended Round 2 in `escalate`:
the `on_error` signature is contradictory across the plan (issue #327 locks it
single-arg `Callable[[BaseException], None]`; step_1.md's own tests and
step_3.md's `_set_lookup_error(e, data)` require two-arg).

## Round 1 — 2026-10-20
**Findings**:
- F1 (design) — `on_error` arity contradiction still present (re-escalation of log_1 round 2): issue #327's Decision table said single-arg `Callable[[BaseException], None]`, but step_1.md's own tests and step_3.md's `_set_lookup_error(e, data)` require two-arg `(exception, resolved)`.
- F2 (mechanical) — duplicate error-message-formatting logic independently spelled out in step_2.md (`_get_repository`) and step_3.md (`_set_lookup_error`).
- F3 (mechanical) — step_3.md never notes that `ci_results_manager.py` needs a new `GithubException` import.
- F4 (mechanical) — issue point 4 ("update the `# type: ignore[typeddict-item]` comments") left unaddressed on paper, even though the existing comments are unrelated to this change and correctly need no edit.

**Decisions**:
- F1 — escalate to user (design/requirements call).
- F2, F3, F4 — accept, straightforward plan edits, folded into the same `/plan_update` pass as F1.

**User decisions**:
- Asked user to choose between Option A (keep `on_error` single-arg per the issue's literal wording, by reordering the decorator to call `on_error(e)` before resolving `default_return` and stashing the cause on an instance attribute) vs. Option B (make `on_error` two-arg `(e, resolved)`, matching what step_1's tests and step_3's `_set_lookup_error` already assumed, correcting the issue's Decision-table row to match).
- User initially chose A. Before implementing, verified decorator mechanics in `base_manager.py` and found Option A isn't truly single-arg either — a module-level `on_error` fixed at class-decoration time has no way to reach `self` without also being passed it, and the issue's own "Proposed change" point 2 text ("so it can mutate the resolved value in place") already assumes two-arg, contradicting only the Decision-table's shorthand. Reported this back; user said "Okay, go on" — confirming Option B.

**Changes**:
- Edited GitHub issue #327: Decision table row and "Proposed change" point 2 corrected to `Callable[[BaseException, T], None]`, called with the exception and the resolved value.
- `pr_info/steps/summary.md` — point 1 corrected to two-arg `on_error`; noted the shared `_format_error_message` helper.
- `pr_info/steps/step_1.md` — WHAT/ALGORITHM/DATA changed from single-arg `on_error(e)` to two-arg `on_error(e, resolved)`, now consistent with its own tests.
- `pr_info/steps/step_2.md` — added new `_format_error_message(e: BaseException) -> str` helper in `base_manager.py`; `_get_repository()`'s two failure branches now call it instead of inlining the format.
- `pr_info/steps/step_3.md` — `_set_lookup_error` now delegates to `_format_error_message`; added note on the new `GithubException` import needed in `ci_results_manager.py`; added clarifying note that the `# type: ignore[typeddict-item]` comments need no change.
- New `pr_info/steps/Decisions.md` logging these four decisions.

**Status**: committed (see commit below)

## Round 2 — 2026-10-20
**Findings**:
- Two-arg `on_error` now consistent across issue, summary.md, step_1.md, step_3.md, Decisions.md.
- `_format_error_message` output matches every exact string asserted in step_2/step_3 tests.
- No collision with the 39 existing `_handle_github_errors` call sites (all pass only `default_return`).
- Generic typing `Callable[[BaseException, T], None]` unifies `T=CIStatusData` cleanly; covered by mypy gate.
- Referenced test classes exist; new `TestLastRepositoryError` correct (existing `TestGetRepositoryDebugLogging` is a different concern).
- `GithubException` import via `base_manager` re-export is correct.
- Step granularity fine; Decisions.md accurate; type-ignore note closes issue point 4.
- Minor: summary.md point 4 restates the message extraction without the `isinstance(e.data, dict)` guard that step_2.md includes.
- Process: reviewer used native `Read` once without justification (self-reported).

**Decisions**:
- summary.md `isinstance` omission — skip: cosmetic, step_2.md is the authoritative spec and is correct.
- All other findings — no issue.

**User decisions**: none

**Changes**: none

**Status**: no changes needed

## Final Status
- Rounds: 2. Round 1 resolved the escalated `on_error` arity contradiction (two-arg, issue #327 corrected) plus three mechanical fixes; round 2 found no further changes.
- Commits: `2eaaa7b` (plan update), plus this log.
- Plan is ready for approval.
