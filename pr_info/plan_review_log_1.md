# review-plan review log 1

## Round 1 — 2026-09-01
**Findings**:
I'll gather context first.`pr_info/steps/step_2.md:17` — critical — `"["` and `"[a-"` in the raise parametrization cannot fire: pathspec compiles an unterminated bracket expression to a literal `\[` regex with `include=True` (`GitIgnoreBasicPattern.__translate_segments` passes `range_error="literal"`, and the same "treat as literal" branch exists back to 0.12.1), so `regex is not None and p.include` is true and no `ValueError` is raised — the test as written fails. Unterminated classes belong with braces (literal chars that could name a real file), i.e. textual `glob_note` in step 3, not the raise.

`pr_info/steps/step_2.md:95` — critical — the stated contingency ("keep the same single condition and adjust which attribute it reads") is unactionable for `[` / `[a-`: no public `PathSpec` attribute distinguishes a literal-bracket pattern from a legitimately literal one, so the implementer is left with no exit from a failing step.

`pr_info/steps/summary.md:31` — high — the solution table repeats the same wrong premise ("unparseable → no usable compiled pattern"), so the error is baked into the artifact steps 2 and 3 are read against.

`pr_info/steps/step_1.md:11` — medium — WHERE puts all four tests in a new `TestSearchFilesGlobSemantics` class appended after `TestSearchFilesGlobOnly`, while HOW (line 33) requires the POSIX case test to sit directly beside `test_windows_case_insensitive_match_preserved`, which lives inside `TestSearchFilesGlobOnly` — the two placements are mutually exclusive.

`pr_info/steps/step_4.md:77` — medium — no step documents the new `glob_note` response key in any caller-visible description; step 4 updates only the `glob:` arg and `Raises:`, leaving the issue's own thesis (the reaching-the-caller docstring is what matters) unmet for the signal this PR adds.

`pr_info/steps/step_1.md:57` — low — the POSIX case test asserts `result["files"] == []`, contradicting the rule at line 46 that forbids exact assertions because the fixture copies `tests/testdata/`; it passes only incidentally, since that tree has no README.

`pr_info/steps/step_4.md:81` — low — `search_reference_files` gains a documented `ValueError` (plus a DOC502 ignore) with no test asserting the raise actually propagates through the async wrapper.
**Decisions**:
Verdict(decision='tasks', tasks=['step_2.md:17 — Remove "[" and "[a-" from the ValueError parametrization: pathspec compiles unterminated bracket expressions to a literal pattern with include=True, so no ValueError is raised and the test fails as written. Move those two patterns to the textual glob_note cases in step 3 alongside brace patterns.', "step_2.md:95 — Rewrite the contingency note so it no longer claims the fix is 'adjust which attribute the single condition reads'; state the actual fallback for literal-bracket patterns now that they are handled as glob_note cases rather than raises.", "summary.md:31 — Correct the solution table row that states 'unparseable → no usable compiled pattern' so it matches pathspec's actual literal-bracket behaviour, keeping steps 2 and 3 consistent with the corrected premise.", 'step_1.md:11 vs :33 — Resolve the contradictory test placement: pick one location for the POSIX case test (either inside TestSearchFilesGlobOnly next to test_windows_case_insensitive_match_preserved, or in the new TestSearchFilesGlobSemantics class) and make WHERE and HOW agree.', 'step_4.md:77 — Add a step (or extend step 4) that documents the new glob_note response key in the caller-visible tool description/docstring, not just the glob: argument and Raises: section.'], escalate_reason=None)
**Changes**:
applied
