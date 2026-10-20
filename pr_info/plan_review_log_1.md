# review-plan review log 1

## Round 1 — 2026-10-20
**Findings**:
I'll read the knowledge base files, issue #327, and the plan steps in parallel.Findings:

pr_info/steps/summary.md:13 — medium — `on_error` is specified as a two-arg callable `Callable[[BaseException, T], None]` called with `(exception, resolved)`, but issue #327's locked Decision table fixes the signature as `Callable[[BaseException], None]` (single arg). The plan silently changes a decided API contract without flagging/justifying the deviation anywhere in the plan.

pr_info/steps/step_1.md:21 — low — internal inconsistency: the `WHAT` code sample types `on_error` as `Callable[[BaseException, Any], None]`, while line 51's `DATA` section types the same parameter as `Callable[[BaseException, T], None]`. Pick one before implementation.

pr_info/steps/step_1.md:51 — medium — same two-arg vs issue's single-arg `on_error` signature mismatch as summary.md:13 (duplicate root cause, listed separately since it's the implementing step).
**Decisions**:
Verdict(decision='tasks', tasks=["In pr_info/steps/summary.md:13, change the on_error signature from Callable[[BaseException, T], None] (called with (exception, resolved)) to the single-arg Callable[[BaseException], None] fixed by issue #327's locked Decision table, and update any call-site description to match (call with just the exception).", "In pr_info/steps/step_1.md, fix both the WHAT code sample (line 21, currently Callable[[BaseException, Any], None]) and the DATA section (line 51, currently Callable[[BaseException, T], None]) to consistently use the single-arg Callable[[BaseException], None] signature mandated by issue #327, and update any invocation code/examples that currently pass a second 'resolved' argument."], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-10-20
**Findings**:
I'll load the needed MCP tool schemas, then gather the knowledge base, issue context, and plan files.Good, confirms current code matches plan's "WHERE" assumptions. Let me check the actual `_handle_github_errors` body (the except branches) to confirm the `cast(T, resolved)` pattern.Both referenced test classes exist as the plan assumes. That confirms the plan's test-location references are sound; the one substantive defect is the `on_error` signature contradiction.

## Findings

`pr_info/steps/step_1.md:21` — critical — `on_error: Optional[Callable[[BaseException], None]]` is declared single-argument, but step_1.md's own tests (lines 58-60, 67-68) require `on_error` to receive `(exception, resolved)` and mutate `resolved` in place — impossible with a one-arg callable. The ALGORITHM at line 42 (`on_error(e)`) calls it with only one argument, matching the type but not the tests.

`pr_info/steps/step_1.md:42` — critical — Same contradiction from the implementation side: `on_error(e)` passes only the exception, so `test_on_error_can_mutate_resolved_dict_in_place` (line 67) cannot pass — `on_error` has no reference to `resolved` to mutate.

`pr_info/steps/step_3.md:31` — critical — `_set_lookup_error(e: BaseException, data: CIStatusData) -> None` is a two-argument function, assigned as `on_error=_set_lookup_error` (line 48) into a parameter step 1 types and calls as one-argument. If step 1 is implemented as literally specified, step 3 either fails mypy (two-arg function assigned to one-arg `Callable` type) or fails at runtime (`on_error(e)` raises `TypeError: _set_lookup_error() missing 1 required positional argument: 'data'`) — the plan is not buildable across steps 1 and 3 as written. Fix: `on_error` must be typed and called as two-argument (`Callable[[BaseException, Any], None]`, called `on_error(e, resolved)`) in step 1; propagate that correction through step_1.md's WHAT/ALGORITHM/DATA sections.
**Decisions**:
Verdict(decision='escalate', tasks=[], escalate_reason="The on_error signature is now contradictory across the plan: issue #327 locks it as single-arg (Callable[[BaseException], None]), but step_1.md's own tests require it to receive and mutate `resolved` in place (two-arg), and step_3.md's `_set_lookup_error(e, data)` can only be wired in as two-arg — these can't all be satisfied without either revisiting the issue's locked decision or redesigning how the lookup failure gets attached to CIStatusData, which is a design call beyond mechanical editing.")
**Changes**:
escalate
**Escalate reason**: The on_error signature is now contradictory across the plan: issue #327 locks it as single-arg (Callable[[BaseException], None]), but step_1.md's own tests require it to receive and mutate `resolved` in place (two-arg), and step_3.md's `_set_lookup_error(e, data)` can only be wired in as two-arg — these can't all be satisfied without either revisiting the issue's locked decision or redesigning how the lookup failure gets attached to CIStatusData, which is a design call beyond mechanical editing.
