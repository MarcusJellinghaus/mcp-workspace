"""Self-tests for the test-guard plugin in ``tests/_guards.py``.

Each test runs an inner pytest session via ``pytester``. Inner runs write their
own ``tox.ini``, because the project pyproject does not apply in pytester's
tmp dir. Cases that start no git run in-process; the ``-n 2`` case runs as a
subprocess, because xdist workers started from an in-process run see only the
outer interpreter's startup ``sys.path`` and could not import ``tests._guards``.
"""

import os
from collections.abc import Sequence
from pathlib import Path

import pytest

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
    marker_lines = "".join(f"\n    {m}" for m in markers)
    limit_lines = "".join(f"\n    {line}" for line in limits)
    pytester.makeini(
        "[pytest]\n"
        f"addopts = {INNER_ADDOPTS}\n"
        f"markers ={marker_lines}\n"
        f"test_time_limits ={limit_lines}\n"
    )
    pytester.makeconftest('pytest_plugins = ["tests._guards"]')
    pytester.makepyfile(**files)


def _run_subprocess(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, *args: str
) -> pytest.RunResult:
    """runpytest_subprocess with PROJECT_ROOT prepended to PYTHONPATH."""
    existing = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv(
        "PYTHONPATH", str(PROJECT_ROOT) + (os.pathsep + existing if existing else "")
    )
    return pytester.runpytest_subprocess(*args)


_DOUBLE_IN_CLASS = """
import pytest

class TestDouble:
    @pytest.mark.git_integration
    @pytest.mark.github_integration
    def test_both(self):
        pass

    def test_sibling(self):
        pass
"""

_DOUBLE_IN_MODULE = """
import pytest

@pytest.mark.git_integration
@pytest.mark.github_integration
def test_both():
    pass

def test_sibling():
    pass
"""

_OK = """
def test_ok():
    pass
"""


@pytest.mark.time_limit(30, reason="in-process pytester run")
def test_collection_failures(pytester: pytest.Pytester) -> None:
    _inner(
        pytester,
        {
            "test_double": _DOUBLE_IN_CLASS,
            "test_no_reason": (
                "import pytest\n\n"
                "@pytest.mark.time_limit(1)\n"
                "def test_no_reason():\n    pass\n"
            ),
            "test_no_seconds": (
                "import pytest\n\n"
                '@pytest.mark.time_limit(reason="r")\n'
                "def test_no_seconds():\n    pass\n"
            ),
            "test_bad_seconds": (
                "import pytest\n\n"
                '@pytest.mark.time_limit("fast", reason="r")\n'
                "def test_bad_seconds():\n    pass\n"
            ),
            "test_ok": _OK,
        },
    )

    result = pytester.runpytest("-n", "0")

    assert result.ret == pytest.ExitCode.INTERRUPTED
    output = result.stdout.str()
    assert "test_double.py::TestDouble::test_both" in output
    assert "git_integration" in output
    assert "github_integration" in output
    assert "test_no_reason.py::test_no_reason" in output
    assert "test_no_seconds.py::test_no_seconds" in output
    assert "test_bad_seconds.py::test_bad_seconds" in output
    result.assert_outcomes(errors=4)


@pytest.mark.time_limit(60, reason="subprocess pytester run with two xdist workers")
def test_double_marker_fails_collection_under_xdist(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    _inner(pytester, {"test_double": _DOUBLE_IN_MODULE, "test_ok": _OK})

    result = _run_subprocess(pytester, monkeypatch, "-n", "2", "-rA")

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    output = result.stdout.str()
    assert "test_double.py::test_both" in output
    assert "git_integration" in output
    assert "github_integration" in output
    result.stdout.fnmatch_lines(["PASSED test_ok.py::test_ok"])
    assert "test_sibling" not in output


@pytest.mark.time_limit(30, reason="in-process pytester run")
def test_config_errors_fail_the_run(pytester: pytest.Pytester) -> None:
    _inner(
        pytester,
        {"test_ok": _OK},
        limits=("uint: 5", "unit: fast"),
        markers=("git_integration", "github_integration", "time_limit"),
    )

    result = pytester.runpytest("-n", "0")

    assert result.ret == pytest.ExitCode.USAGE_ERROR
    errors = result.stderr.str()
    assert "uint: 5" in errors
    assert "unit: fast" in errors
    assert "performance" in errors
