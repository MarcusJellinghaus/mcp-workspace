# review-implementation review log 1

## Round 1 — 2026-11-25
**Findings**:
Diff and issue are read; now checking the structlog dependency and the task tracker, then I'll write up the findings.`tests/test_guards.py:336` — medium — `test_time_limit` only checks that "own message" appears for `test_pytrace_false`. It never checks that the guard's time note was added to that same failure's `msg`. The test still passes if `_attach` drops the note for `Failed`/`pytrace=False`, so the acceptance item "pytest.fail(..., pytrace=False) and also breaks a guard shows both messages" is not actually tested. Assert on `test_time.py::test_pytrace_false took` in the output too.

`tests/conftest.py:13` — low — `import structlog` imports a package directly that the project doesn't declare; it only arrives through `mcp-coder-utils`. Deptry runs on `src/` only, so nothing catches it. Declare `structlog` in the `dev` extra, or reach it through `mcp_coder_utils.log_utils`.
**Decisions**:
Verdict(decision='tasks', tasks=["In tests/test_guards.py around line 336 (test_time_limit), extend the assertions for test_pytrace_false so they also check that the guard's time note is attached to that same failure, e.g. assert 'test_time.py::test_pytrace_false took' appears in the output alongside the test's own message. This makes the acceptance criterion 'pytest.fail(..., pytrace=False) that also breaks a guard shows both messages' actually tested.", 'tests/conftest.py:13 imports structlog directly, but the project does not declare it. Add structlog to the `dev` optional-dependency extra in pyproject.toml so the test suite does not rely on it arriving transitively through mcp-coder-utils.'], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-11-25
**Findings**:
Reviewing the branch diff for #417 against the issue spec; checking the task tracker and structlog usage in tests before I write the report.`tests/test_guards.py:278` — medium — `test_git_guard` doesn't prove the git note is attached to `test_own_failure`'s own call failure. It only checks that "own failure" and "test_own_failure started a git process" appear somewhere in the output, and it never asserts the error count. If `_attach` dropped the note in the call wrapper, the teardown check would print it as a separate "ERROR at teardown of test_own_failure" and the test would still pass. So the acceptance item "a test that fails on its own and also starts git reports its own failure with the guard note appended" isn't really tested. Fix: assert `"ERROR at teardown of test_own_failure" not in output`, check the order with `fnmatch_lines(["*own failure*", "*test_own_failure started a git process*"])`, and pin `outcomes["errors"]`.
**Decisions**:
Verdict(decision='tasks', tasks=["In tests/test_guards.py around line 278 (test_git_guard), make the test prove the git note is attached to test_own_failure's own call failure and not reported as a separate teardown error. Three changes: (1) assert that 'ERROR at teardown of test_own_failure' is not in the output; (2) check ordering with result.stdout.fnmatch_lines(['*own failure*', '*test_own_failure started a git process*']); (3) pin the expected error count via the parsed outcomes (outcomes['errors'])."], escalate_reason=None)
**Changes**:
applied
