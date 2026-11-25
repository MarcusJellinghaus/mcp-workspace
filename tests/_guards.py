"""Test guards: disjoint group markers, git guard, per-group time limits.

A pytest plugin loaded from ``tests/conftest.py`` via ``pytest_plugins``. It
imports nothing from ``mcp_workspace``, so it can move into a shared plugin.

Group markers
    ``git_integration``, ``github_integration`` and ``performance`` (the
    ``GROUP_MARKERS`` constant). A test carries at most one of them; a test
    without one belongs to the ``unit`` group. ``GROUP_MARKERS`` duplicates
    the marker registration in pyproject and must match it: the run fails at
    configure time if a group marker is not registered.

    A test carrying two group markers fails collection of its containing
    module or class, naming the test and its markers. With ``-n 0`` this
    interrupts the session; under xdist the other modules still run, and the
    run fails.

Time limits
    A test whose setup + call + teardown takes longer than its limit fails.
    The limit is wall-clock time (``time.perf_counter``), so machine load and
    xdist contention count; the test is not interrupted, only failed once it
    ends.

    The ``test_time_limits`` ini linelist sets a limit per group, e.g.
    ``"unit: 5"`` or ``"git_integration: 30"``. Keys are ``unit`` or a group
    marker; values are positive seconds, fractions allowed. A group without
    an entry has no limit. An unknown key or a bad value fails the run at
    configure time, so a typo never silently means "no limit".

    ``@pytest.mark.time_limit(seconds, reason="...")`` overrides the limit
    for one test in any group. ``seconds`` must be a positive number and
    ``reason`` a non-empty string; otherwise collection of the containing
    module or class fails.

    ``--no-time-limit`` switches the time limit off and leaves the other
    guards on. Use it with ``--pdb``, breakpoints or profiling; through
    mcp-tools-py, ``run_pytest_check(extra_args=["--no-time-limit", ...])``.

    Re-run rule: a time-limit failure can be a load spike. Re-run before
    changing anything; a single spike under xdist is not a reason to add
    ``time_limit``, re-mark or rewrite the test. Only if it fails again:
    speed the test up, give it the right group marker, or add a
    ``time_limit`` with a reason. In CI, re-run the job.

Git guard
    A test without a group marker that starts a ``git`` process during setup,
    call or teardown fails, naming the test and ``git_integration``. A git
    process is any ``subprocess.Popen`` whose executable basename is ``git``
    or ``git.exe`` (case-insensitive), from ``executable`` (keyword or
    positional) or else the first element or token of ``args``. This covers
    GitPython and direct subprocess calls. ``Popen.__init__`` is patched once
    per process and counts started git processes; each test compares the
    count against a snapshot taken at the start of its setup.

    Git guard limitations:

    - ``shell=True`` starts the shell, not git, and is not counted.
    - Grandchild processes (a child process that starts git) are not seen.
    - A mocked ``subprocess`` starts no process and is not seen.
    - ``import git`` runs ``git version``. GitPython must stay imported at
      module level in ``tests/conftest.py``, so it loads at collection time;
      a first import inside a test would charge that process to whichever
      test runs first in each xdist worker.

Reporting
    Git and time violations are reported when the test body ends, as a call
    failure; a test that fails on its own keeps its failure with the guard
    note appended. A violation not yet reported then is reported after
    fixture teardown, as a teardown error: git started or time exceeded only
    in teardown, in a setup that failed or skipped, or before
    ``pytest.skip()`` / ``pytest.xfail()`` in the body. Each violation is
    reported once per test.

    Limitations:

    - Module- and session-scoped fixtures are set up in the first test that
      uses them and torn down in the last, so their git use and time are
      charged to those tests.
    - A guard failure on an xfail-marked test is swallowed by the xfail.
"""

import functools
import inspect
import math
import ntpath
import os
import subprocess
import time
from collections.abc import Generator, Iterable
from dataclasses import dataclass, field
from typing import Any

import pytest

GROUP_MARKERS: tuple[str, ...] = (
    "git_integration",
    "github_integration",
    "performance",
)
UNIT = "unit"
RERUN_NOTE = (
    "re-run before changing anything; a single spike under xdist is not a reason to add "
    "`time_limit`, re-mark or rewrite the test — act only if it fails again."
)
# Parsed test_time_limits per run; None when --no-time-limit is given.
_LIMITS = pytest.StashKey[dict[str, float] | None]()


@dataclass
class _GitCounter:
    """Number of git processes started in this process; only ever increases."""

    spawns: int = 0


# The only process-global state. In-process pytester runs share this module,
# so it is never reset; tests compare against their own snapshot instead.
_GIT = _GitCounter()


@dataclass
class _TestState:
    """Per-test guard state, stored in ``item.stash`` at the start of setup."""

    start: float
    git_start: int
    reported: set[str] = field(default_factory=set)


_STATE = pytest.StashKey[_TestState]()


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register ``--no-time-limit`` and the ``test_time_limits`` ini setting."""
    parser.addoption(
        "--no-time-limit",
        action="store_true",
        help="Disable the per-group test time limits (the other guards stay on).",
    )
    parser.addini(
        "test_time_limits",
        type="linelist",
        help="Per-group wall-clock limits in seconds, one 'group: seconds' per line.",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Validate the guard configuration and store the parsed limits.

    Raises:
        pytest.UsageError: If a ``test_time_limits`` entry is invalid or a
            group marker is not registered.
    """
    limits, errors = _parse_limits(config.getini("test_time_limits"))
    registered = {
        line.split(":")[0].split("(")[0].strip() for line in config.getini("markers")
    }
    errors += [
        f"group marker {m!r} is not registered in markers"
        for m in GROUP_MARKERS
        if m not in registered
    ]
    if errors:
        raise pytest.UsageError("tests._guards: " + "; ".join(errors))
    config.stash[_LIMITS] = None if config.getoption("--no-time-limit") else limits
    _install_git_counter()


@pytest.hookimpl(wrapper=True)
def pytest_make_collect_report(
    collector: pytest.Collector,
) -> Generator[None, pytest.CollectReport, pytest.CollectReport]:
    """Fail a module or class whose tests break the marker rules.

    A failed report, rather than an exception, keeps the message visible
    under xdist, where collection runs in the workers.
    """
    report = yield
    if not (report.passed and isinstance(collector, (pytest.Module, pytest.Class))):
        return report
    errors = [
        error
        for item in report.result
        if isinstance(item, pytest.Function)
        for error in _collect_errors(item)
    ]
    if not errors:
        return report
    return pytest.CollectReport(
        report.nodeid, "failed", "\n".join(errors), [], sections=report.sections
    )


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:
    """Snapshot the clock and the git counter before any fixture runs."""
    item.stash[_STATE] = _TestState(time.perf_counter(), _GIT.spawns)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None, None, None]:
    """Fail the call phase on a guard violation, keeping the test's own failure.

    ``Skipped`` and ``XFailed`` pass through unchecked; teardown checks them.
    They are caught first because ``XFailed`` subclasses ``Failed``.
    """
    try:
        yield
    except (pytest.skip.Exception, pytest.xfail.Exception):
        raise
    except BaseException as exc:
        note = _report(item)
        if note:
            _attach(exc, note)
        raise
    note = _report(item)
    if note:
        pytest.fail(note, pytrace=False)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item: pytest.Item) -> Generator[None, None, None]:
    """Report violations not yet reported in the call phase as a teardown error."""
    try:
        yield
    except BaseException as exc:
        note = _report(item)
        if note:
            _attach(exc, note)
        raise
    note = _report(item)
    if note:
        pytest.fail(note, pytrace=False)


def _install_git_counter() -> None:
    """Patch ``subprocess.Popen.__init__`` to count started git processes.

    The patch goes on the class, because GitPython binds ``Popen`` at import.
    The signature is captured before patching: afterwards it would read as
    ``(*args, **kwargs)`` and ``executable`` would never bind.
    """
    original = subprocess.Popen.__init__
    if getattr(original, "_tests_guards_git_counter", False):
        return
    signature = inspect.signature(original)

    @functools.wraps(original)
    def patched(self: subprocess.Popen[Any], *args: Any, **kwargs: Any) -> None:
        bound: dict[str, Any] | None
        try:
            bound = dict(signature.bind(self, *args, **kwargs).arguments)
        except TypeError:
            bound = None  # the original call raises its own TypeError
        original(self, *args, **kwargs)
        if bound is not None and _is_git(
            bound.get("args"), bound.get("executable"), bound.get("shell", False)
        ):
            _GIT.spawns += 1

    patched._tests_guards_git_counter = True  # type: ignore[attr-defined]
    subprocess.Popen.__init__ = patched  # type: ignore[method-assign]


def _decode(value: object) -> str:
    """Return a str/bytes/PathLike value as str; anything else as ``""``."""
    if isinstance(value, (str, bytes, os.PathLike)):
        return os.fsdecode(value)
    return ""


def _first_token(command: str) -> str:
    """Return the program of a command string, honouring a quoted path."""
    command = command.lstrip()
    if command.startswith('"'):
        return command[1:].split('"', 1)[0]
    parts = command.split()
    return parts[0] if parts else ""


def _is_git(args: object, executable: object, shell: object) -> bool:
    """Return whether a ``Popen`` call with these arguments starts git."""
    if shell:
        return False
    if executable is not None:
        target = _decode(executable)
    elif isinstance(args, (str, bytes)):
        target = _first_token(os.fsdecode(args))
    elif isinstance(args, os.PathLike):
        target = os.fsdecode(args)
    elif isinstance(args, Iterable):
        target = _decode(next(iter(args), ""))
    else:
        target = ""
    # ntpath also splits on "/", and handles Windows paths on any platform.
    basename = ntpath.basename(target) if "\\" in target else os.path.basename(target)
    return basename.lower() in {"git", "git.exe"}


def _group(item: pytest.Item) -> str:
    """Return the test's group marker name, or ``UNIT``."""
    for name in GROUP_MARKERS:
        if item.get_closest_marker(name):
            return name
    return UNIT


def _report(item: pytest.Item) -> str | None:
    """Return the test's not yet reported violations as one note.

    Marks them reported, so the teardown check skips what the call phase
    already reported. A test that never reached setup has nothing to check.
    """
    state = item.stash.get(_STATE, None)
    if state is None:
        return None
    notes: list[str] = []
    if (
        "git" not in state.reported
        and _GIT.spawns > state.git_start
        and _group(item) == UNIT
    ):
        state.reported.add("git")
        notes.append(
            f"{item.nodeid} started a git process but has no group marker that "
            "allows git. Mark it @pytest.mark.git_integration (or "
            "github_integration / performance), or stop it from starting git."
        )
    limit = _limit(item)
    elapsed = time.perf_counter() - state.start
    if "time" not in state.reported and limit and elapsed > limit[0]:
        state.reported.add("time")
        notes.append(
            f"{item.nodeid} took {elapsed:.2f} s wall-clock (setup + call + "
            f"teardown so far), over the {limit[0]:g} s limit of {limit[1]}. "
            f"The limit is wall-clock time, so machine load counts: {RERUN_NOTE} "
            "In CI, re-run the job. If it fails again: speed the test up, give "
            "it the right group marker, or add "
            '@pytest.mark.time_limit(seconds, reason="...").'
        )
    return "\n\n".join(notes) or None


def _limit(item: pytest.Item) -> tuple[float, str] | None:
    """Return the test's time limit and where it comes from, or ``None``.

    ``None`` means no limit: ``--no-time-limit`` was given, or the test has
    no ``time_limit`` marker and its group has no ``test_time_limits`` entry.
    """
    limits = item.config.stash[_LIMITS]
    if limits is None:
        return None
    mark = item.get_closest_marker("time_limit")
    if mark:
        return _time_limit_seconds(mark), "its time_limit marker"
    group = _group(item)
    return (limits[group], f"group {group!r}") if group in limits else None


def _attach(exc: BaseException, note: str) -> None:
    """Append a guard note to the test's own exception.

    pytest renders only ``msg`` of a ``Failed``, so the note goes there;
    other exceptions render their notes.
    """
    if isinstance(exc, pytest.fail.Exception):
        exc.msg = f"{exc.msg}\n\n{note}" if exc.msg else note
    else:
        exc.add_note(note)


def _parse_limits(lines: list[str]) -> tuple[dict[str, float], list[str]]:
    """Parse ``test_time_limits`` lines into limits and error messages."""
    limits: dict[str, float] = {}
    errors: list[str] = []
    for line in lines:
        key, _, value = line.partition(":")
        key = key.strip()
        if key != UNIT and key not in GROUP_MARKERS:
            errors.append(f"invalid test_time_limits entry {line!r}: unknown key")
            continue
        try:
            seconds = float(value)
        except ValueError:
            seconds = math.nan
        if not (math.isfinite(seconds) and seconds > 0):
            errors.append(
                f"invalid test_time_limits entry {line!r}: not a positive number"
            )
            continue
        limits[key] = seconds
    return limits, errors


def _time_limit_seconds(mark: pytest.Mark) -> float:
    """Return the seconds of a ``time_limit`` marker.

    Raises:
        ValueError: If ``seconds`` is missing or not a positive number, or
            ``reason`` is missing or empty.
    """
    if mark.args:
        seconds = mark.args[0]
    elif "seconds" in mark.kwargs:
        seconds = mark.kwargs["seconds"]
    else:
        raise ValueError("seconds is missing")
    if (
        isinstance(seconds, bool)
        or not isinstance(seconds, (int, float))
        or not seconds > 0
    ):
        raise ValueError(f"seconds must be a positive number, got {seconds!r}")
    reason = mark.kwargs.get("reason")
    if not isinstance(reason, str) or not reason:
        raise ValueError("reason is missing")
    return float(seconds)


def _collect_errors(item: pytest.Function) -> list[str]:
    """Return the marker-rule violations of one collected test."""
    errors: list[str] = []
    groups = [m for m in GROUP_MARKERS if item.get_closest_marker(m)]
    if len(groups) > 1:
        errors.append(
            f"{item.nodeid} carries group markers {', '.join(groups)}; "
            f"a test carries at most one of {', '.join(GROUP_MARKERS)}"
        )
    mark = item.get_closest_marker("time_limit")
    if mark:
        try:
            _time_limit_seconds(mark)
        except ValueError as exc:
            errors.append(f"{item.nodeid}: invalid time_limit marker: {exc}")
    return errors
