# review-plan review log 1

## Round 1 — 2026-11-03
**Findings**:
Checking `to_git_paths` behaviour to confirm the test setups in the plan are valid.pr_info/steps/step_2.md:41 — medium — Plan says to put `"renormalize_paths"` after `"reset_hard"` in `__all__`, but `"ren"` sorts before `"res"`. It belongs between `"rebase_start"` and `"reset_hard"`. As written, `test_all_remains_alphabetised` fails.
pr_info/steps/summary.md:47 — medium — The acceptance criterion "both helpers importable … from `mcp_workspace.git_operations`" has no test of its own. `test_init_exports.py` only checks the count (68→70) and runs `hasattr` over `__all__`, so it never asserts that `renormalize_paths` and `is_staged_diff_cr_only` are the names added. Steps 2 and 3 should add a name-specific assertion, like the existing `test_verify_git_and_check_result_exported`.
pr_info/steps/step_2.md:88 — low — The release-note section uses `### New functions` and has no `### Summary` heading. `docs/release-notes.md` uses `### Summary` and `### New API` (step_3.md:77 has the same mismatch).
**Decisions**:
Verdict(decision='tasks', tasks=['In pr_info/steps/step_2.md:41, put "renormalize_paths" between "rebase_start" and "reset_hard" in the `__all__` placement instruction ("ren" sorts before "res"). As written, test_all_remains_alphabetised fails.', 'In pr_info/steps/step_2.md and pr_info/steps/step_3.md, add a test to tests/.../test_init_exports.py that checks `renormalize_paths` (step 2) and `is_staged_diff_cr_only` (step 3) by name. Each should be importable from `mcp_workspace.git_operations` and listed in `__all__`. Follow the pattern of the existing test_verify_git_and_check_result_exported.'], escalate_reason=None)
**Changes**:
applied
