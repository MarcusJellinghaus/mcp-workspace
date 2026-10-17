# review-plan review log 1

## Round 1 — 2026-10-17
**Findings**:
I'll gather the knowledge base principles, the issue details, and the plan files.Now let me read the knowledge base files and all plan step files in parallel.Let me verify the README wording the step 4 precondition depends on, and check the existing test file structure for consistency.pr_info/steps/step_2.md:92 — critical — `_validate_log_level(pre.log_level)` raises `ValueError` immediately, before `_resolve_project_dir`/`_resolve_log_file`/`setup_logging` run. Confirmed against `mcp_coder_utils.log_utils.setup_logging`: it calls `_parse_level` (which also raises `ValueError` for an unknown name) before creating any handler, so no `FileHandler` can exist when the log-level string is bad. `_handle_startup_failure` therefore always finds "no FileHandler" for a bad `--log-level` and writes the **fallback** log, never the normal one — directly contradicting the test this same step specifies at line 143 (`test_invalid_log_level_logs_to_normal_log`, which asserts the normal log under `tmp_path/logs/` contains `BOGUS` and the fallback file was never created). As written, step 2 cannot pass both its own algorithm and its own test in one commit; the design needs a mechanism to establish the normal log sink (e.g. bootstrap with the default level before validating the user-supplied string, or validate inside/after a successful `setup_logging` call) that isn't described anywhere in the plan.
**Decisions**:
Verdict(decision='tasks', tasks=["In step_2.md, fix the startup validation order: do not call `_validate_log_level(pre.log_level)` before a normal log sink exists. Either (a) bootstrap `setup_logging` with the default log level first so a FileHandler exists, then validate/apply the user-supplied `--log-level`, logging any invalid-level error through that already-established normal log handler, or (b) perform log-level validation as part of/after a successful `setup_logging` call rather than before it. Update the step's algorithm description so `_handle_startup_failure`'s fallback-vs-normal-log branching is consistent with `test_invalid_log_level_logs_to_normal_log` (which requires the normal log under `tmp_path/logs/` to contain the bad value and no fallback file to be created)."], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-10-17
**Findings**:
I'll gather context: knowledge base, issue #319, and the plan files.Now let me read the knowledge base files and the plan files.`.claude/knowledge_base/*.md` principles, issue #319 (with linked history), and `pr_info/steps/{summary,step_1..4}.md` reviewed. Round 1's critical finding (log-level validation racing ahead of a log sink) was correctly fixed via the bootstrap-with-INFO re-raise pattern in step_2.md; I verified the fix is internally consistent with `test_invalid_log_level_logs_to_normal_log` and with the `test_ssl.py`/`test_reference_projects.py` traces claiming no edits needed there (confirmed against the actual test file content — those tests don't assert on `setup_logging`'s call args/count, so they tolerate the new control flow).

Two new issues surfaced in this round:

pr_info/steps/step_2.md:58-59 — high — `_validate_log_level` checks `log_level.upper() in _LOG_LEVELS` but then "returns it unchanged" (not the upper-cased form). A lowercase/mixed-case value like `debug` now passes validation (a behavior the old `choices=[...]` never allowed) but is fed as-is into `setup_logging(log_level, log_file)`, which expects the canonical names. This either crashes differently than the designed "exit 1, error logged" path or silently misconfigures logging — undermining the issue's explicit requirement that invalid `--log-level` values exit non-zero with a logged error. Fix: return `log_level.upper()`.

pr_info/steps/step_2.md:150 — medium — the issue's "Done when" list includes "Startup errors appear on stderr; nothing is written to stdout," but no test in step 2's or step 3's test lists captures stdout/stderr content for any failure path. All other testable "Done when" items are covered; this one has no corresponding test anywhere in the plan.
**Decisions**:
Verdict(decision='tasks', tasks=["In step_2.md's `_validate_log_level`, return the upper-cased value (`log_level.upper()`) instead of the original-case input, so a lowercase/mixed-case level like `debug` is normalized to `DEBUG` before being passed to `setup_logging`, matching the canonical names it expects.", "Add a test (in step 2 or step 3's test list) that captures stderr/stdout for a startup-failure path (e.g. invalid `--log-level` or invalid project dir) and asserts the error message appears on stderr and stdout is empty, to cover the 'Done when' requirement that startup errors go to stderr only."], escalate_reason=None)
**Changes**:
applied

## Round 3 — 2026-10-17
**Findings**:
I'll load the necessary MCP tool schemas first, then gather context from the knowledge base, GitHub issues, and plan files.I'll fetch the knowledge base files, the plan files, and issue #319 in parallel.Now I'll read the four step files.Let me check the prior review log to see what's already been addressed in earlier rounds.Review complete — rounds 1 and 2's fixes (log-level bootstrap ordering, upper-casing, stderr test) are correctly applied and internally consistent. One new high-severity gap found.

pr_info/steps/step_2.md:173 — high — `test_trailing_log_level_flag_falls_back`, `test_trailing_project_dir_flag_falls_back` (line 177), and `test_console_only_startup_error_still_writes_fallback` (line 198) all assert on the fallback log but, unlike every other fallback-log test in this same list (lines 160-162, 183-187, 188-190, 194-197, which explicitly use `monkeypatch.chdir(tmp_path)`), specify no chdir or tmp_path at all. As written they write `logs/mcp_workspace_startup_error.log` relative to the real pytest working directory, polluting the actual repo filesystem during test runs and leaving the "fallback log exists/has an entry" assertion location-ambiguous.
**Decisions**:
Verdict(decision='tasks', tasks=["In step_2.md, add `monkeypatch.chdir(tmp_path)` (consistent with the other fallback-log tests in the same list) to `test_trailing_log_level_flag_falls_back`, `test_trailing_project_dir_flag_falls_back`, and `test_console_only_startup_error_still_writes_fallback`, so the fallback log is written under `tmp_path/logs/` instead of the real working directory, and update each test's assertions to check the fallback log at that tmp_path location."], escalate_reason=None)
**Changes**:
applied

## Round 4 — 2026-10-17
**Findings**:
I'll gather the knowledge base principles, the issue context, and the plan files in parallel.This is round 4 — focus on critical/high only. Let me read the four step files.Reviewed the knowledge base, issue #319 (and its planning doc), and all four plan steps. The design is internally consistent: the two-stage parsing, fallback-log rule, help/version short-circuit, and unknown-argument handling all trace through cleanly against the issue's "Done when" criteria, and the trickier edge cases (explicit-but-invalid `--log-file`, console-only + fatal error, bootstrap-then-reraise for bad log level) are each handled by a specific, testable branch rather than hand-waved. I traced the claim that the existing `setup_logging`-patching tests in `test_reference_projects.py`/`test_ssl.py` will keep passing unmodified, and it holds given the preserved call order and the fact those tests never exercise a parse-level failure through `main()`. No new critical/high issues found.

NO FINDINGS
**Decisions**:
Verdict(decision='dismiss', tasks=[], escalate_reason=None)
**Changes**:
dismiss
