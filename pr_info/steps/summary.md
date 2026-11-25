# Summary: Test guards (#417)

Disjoint group markers, git-process guard, per-group time limits.

## Goal

Three checks that run in every pytest run under `tests/` (local, agent, CI) with no CI workflow change. Each failure names the offending test.

1. **Disjoint group markers.** A test carries at most one of `git_integration`, `github_integration`, `performance`. Otherwise its module or class fails collection.
2. **Git guard.** A test without a group marker that starts a `git` process fails.
3. **Per-group time limit.** If setup + call + teardown of one test, measured as wall-clock time, exceeds its group's limit, the test fails. The limits are configured in pyproject. `@pytest.mark.time_limit(seconds, reason=...)` overrides the limit for one test, and `--no-time-limit` switches the limit off.

The issue text (#417) is the full specification. This plan is the simplest way to meet it; when in doubt, the issue wins.

## Architectural / design changes

- **New test-only pytest plugin `tests/_guards.py`.** It holds all guard logic and hooks, including `pytest_addoption` and `addini`, and imports nothing from `mcp_workspace`, so it can later move into a shared plugin. `tests/conftest.py` only loads it: `pytest_plugins = ["pytester", "tests._guards"]`.
- **Configuration lives in pyproject:**
  - the `test_time_limits` ini linelist: `unit: 5`, `git_integration: 30`
  - the `time_limit` marker registration
- **One constant `GROUP_MARKERS`** is used by all three guards. `pytest_configure` checks that every group marker is registered and that every `test_time_limits` entry is valid. It reports all problems in one `pytest.UsageError`, so a typo never silently means "no limit".
- **Guard 1 and `time_limit` validation** are one `pytest_make_collect_report` wrapper (`wrapper=True`). For a `Module` or `Class` collector it inspects the collected `Function` children. On any problem it returns a failed `CollectReport` instead of raising, which also works under xdist.
- **Git detection:**
  - `subprocess.Popen.__init__` is patched once per process. A marker attribute on the patched function guards against patching twice.
  - The patch binds each call to the original signature (captured at install time) and checks the `executable` / `args` basename against `git` / `git.exe`, ignoring case.
  - It increments one process-wide counter that only ever goes up. This is the only process-global state.
- **Per-test state** is one `_TestState` record (start time, git counter at setup start, set of guard violations already reported) in `item.stash`. A plain `tryfirst` `pytest_runtest_setup` hook writes it before fixtures run.
- **Per-run state** is one `config.stash` value: the parsed limits dict, or `None` when `--no-time-limit` is given. Nothing is reset at session end, because in-process pytester runs share the module.
- **One check function `_report(item) -> str | None`**, called from two wrappers:
  - `pytest_runtest_call` checks when the test body ends. It re-raises `Skipped` / `XFailed` unchecked, appends the note to `Failed.msg`, uses `add_note` on any other `BaseException`, and otherwise fails with the note.
  - `pytest_runtest_teardown` checks again after fixture teardown.

  Because already-reported violations are skipped, this one rule covers four cases: the call-phase report, a teardown-only violation, no call phase (setup failed or skipped), and a deferred skip or xfail.
- **Guard self-tests (`tests/test_guards.py`)** batch scenarios into a few inner pytester runs:
  - in-process for cases that start no git
  - `runpytest_subprocess` with `PYTHONPATH` set to the project root for git cases and for the single `-n 2` case

  Every inner run writes its own `tox.ini` (markers, `test_time_limits`, `addopts = -p no:tach -p no:textual-snapshot -p no:cacheprovider --strict-markers`) and a `conftest.py` with `pytest_plugins = ["tests._guards"]`. Every outer self-test carries a `time_limit` with a reason.
- **Documentation** goes in the `tests/_guards.py` module docstring (usage and documented limitations), so it moves with the plugin. `tests/README.md` gets a short pointer.

## Files

### Created
- `tests/_guards.py`: the guard plugin.
- `tests/test_guards.py`: the guard self-tests (pytester, plus pure unit tests for `_is_git`).

### Modified
- `tests/conftest.py`: adds `pytest_plugins = ["pytester", "tests._guards"]`.
- `pyproject.toml`: registers the `time_limit` marker; adds `test_time_limits`.
- `vulture_whitelist.py`: `pytest_plugins` and the `pytest_*` hook names.
- Known candidates get `@pytest.mark.time_limit(60, reason=...)`:
  - `tests/test_startup_performance.py`: the two unmarked tests
  - `tests/test_main_verify.py`: `test_main_import_does_not_load_verify_dependencies`
  - `tests/toolset/test_toolset_imports.py`: a module-level `pytestmark`
  - `tests/github_operations/test_traffic_log.py`: `test_concurrent_processes_lose_no_lines`
- `tests/README.md`: a short "Test guards" pointer.
- Any test the guard runs surface: re-mark it or add a `time_limit`, as the steps describe.

## Steps

1. Plugin skeleton: options, configure-time checks, guard 1 and `time_limit` validation, wiring, candidates marked.
2. Git guard and the shared call/teardown reporting.
3. Time limits, documentation, final unit-group run.

## Blocking rule (all steps)

If a precondition named in a step does not hold, write one line to `pr_info/.blocked.txt` and stop.
