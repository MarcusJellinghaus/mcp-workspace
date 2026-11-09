# review-plan review log 1

## Round 1 — 2026-11-09
**Findings**:
Checking the plan's claims against the test fixtures and other `JobData` producers.pr_info/steps/step_2.md:151 — low — `test_job_beyond_log_cap_has_correct_link` returns `{}` logs for runs 1–3 as well, so "(logs not available locally)" shows up in every section. The test would still pass if run 4 wrongly reused another run's logs. Fix: give runs 1–3 non-empty logs that match run 4's job name (e.g. via `side_effect`), then assert that run 4's section has none of them.
**Decisions**:
Verdict(decision='tasks', tasks=["In pr_info/steps/step_2.md:151, strengthen `test_job_beyond_log_cap_has_correct_link`: give runs 1–3 non-empty logs (e.g. via `side_effect`) keyed to the same job name as run 4's failed job, then assert that run 4's section contains none of those log contents and still shows '(logs not available locally)', so the test fails if run 4 picks up another run's logs."], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-11-09
**Findings**:
Plan files and code read; now checking the existing tests the plan says must pass unchanged.pr_info/steps/step_2.md:152 — medium — `test_job_beyond_log_cap_has_correct_link` doesn't say what order the 4 runs appear in `jobs`. The fetch cap applies to the first 3 run keys in order of appearance, so run 4 only goes without logs if its job is listed last. The plan's own convention is that the newer run is listed first (B=200 before A=100, step_2.md:132-133). By that convention run 4, the newest, would be listed first and get logs, and the test's asserts would fail. Fix: state that the jobs are listed in order run 1, 2, 3, 4, so run 4 falls past `[:3]`, or rename the test to say "4th run in jobs order".
**Decisions**:
Verdict(decision='tasks', tasks=["In pr_info/steps/step_2.md:152, make `test_job_beyond_log_cap_has_correct_link` say the 4 runs' jobs appear in `jobs` in the order run 1, 2, 3, 4. That ordering puts run 4 past the `[:3]` fetch cap. Add a short note that this deliberately differs from the newest-first convention used at step_2.md:132-133."], escalate_reason=None)
**Changes**:
applied
