# review-plan review log 1

## Round 1 — 2026-09-01
**Findings**:
I'll gather context first — knowledge base, the issue tree, and the plan files.`pr_info/steps/step_1.md:229` — high — Plan moves only four validation-message assertions to `test_search.py`; the issue's Decisions row ("Validation-error tests") requires all five, so `f"Invalid state: {state}. Expected 'open', 'closed' or 'all'."` gets no unit-level assertion. Its only coverage stays `test_github_search_invalid_state`, which passes `state="bogus"` (already lower-case), so a regression that interpolated the normalized state instead of the original would pass every test while the DATA block at `step_1.md:150-154` calls that distinction out explicitly.

`pr_info/steps/step_1.md:264` — medium — Plan declines any assertion on `needs_type_default` / `has_inline_state`, contradicting the issue's "Flag computation" decision, whose stated reason for making them public fields is that they are "directly assertable in the pure tests". As planned, the two fields are public with no reader outside `to_query`; either add the direct assertions or record that the rationale is superseded.

`pr_info/steps/step_1.md:241` — medium — The parametrized validation test specifies one real parameter tuple; the other three cases (blank labels, whitespace assignees, `type:pull-request`) exist only as prose comments without their `query` values or literal tuples. Since the binding invariant is byte-identical messages with per-case `{label!r}` / `{assignee!r}` interpolation, the implementer must reconstruct the data the step file is supposed to supply.

`pr_info/steps/step_1.md:217` — low — Mapping row for `test_github_search_state_all_emits_no_token` omits its `search_issues.assert_called_once()` assertion (`test_github_search_tool.py:280`), which has no equivalent at `SearchSpec` level; the table implies the test moves verbatim minus nothing.
**Decisions**:
Verdict(decision='tasks', tasks=['In pr_info/steps/step_1.md around line 229, add the fifth validation-message assertion to the test_search.py migration list: assert the invalid-state message is f"Invalid state: {state}. Expected \'open\', \'closed\' or \'all\'." using a mixed-case input (e.g. state="Bogus") so the test pins interpolation of the original string rather than the normalized one, matching the DATA block at step_1.md:150-154.', "In pr_info/steps/step_1.md around line 264, either specify direct assertions on the public SearchSpec fields needs_type_default and has_inline_state as required by the issue's 'Flag computation' decision, or record explicitly in the step file that the rationale for making them public is superseded and change them to non-public.", 'In pr_info/steps/step_1.md around line 241, replace the prose comments for the remaining three parametrized validation cases (blank labels, whitespace assignees, type:pull-request) with their literal parameter tuples, including the query value and the exact expected message with per-case {label!r} / {assignee!r} interpolation.'], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-09-01
**Findings**:
I'll gather context first.`pr_info/steps/step_1.md:165` — medium — Replacement range contradicts the replacement snippet: the range is stated as lines 1059–1128 ("down to and including the `kwargs: Dict[str, str] = {...}` assignment", which is line 1128), but the snippet that follows also contains the `if sort:` / `if order:` blocks that live at `server.py:1129-1132`, and line 186 declares the unchanged region as starting at the `# pylint: disable=protected-access` line (1133). Followed literally this duplicates the sort/order blocks; no configured check (pylint W/C/R disabled, ruff D/DOC only, vulture) would flag the duplication. Range should read 1059–1132.

`pr_info/steps/step_1.md:287` — medium — The literal test signature `def test_from_arguments_rejects_invalid_input(kwargs: dict, message: str)` uses a bare generic. mypy runs `strict = true` and the `tests.*` override only disables `unreachable`/`union-attr`, so `disallow_any_generics` applies and this fails with "Missing type parameters for generic type dict"; no existing test file uses a bare `dict` annotation. Needs `dict[str, Any]` (or an explicit TypedDict/`dict[str, object]`).
**Decisions**:
Verdict(decision='tasks', tasks=["In pr_info/steps/step_1.md around line 165, correct the replacement range to lines 1059-1132 so it covers the `if sort:` / `if order:` blocks that appear in the replacement snippet, keeping it consistent with line 186's statement that the unchanged region starts at the `# pylint: disable=protected-access` line (1133).", "In pr_info/steps/step_1.md around line 287, change the parametrized test signature to use a parameterized generic, e.g. `def test_from_arguments_rejects_invalid_input(kwargs: dict[str, Any], message: str)` (adding the `Any` import), so it satisfies mypy strict's disallow_any_generics."], escalate_reason=None)
**Changes**:
applied

## Round 3 — 2026-09-01
**Findings**:
I'll gather context first.`NO FINDINGS`
**Decisions**:
Verdict(decision='dismiss', tasks=[], escalate_reason=None)
**Changes**:
dismiss
