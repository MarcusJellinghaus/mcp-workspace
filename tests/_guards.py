"""Test guards: disjoint group markers and per-test ``time_limit`` validation.

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
    The ``test_time_limits`` ini linelist sets a wall-clock limit per group,
    e.g. ``"unit: 5"`` or ``"git_integration: 30"``. Keys are ``unit`` or a
    group marker; values are positive seconds, fractions allowed. A group
    without an entry has no limit. An unknown key or a bad value fails the
    run at configure time, so a typo never silently means "no limit".
    ``--no-time-limit`` switches the limits off.

    ``@pytest.mark.time_limit(seconds, reason="...")`` overrides the limit
    for one test in any group. ``seconds`` must be a positive number and
    ``reason`` a non-empty string; otherwise collection of the containing
    module or class fails.
"""

import math
from collections.abc import Generator

import pytest

GROUP_MARKERS: tuple[str, ...] = (
    "git_integration",
    "github_integration",
    "performance",
)
UNIT = "unit"
# Parsed test_time_limits per run; None when --no-time-limit is given.
_LIMITS = pytest.StashKey[dict[str, float] | None]()


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
