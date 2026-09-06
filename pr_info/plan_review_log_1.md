# review-plan review log 1

## Round 1 — 2026-09-06
**Findings**:
I'll gather context first.`pr_info/steps/step_3.md:5` — medium — Claims independence from step 1, but the drafted block (step_3.md:83, 98) documents the two 50-item caps that step 1 introduces; committing step 3 first ships README text describing behaviour the code does not yet have. Step 3 should be ordered after step 1 (summary.md:101-102 carries the same claim).

`pr_info/steps/summary.md:110` — medium — "Both caps are named constants" is listed as a *tested* criterion (copied from the issue), but none of the four planned tests references `_MAX_REPORT_VIOLATIONS` or `_MAX_STALE_ENTRIES` — all assert the literal `50`. Either import the constants in one assertion or move this criterion to "Verified in review".

`pr_info/steps/step_1.md:124` — low — "Add `List` to the `typing` import" is wrong about the target file: `tests/checks/test_file_sizes.py` has no `typing` import at all (lines 3-6 are `os`, `pathlib.Path`, `pytest`), so a new import line is needed.

`pr_info/steps/step_1.md:142` — low — `test_exactly_50_no_notice` does not specify `passed=False`; with the default the violations block never renders and the "all 100 items are listed" assertion fails. Cases 1 and 2 state `passed` explicitly; cases 3 and 4 do not.

`pr_info/steps/step_1.md:92` — low — The "unchanged output elements" list omits the `Violations:` header (`file_sizes.py:164`), which sits between the summary line and the item loop; it is neither in the unchanged list nor in the ALGORITHM pseudo-code at step_1.md:51-56.

`pr_info/steps/step_2.md:19` — low — Misreads #235 as a "first-line-terse" pattern. #235 is the opposite: it rewrites summary lines so capabilities documented only under `Args:` become visible at tool-selection time. The terse-first-line choice is the issue's own decision and should be cited as such, not as #235's pattern.
**Decisions**:
Verdict(decision='tasks', tasks=['In pr_info/steps/step_3.md:5 and summary.md:101-102, remove the claim that step 3 is independent of step 1 and reorder step 3 to run after step 1, since the drafted README block (step_3.md:83, 98) documents the two 50-item caps that step 1 introduces.', "Resolve the 'Both caps are named constants' criterion at pr_info/steps/summary.md:110: either change one planned test to import and assert against `_MAX_REPORT_VIOLATIONS` and `_MAX_STALE_ENTRIES` instead of the literal 50, or move the criterion out of the tested list into 'Verified in review'.", 'Correct pr_info/steps/step_1.md:124: tests/checks/test_file_sizes.py has no `typing` import, so the instruction must say to add a new `from typing import List` import line rather than extend an existing one.', "In pr_info/steps/step_1.md:142, specify `passed=False` for `test_exactly_50_no_notice` (and check case 4 likewise), so the violations block renders and the 'all items listed' assertion can hold."], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-09-06
**Findings**:
I'll gather context first.`pr_info/steps/step_1.md:106` — low — The W1309 justification for the string split does not hold in this repo: `pyproject.toml:141` sets pylint `disable = ["W", "C", "R"]` and ruff enables only `D`/`DOC` rules, so neither `f-string-without-interpolation` nor line length is enforced. The prescribed split is harmless, but the stated reason is wrong and may be copied into a code comment.

`pr_info/steps/step_1.md:104` — low — The note implies only the violations notice exceeds 88 chars; the stale notice (`lines.append(f"  ... showing {_MAX_STALE_ENTRIES} of {stale_count} stale entries")` at indent 8) is 90 chars and black wraps it onto its own line without any split, so the guidance is incomplete for one site and unnecessary for it at the same time.

`pr_info/steps/step_3.md:112` — low — "No test in this repo asserts on README content" is inaccurate: `tests/test_reference_projects_mcp_tools.py:69-80` asserts a README-quoted usage example. It does not cover the tool table, `#### List Directory`, or the new block, so step 3 is still test-free — but the blanket claim is wrong.
**Decisions**:
Verdict(decision='dismiss', tasks=[], escalate_reason=None)
**Changes**:
dismiss
