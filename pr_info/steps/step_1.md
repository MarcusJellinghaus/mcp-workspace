# Step 1: Plugin skeleton, configure-time checks, guard 1, `time_limit` validation

One commit: `test(guards): add test-guard plugin with group-marker and time_limit checks`

Read `pr_info/steps/summary.md` first. Issue #417 is the full specification.

## Goal

- Create `tests/_guards.py` and load it from `tests/conftest.py`.
- Add `--no-time-limit` and the `test_time_limits` ini setting. Check the configuration at configure time.
- Make a test carrying two group markers, or an invalid `time_limit` marker, fail collection of its module or class.
- Mark the known slow candidates with `time_limit`. Time limits are **not enforced yet**; the git guard does not exist yet.

## WHERE

- New: `tests/_guards.py`, `tests/test_guards.py`
- Modified:
  - `tests/conftest.py`
  - `pyproject.toml`
  - `vulture_whitelist.py`
  - the candidate tests:
    - `tests/test_startup_performance.py`
    - `tests/test_main_verify.py`
    - `tests/toolset/test_toolset_imports.py`
    - `tests/github_operations/test_traffic_log.py`

## Tests first (`tests/test_guards.py`)

### Module-level helpers

```python
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INNER_ADDOPTS = "-p no:tach -p no:textual-snapshot -p no:cacheprovider --strict-markers"
ALL_MARKERS = ("git_integration", "github_integration", "performance", "time_limit")

def _inner(
    pytester: pytest.Pytester,
    files: dict[str, str],
    *,
    limits: Sequence[str] = ("unit: 0.5", "git_integration: 30"),
    markers: Sequence[str] = ALL_MARKERS,
) -> None:
    """Write tox.ini ([pytest] addopts/markers/test_time_limits), conftest and test files."""

def _run_subprocess(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, *args: str
) -> pytest.RunResult:
    """runpytest_subprocess with PROJECT_ROOT prepended to PYTHONPATH."""
```

- `_inner` writes:
  - `tox.ini` via `pytester.makeini` with a `[pytest]` section:
    - `addopts = {INNER_ADDOPTS}`
    - `markers =` one name per line
    - `test_time_limits =` one entry per line
  - `conftest.py` via `pytester.makeconftest('pytest_plugins = ["tests._guards"]')`
  - the test files via `pytester.makepyfile(**files)`
- In-process runs call `pytester.runpytest("-n", "0", ...)`.
- `_run_subprocess` calls `monkeypatch.setenv("PYTHONPATH", ...)` and then `pytester.runpytest_subprocess(*args)`.
- Never use `-n auto` in inner runs.

### Tests

Each one carries `@pytest.mark.time_limit(<s>, reason=...)`.

1. **`test_collection_failures`**: in-process, `-n 0`, `time_limit(30, reason="in-process pytester run")`.
   - Inner files:
     - `test_double.py`: a class `TestDouble` with
       - `test_both`, marked `git_integration` and `github_integration`
       - `test_sibling`, unmarked
     - `test_no_reason.py`: `@pytest.mark.time_limit(1)`
     - `test_no_seconds.py`: `@pytest.mark.time_limit(reason="r")`
     - `test_bad_seconds.py`: `@pytest.mark.time_limit("fast", reason="r")`
     - `test_ok.py`: a trivial passing test
   - Assert:
     - `result.ret == pytest.ExitCode.INTERRUPTED`
     - the output contains `test_double.py::TestDouble::test_both`, `git_integration` and `github_integration`
     - the output names each of the three bad `time_limit` tests
     - the summary shows 4 errors
     - no test passed
2. **`test_double_marker_fails_collection_under_xdist`**: subprocess, `-n 2`, `time_limit(60, reason="subprocess pytester run with two xdist workers")`.
   - Inner files:
     - `test_double.py`: a module-level double-marked test plus an unmarked sibling
     - `test_ok.py`: one passing test
   - Assert:
     - `result.ret == pytest.ExitCode.TESTS_FAILED`
     - the output names the double-marked test and both markers
     - `test_ok` passed
     - the sibling did not run
3. **`test_config_errors_fail_the_run`**: in-process, `time_limit(30, reason="in-process pytester run")`.
   - Inner config: `limits=("uint: 5", "unit: fast")`, and `markers` without `performance`.
   - Assert:
     - `result.ret == pytest.ExitCode.USAGE_ERROR`
     - stderr contains `uint: 5`, `unit: fast` and `performance`

## WHAT (`tests/_guards.py`)

```python
GROUP_MARKERS: tuple[str, ...] = ("git_integration", "github_integration", "performance")
UNIT = "unit"
_LIMITS = pytest.StashKey[dict[str, float] | None]()   # None = --no-time-limit

def pytest_addoption(parser: pytest.Parser) -> None
def pytest_configure(config: pytest.Config) -> None
@pytest.hookimpl(wrapper=True)
def pytest_make_collect_report(collector: pytest.Collector) -> Generator[None, pytest.CollectReport, pytest.CollectReport]

def _parse_limits(lines: list[str]) -> tuple[dict[str, float], list[str]]   # (limits, errors)
def _time_limit_seconds(mark: pytest.Mark) -> float                         # raises ValueError
def _collect_errors(item: pytest.Function) -> list[str]
```

## HOW

- `pytest_addoption`:
  - `parser.addoption("--no-time-limit", action="store_true", help=...)`
  - `parser.addini("test_time_limits", type="linelist", help=...)`
- `tests/conftest.py`: add `pytest_plugins = ["pytester", "tests._guards"]` near the top. Keep `import git` at module level; it must stay there.
- `pyproject.toml` `[tool.pytest.ini_options]`:
  - add a `markers` entry: `"time_limit(seconds, reason): per-test wall-clock limit override in seconds; reason is mandatory"`
  - add `test_time_limits = ["unit: 5", "git_integration: 30"]`
- `vulture_whitelist.py`: add a commented block with `_.pytest_plugins`, `_.pytest_addoption`, `_.pytest_configure` and `_.pytest_make_collect_report`.
- Hooks declare only the arguments they use.
- Candidate tests get `@pytest.mark.time_limit(60, reason="spawns a fresh Python interpreter")`:
  - the two unmarked tests in `test_startup_performance.py`
  - `test_main_import_does_not_load_verify_dependencies`
  - `test_toolset_imports.py`, as a module-level `pytestmark`
  - `test_concurrent_processes_lose_no_lines`, with reason `"spawns 8 Python interpreters"`
- Module docstring of `_guards.py`:
  - what the plugin does
  - the group markers, and that `GROUP_MARKERS` must match the pyproject registration
  - `test_time_limits` and `time_limit`

  Steps 2 and 3 extend it.

## ALGORITHM

### `pytest_configure`

```
limits, errors = _parse_limits(config.getini("test_time_limits"))
registered = {line.split(":")[0].split("(")[0].strip() for line in config.getini("markers")}
errors += [f"group marker {m!r} is not registered in markers" for m in GROUP_MARKERS if m not in registered]
if errors: raise pytest.UsageError("tests._guards: " + "; ".join(errors))
config.stash[_LIMITS] = None if config.getoption("--no-time-limit") else limits
```

- `_parse_limits`: for each line, `key, sep, value = line.partition(":")`.
  - If the key is not `unit` or a group marker, report `f"invalid test_time_limits entry {line!r}: unknown key"`.
  - If `float(value)` fails, or the value is not finite and greater than 0, report `"... : not a positive number"`.

### `_time_limit_seconds(mark)`

- `seconds` is `mark.args[0]`, or `mark.kwargs["seconds"]`. It must be `int` or `float` (not `bool`) and greater than 0.
- `reason` is `mark.kwargs["reason"]` and must be a non-empty `str`.
- On violation, raise `ValueError` with a message naming what is missing or invalid. Otherwise return `float(seconds)`.

### `pytest_make_collect_report`

```
report = yield
if not (report.passed and isinstance(collector, (pytest.Module, pytest.Class))): return report
errors = [e for item in report.result if isinstance(item, pytest.Function) for e in _collect_errors(item)]
if not errors: return report
return pytest.CollectReport(report.nodeid, "failed", "\n".join(errors), [], sections=report.sections)
```

### `_collect_errors(item)`

```
groups = [m for m in GROUP_MARKERS if item.get_closest_marker(m)]
if len(groups) > 1: append(f"{item.nodeid} carries group markers {', '.join(groups)}; a test carries at most one of {', '.join(GROUP_MARKERS)}")
mark = item.get_closest_marker("time_limit")
if mark: try _time_limit_seconds(mark) except ValueError as exc: append(f"{item.nodeid}: invalid time_limit marker: {exc}")
```

## DATA

- `config.stash[_LIMITS]`: `{"unit": 5.0, "git_integration": 30.0}`, or `None` with `--no-time-limit`. Step 3 reads it.
- A failed `CollectReport` whose `longrepr` is a plain string, one line per problem.

## Checks

- `run_pylint_check`, `run_mypy_check`, `run_ruff_check`, `run_vulture_check`.
- The unit group: `run_pytest_check(markers=["not git_integration", "not github_integration"], extra_args=["-n", "auto"])`. Never run the `git_integration` / `github_integration` groups or the full suite in automated steps (it exceeds the 600 s inactivity limit).
- The guard self-tests serially: `run_pytest_check(extra_args=["-n", "0", "tests/test_guards.py"])`.
- The serial performance run: `run_pytest_check(markers=["performance"], extra_args=["-n", "0"])`.
- `run_format_code` before the commit.

## Blocked conditions

In each case below, write one line to `pr_info/.blocked.txt` and stop.

- pytest rejects `pytest_plugins` in `tests/conftest.py`.
- A plugin breaks in-process inner runs and cannot be disabled with `-p no:<name>` in the inner `addopts`.
- A `.scratch/` probe run (path outside `tests/`) fails because of the "Unknown config option: test_time_limits" warning.
- An existing test carries two group markers and the right single marker is not clear from the test.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`, and issue #417 for the full requirements. Implement step 1 only:
> - write the tests in `tests/test_guards.py` first, then `tests/_guards.py`
> - add the `pytest_plugins` wiring in `tests/conftest.py`
> - make the pyproject, vulture whitelist and candidate `time_limit` changes
>
> Don't implement the git guard or time-limit enforcement. Use the MCP tools listed in `.claude/CLAUDE.md`. Run pylint, the pytest runs listed under Checks (unit group only), mypy, ruff and vulture until all pass, format the code, then make one commit. If a blocked condition from the step file applies, write one line to `pr_info/.blocked.txt` and stop.
