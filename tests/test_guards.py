"""Self-tests for the test-guard plugin in ``tests/_guards.py``.

Most tests run an inner pytest session via ``pytester``. Inner runs write their
own ``tox.ini``, because the project pyproject does not apply in pytester's
tmp dir. Cases that start no git run in-process. Git cases run as a
subprocess, so the outer guard does not charge inner git to the outer test.
The ``-n 2`` case runs as a subprocess, because xdist workers started from an
in-process run see only the outer interpreter's startup ``sys.path`` and could
not import ``tests._guards``.
"""

import os
from collections.abc import Sequence
from pathlib import Path

import pytest

from tests._guards import _is_git

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


@pytest.mark.time_limit(
    5, reason="guard self-test; every guard self-test carries a time_limit"
)
@pytest.mark.parametrize(
    ("args", "executable", "shell", "expected"),
    [
        (["git", "status"], None, False, True),
        ([r"C:\Program Files\Git\cmd\git.exe", "status"], None, False, True),
        (["/usr/bin/git"], None, False, True),
        (["GIT.EXE"], None, False, True),
        ("git status", None, False, True),
        ('"C:\\Program Files\\Git\\cmd\\git.exe" status', None, False, True),
        (b"git status", None, False, True),
        ([Path("/usr/bin/git")], None, False, True),
        (["python"], "/usr/bin/git", False, True),
        (["x"], b"git.exe", False, True),
        (["python", "-c", "..."], None, False, False),
        (["gitk"], None, False, False),
        (["git-lfs"], None, False, False),
        ("git status", None, True, False),
        (["git"], "/usr/bin/python", False, False),
    ],
)
def test_is_git(args: object, executable: object, shell: bool, expected: bool) -> None:
    assert _is_git(args, executable, shell) is expected


_GIT_TESTS = """
import shutil
import subprocess

import git
import pytest


def _run_git():
    subprocess.run(["git", "--version"], check=True, capture_output=True)


@pytest.fixture
def git_then_fail():
    _run_git()
    raise RuntimeError("fixture broke")


@pytest.fixture
def git_then_skip():
    _run_git()
    pytest.skip("fixture skipped")


def test_gitpython(tmp_path):
    git.Repo.init(tmp_path)


def test_subprocess_git():
    subprocess.run(["git", "--version"], check=True, capture_output=True)


def test_positional_executable():
    subprocess.Popen(
        ["not-git", "--version"],
        -1,
        shutil.which("git"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).wait()


@pytest.mark.git_integration
def test_marked(tmp_path):
    git.Repo.init(tmp_path)


def test_no_git():
    pass


def test_own_failure():
    _run_git()
    assert 1 == 2, "own failure"


def test_fixture_fails(git_then_fail):
    pass


def test_fixture_skips(git_then_skip):
    pass


def test_skip_in_body():
    _run_git()
    pytest.skip("body skipped")
"""


@pytest.mark.time_limit(60, reason="subprocess pytester run; inner tests start git")
def test_git_guard(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> None:
    _inner(pytester, {"test_git": _GIT_TESTS})

    result = _run_subprocess(pytester, monkeypatch, "-n", "0")

    outcomes = result.parseoutcomes()
    assert outcomes["failed"] == 4
    assert outcomes["passed"] == 2
    output = result.stdout.str()
    for name in (
        "test_gitpython",
        "test_subprocess_git",
        "test_positional_executable",
        "test_own_failure",
        "test_fixture_fails",
        "test_fixture_skips",
        "test_skip_in_body",
    ):
        assert f"test_git.py::{name} started a git process" in output
    assert "git_integration" in output
    assert "own failure" in output
    for name in ("test_fixture_fails", "test_fixture_skips", "test_skip_in_body"):
        assert f"ERROR at teardown of {name}" in output


_TIME_TESTS = """
import time

import pytest


@pytest.fixture
def slow_setup():
    time.sleep(0.7)


@pytest.fixture
def slow_teardown():
    yield
    time.sleep(0.7)


def test_slow_fixture(slow_setup):
    pass


@pytest.mark.time_limit(5, reason="r")
def test_override():
    time.sleep(0.7)


def test_pytrace_false():
    time.sleep(0.7)
    pytest.fail("own message", pytrace=False)


def test_slow_teardown(slow_teardown):
    pass


def test_fast():
    pass
"""


@pytest.mark.time_limit(30, reason="in-process pytester run; inner tests sleep")
def test_time_limit(pytester: pytest.Pytester) -> None:
    _inner(pytester, {"test_time": _TIME_TESTS})

    result = pytester.runpytest("-n", "0", "-rA")

    assert result.parseoutcomes()["failed"] == 2
    output = result.stdout.str()
    assert "PASSED test_time.py::test_override" in output
    assert "PASSED test_time.py::test_fast" in output
    assert "test_time.py::test_slow_fixture" in output
    assert "wall-clock" in output
    assert "0.5 s" in output
    result.stdout.fnmatch_lines(
        ["*own message*", "*test_time.py::test_pytrace_false took * s wall-clock*"]
    )
    assert "ERROR at teardown of test_slow_teardown" in output
    assert (
        "re-run before changing anything; a single spike under xdist is not a "
        "reason to add `time_limit`, re-mark or rewrite the test — act only if "
        "it fails again."
    ) in output


_NO_TIME_LIMIT_TESTS = """
import subprocess
import time


def test_slow():
    time.sleep(0.7)


def test_git():
    subprocess.run(["git", "--version"], check=True, capture_output=True)
"""


@pytest.mark.time_limit(60, reason="subprocess pytester run; inner test starts git")
def test_no_time_limit_keeps_git_guard(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    _inner(pytester, {"test_git": _NO_TIME_LIMIT_TESTS})

    result = _run_subprocess(pytester, monkeypatch, "-n", "0", "-rA", "--no-time-limit")

    result.assert_outcomes(passed=1, failed=1)
    output = result.stdout.str()
    assert "PASSED test_git.py::test_slow" in output
    assert "test_git.py::test_git started a git process" in output
