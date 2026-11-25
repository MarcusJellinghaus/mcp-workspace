# review-implementation review log 1

## Round 1 — 2026-11-25
**Findings**:
Diff and issue are read; now checking the structlog dependency and the task tracker, then I'll write up the findings.`tests/test_guards.py:336` — medium — `test_time_limit` only checks that "own message" appears for `test_pytrace_false`. It never checks that the guard's time note was added to that same failure's `msg`. The test still passes if `_attach` drops the note for `Failed`/`pytrace=False`, so the acceptance item "pytest.fail(..., pytrace=False) and also breaks a guard shows both messages" is not actually tested. Assert on `test_time.py::test_pytrace_false took` in the output too.

`tests/conftest.py:13` — low — `import structlog` imports a package directly that the project doesn't declare; it only arrives through `mcp-coder-utils`. Deptry runs on `src/` only, so nothing catches it. Declare `structlog` in the `dev` extra, or reach it through `mcp_coder_utils.log_utils`.
**Decisions**:
Verdict(decision='tasks', tasks=["In tests/test_guards.py around line 336 (test_time_limit), extend the assertions for test_pytrace_false so they also check that the guard's time note is attached to that same failure, e.g. assert 'test_time.py::test_pytrace_false took' appears in the output alongside the test's own message. This makes the acceptance criterion 'pytest.fail(..., pytrace=False) that also breaks a guard shows both messages' actually tested.", 'tests/conftest.py:13 imports structlog directly, but the project does not declare it. Add structlog to the `dev` optional-dependency extra in pyproject.toml so the test suite does not rely on it arriving transitively through mcp-coder-utils.'], escalate_reason=None)
**Changes**:
applied
