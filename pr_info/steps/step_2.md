# Step 2: Git guard and the shared call/teardown reporting

One commit: `test(guards): fail unmarked tests that start a git process`

Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md` first. Issue #417 is the full specification ("Guard 2", "Reporting", "Constraints").

## Goal

An unmarked test (no group marker) that starts a `git` process during setup, call or teardown fails, naming the test and `git_integration`. The reporting built here (`_TestState`, `_report`, and the call and teardown wrappers) is reused by step 3 for time limits.

## WHERE

- Modified:
  - `tests/_guards.py`
  - `tests/test_guards.py`
  - `vulture_whitelist.py`
  - any existing unmarked test the guard catches (see Existing violations)

## Tests first (`tests/test_guards.py`)

1. **`test_is_git`**: a plain parametrized unit test with no pytester and no git. It calls `_is_git(args, executable, shell)` directly.
   - True:
     - `["git", "status"]`
     - `[r"C:\Program Files\Git\cmd\git.exe", "status"]`
     - `["/usr/bin/git"]`
     - `["GIT.EXE"]`
     - `"git status"` (string args)
     - `'"C:\\Program Files\\Git\\cmd\\git.exe" status'`
     - `b"git status"`
     - `[Path("/usr/bin/git")]`
     - `args=["python"]` with `executable="/usr/bin/git"`
     - `args=["x"]` with `executable=b"git.exe"`
   - False:
     - `["python", "-c", "..."]`
     - `["gitk"]`
     - `["git-lfs"]`
     - `"git status"` with `shell=True`
     - `args=["git"]` with `executable="/usr/bin/python"`
2. **`test_git_guard`**: one subprocess run, `-n 0`, `time_limit(60, reason="subprocess pytester run; inner tests start git")`. The inner `test_git.py` imports `git` at module level and contains:
   - `test_gitpython(tmp_path)`: `git.Repo.init(tmp_path)`. Expect a failure.
   - `test_subprocess_git()`: `subprocess.run(["git", "--version"], check=True, capture_output=True)`. Expect a failure.
   - `test_positional_executable()`: `subprocess.Popen(["not-git", "--version"], -1, shutil.which("git"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()`. Expect a failure.
   - `@pytest.mark.git_integration test_marked(tmp_path)`: `git.Repo.init(tmp_path)`. Expect a pass.
   - `test_no_git()`: expect a pass.
   - `test_own_failure()`: runs git, then `assert 1 == 2, "own failure"`. Expect a failure showing both `own failure` and the guard note.
   - `test_fixture_fails(git_then_fail)`: the fixture runs git, then raises `RuntimeError("fixture broke")`. Expect a setup error and `ERROR at teardown of test_fixture_fails` carrying the guard message.
   - `test_fixture_skips(git_then_skip)`: the fixture runs git, then `pytest.skip(...)`. Expect a skip and `ERROR at teardown of test_fixture_skips`.
   - `test_skip_in_body()`: runs git, then `pytest.skip("body skipped")`. Expect a skip and `ERROR at teardown of test_skip_in_body`.
   - Assert:
     - `parseoutcomes()["failed"] == 4` and `["passed"] == 2`
     - for every expected git violation, `f"test_git.py::{name} started a git process"` is in stdout
     - `"git_integration"` is in stdout
     - the `ERROR at teardown of ...` headers above are present
   - Don't configure a git identity. Use only `git init` and `git --version`, because pytester points `HOME` / `USERPROFILE` at a tmp dir.

## WHAT (`tests/_guards.py`)

```python
@dataclass
class _GitCounter:
    spawns: int = 0

_GIT = _GitCounter()   # process-global, only increases; mutated in place (no `global`, pylint W0603)

@dataclass
class _TestState:
    start: float                      # time.perf_counter() at setup start (used by step 3)
    git_start: int                    # _GIT.spawns at setup start
    reported: set[str] = field(default_factory=set)   # {"git", "time"}

_STATE = pytest.StashKey[_TestState]()

def _install_git_counter() -> None
def _is_git(args: object, executable: object, shell: object) -> bool
def _group(item: pytest.Item) -> str                 # group marker name or UNIT
def _report(item: pytest.Item) -> str | None         # new violations as one note, marks them reported
def _attach(exc: BaseException, note: str) -> None   # Failed -> msg append; else add_note

@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None
@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None, None, None]
@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item: pytest.Item) -> Generator[None, None, None]
```

## HOW

- `pytest_configure` (step 1) also calls `_install_git_counter()`.
- The patch:
  - Assign it directly: `subprocess.Popen.__init__ = patched  # type: ignore[method-assign]`. No `setattr`; ruff B010 forbids it.
  - Wrap with `functools.wraps(original)`.
  - Set the marker `patched._tests_guards_git_counter = True  # type: ignore[attr-defined]`.
  - Capture `inspect.signature(original)` inside `_install_git_counter` before assigning.
- `_group(item)`: the first name in `GROUP_MARKERS` for which `item.get_closest_marker(name)` is truthy, else `UNIT`.
- `pytest_runtest_setup` (plain, `tryfirst`) stores `_TestState(time.perf_counter(), _GIT.spawns)`. A mark-skipped test may never reach it, so `_report` treats a missing state (`item.stash.get(_STATE, None)`) as "nothing to check".
- `vulture_whitelist.py`: add `_.pytest_runtest_setup`, `_.pytest_runtest_call` and `_.pytest_runtest_teardown`.
- Module docstring: add the git guard and its documented limitations:
  - `shell=True` is not counted
  - grandchild processes are not seen
  - mocked `subprocess` is not seen
  - module- and session-scoped fixtures are charged to the first or last test that uses them
  - a guard failure on an xfail-marked test is swallowed
  - `import git` must stay at module level in `tests/conftest.py`

## ALGORITHM

### `_install_git_counter`

```
original = subprocess.Popen.__init__
if getattr(original, "_tests_guards_git_counter", False): return       # installed once per process
signature = inspect.signature(original)
def patched(self, *args, **kwargs):
    try: bound = signature.bind(self, *args, **kwargs).arguments
    except TypeError: bound = None                                       # original raises its own TypeError
    original(self, *args, **kwargs)                                      # count only started processes
    if bound is not None and _is_git(bound.get("args"), bound.get("executable"), bound.get("shell", False)): _GIT.spawns += 1
```

### `_is_git`

```
if shell: return False
if executable is not None: target = os.fsdecode(executable)
elif isinstance(args, (str, bytes)): target = _first_token(os.fsdecode(args))   # quoted path → up to closing quote, else split()[0]
elif isinstance(args, os.PathLike): target = os.fsdecode(args)
else: target = os.fsdecode(next(iter(args), ""))
return os.path.basename(target).lower() in {"git", "git.exe"}
```

Use `ntpath.basename` when the string contains a backslash, so the Windows-path cases also pass on Linux CI.

### `_report(item)`

```
state = item.stash.get(_STATE, None); if state is None: return None
notes = []
if "git" not in state.reported and _GIT.spawns > state.git_start and _group(item) == UNIT:
    state.reported.add("git"); notes.append(f"{item.nodeid} started a git process but has no group marker that allows git. Mark it @pytest.mark.git_integration (or github_integration / performance), or stop it from starting git.")
return "\n\n".join(notes) or None
```

### `pytest_runtest_call`

`pytest_runtest_teardown` is the same, minus the skip/xfail branch.

```
try: yield
except (pytest.skip.Exception, pytest.xfail.Exception): raise           # defer to teardown; XFailed subclasses Failed → check first
except BaseException as exc:
    note = _report(item); if note: _attach(exc, note)
    raise
note = _report(item); if note: pytest.fail(note, pytrace=False)
```

### `_attach`

- `pytest.fail.Exception`: set `exc.msg = f"{exc.msg}\n\n{note}"`. This is the only part that gets rendered.
- Anything else: `exc.add_note(note)`.

## DATA

- `_GIT.spawns: int` is monotonic.
- `item.stash[_STATE]` is a `_TestState`.
- `_report` returns `None` or one note string. Step 3 adds the time note to the same list.

## Existing violations

After the guard is on, run the full suite. If an existing unmarked test starts git:
- re-run once
- if it still fails, give it the right group marker (normally `git_integration`), or stop it from starting git

Record each change in the commit message body.

## Checks

- pylint, `run_pytest_check(extra_args=["-n", "auto"])`, the serial performance run, mypy, ruff, vulture.
- `run_format_code` before the commit.

## Blocked conditions

In each case below, write one line to `pr_info/.blocked.txt` and stop.

- `signature.bind` raises `TypeError` for a call that `Popen` itself accepts.
- The guard needs a new dependency.
- A plugin breaks inner runs and cannot be disabled with `-p no:<name>`.

## LLM prompt

> Read `pr_info/steps/summary.md`, `pr_info/steps/step_2.md`, and issue #417 ("Guard 2", "Reporting", "Constraints"). Step 1 is done. Implement step 2 only:
> - write `test_is_git` and `test_git_guard` in `tests/test_guards.py` first
> - then add the `Popen.__init__` counter, `_TestState`, `_report`, `_attach` and the setup, call and teardown hooks to `tests/_guards.py`
> - update the vulture whitelist and the module docstring
>
> Don't add time-limit checks yet. Handle any existing unmarked git-starting test as the step describes. Use the MCP tools listed in `.claude/CLAUDE.md`. Run pylint, pytest (`-n auto`), mypy, ruff and vulture until all pass, format the code, then make one commit. If a blocked condition applies, write one line to `pr_info/.blocked.txt` and stop.
