# review-plan review log 1

## Round 1 — 2026-11-25
**Findings**:
Now the knowledge base.`pr_info/steps/step_2.md:170` — high — Tells the automated step to run the full suite to find existing git-guard violations. Issue #417 says the full suite exceeds the 600 s LLM inactivity limit and is run interactively only. It is also unnecessary here: the git guard only affects unmarked tests, and all of those are in the unit group. Replace it with the unit-group run (`-m "not git_integration and not github_integration"`, `-n auto`).

`pr_info/steps/step_3.md:103` — high — "Then run the full suite (`-n auto`)" in an automated step contradicts the issue: the full suite (the only run covering `git_integration`/`github_integration`) is interactive. The plan should end the automated work at the unit-group run and serial performance run. It should name the interactive full-suite run as a remaining acceptance item, not an implementer action.

`pr_info/steps/step_1.md:184` — medium — The per-step Checks run plain `run_pytest_check(extra_args=["-n", "auto"])`, which is the whole suite including `git_integration` (addopts has no `-m`). Same 600 s problem as above. Use the unit-group marker expression in the Checks of every step (`step_2.md:178` and `step_3.md:107` too).

`pr_info/steps/step_1.md:184` — medium — No step runs `tests/test_guards.py` serially (`-n 0`), but acceptance requires the self-tests to pass serially in the dev environment (with `tach`/`textual-snapshot` installed). The `textual-snapshot` clobbering shows up only in a serial run. Add `run_pytest_check(extra_args=["-n", "0", "tests/test_guards.py"])` to the Checks of all three steps (`step_2.md:178`, `step_3.md:107`).

`pr_info/steps/step_2.md:21` — low — `test_is_git` has no `time_limit` marker. Acceptance says "Every guard self-test carries a `time_limit` marker with a reason". Give it one, or state that it applies only to pytester tests.
**Decisions**:
Verdict(decision='tasks', tasks=['pr_info/steps/step_2.md:170 — replace the full-suite run for finding existing git-guard violations with the unit-group run: run_pytest_check(markers expression "not git_integration and not github_integration", extra_args=["-n", "auto"]). Unmarked tests, the only ones the git guard affects, are all in the unit group.', 'pr_info/steps/step_3.md:103 — remove the implementer instruction \'Then run the full suite (-n auto)\'. End the automated work at the unit-group run (-m "not git_integration and not github_integration", -n auto) plus the serial performance run (markers=["performance"], -n 0). Add a note that the interactive full-suite run is a remaining acceptance item for a human, not an implementer action.', 'pr_info/steps/step_1.md:184, step_2.md:178, step_3.md:107 — change each step\'s Checks pytest call from plain run_pytest_check(extra_args=["-n", "auto"]) to the unit-group marker expression "not git_integration and not github_integration" with -n auto, so automated checks never run the git/github integration groups.', 'pr_info/steps/step_1.md:184, step_2.md:178, step_3.md:107 — add run_pytest_check(extra_args=["-n", "0", "tests/test_guards.py"]) to each step\'s Checks so the guard self-tests run serially, as acceptance requires.', 'pr_info/steps/step_2.md:21 — add a time_limit marker with a reason to test_is_git, so every guard self-test has one as acceptance requires.'], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-11-25
**Findings**:
Reviewing the plan: checking candidate tests and conftest hooks against the plan's assumptions.`pr_info/steps/step_2.md:49` — low — The assert list for `test_git_guard` doesn't check that `own failure` appears in stdout next to the guard note for `test_own_failure`. Line 45 expects both, but nothing asserts it. That leaves the acceptance item "reports its own failure with the guard note appended" unverified, because a replaced failure would still pass the count and message asserts. Add `"own failure"` to the asserted stdout strings.

`pr_info/steps/step_3.md:28` — low — The assert list for `test_time_limit` doesn't include `ERROR at teardown of test_slow_teardown`. Line 25 expects it, but nothing asserts it. The teardown-only time violation (the fallback named in Reporting) is therefore untested. Add that header to the asserted stdout strings.
**Decisions**:
Verdict(decision='tasks', tasks=['pr_info/steps/step_2.md:49 — add "own failure" to the stdout strings asserted in test_git_guard. This checks that test_own_failure reports its own failure with the guard note appended, rather than having the failure replaced.', 'pr_info/steps/step_3.md:28 — add "ERROR at teardown of test_slow_teardown" to the stdout strings asserted in test_time_limit, so the teardown-only time-limit violation is covered by a test.'], escalate_reason=None)
**Changes**:
applied
