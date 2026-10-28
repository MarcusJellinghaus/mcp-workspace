"""Tests for the opt-in GitHub traffic log writer."""

import re
import subprocess
import sys
import textwrap
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from github import GithubException

from mcp_workspace import traffic_log


def _enable(monkeypatch: pytest.MonkeyPatch, directory: Path) -> None:
    monkeypatch.setattr("mcp_workspace.config.get_traffic_log_dir", lambda: directory)


def _lines(directory: Path) -> list[str]:
    files = list(directory.glob("github_requests_*.log"))
    assert len(files) == 1
    return files[0].read_text(encoding="utf-8").splitlines()


def _define(module: str, source: str, **names: Any) -> dict[str, Any]:
    """Execute ``source`` as if it lived in ``module``; return its namespace."""
    namespace: dict[str, Any] = {"__name__": module, **names}
    exec(textwrap.dedent(source), namespace)  # pylint: disable=exec-used
    return namespace


class TestLogRequestOff:
    """The log is off by default (autouse fixture)."""

    def test_no_file_and_no_chain_walk(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _fail() -> str:
            raise AssertionError("_call_chain must not run when the log is off")

        monkeypatch.setattr(traffic_log, "_call_chain", _fail)
        traffic_log.log_request("GET", "https://api.github.com/x", "200", {}, 0.0)
        assert not list(tmp_path.iterdir())


class TestLogRequestLine:
    """Field layout of one written line."""

    def test_line_fields(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _enable(monkeypatch, tmp_path)
        monkeypatch.setattr(traffic_log, "_command", "vscodeclaude launch")
        monkeypatch.setattr("mcp_workspace.traffic_log.time.monotonic", lambda: 100.182)

        traffic_log.log_request(
            "GET",
            "https://api.github.com/repos/o/r?page=2",
            "200",
            {"x-ratelimit-resource": "core", "x-ratelimit-remaining": "4211"},
            100.0,
        )

        (line,) = _lines(tmp_path)
        fields = line.split(" | ")
        assert len(fields) == 8
        assert re.fullmatch(
            r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}[+-]\d\d:\d\d", fields[0]
        )
        assert fields[1].isdigit()
        assert fields[2:7] == [
            "vscodeclaude launch",
            "GET /repos/o/r?page=2",
            "200",
            "core 4211",
            "182ms",
        ]

    def test_started_none_prints_dash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable(monkeypatch, tmp_path)
        traffic_log.log_request("GET", "/repos/o/r", "retry 502", None, None)
        assert _lines(tmp_path)[0].split(" | ")[6] == "-"

    def test_two_calls_append_to_same_daily_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable(monkeypatch, tmp_path)
        traffic_log.log_request("GET", "/a", "200", None, None)
        traffic_log.log_request("POST", "/b", "201", None, None)
        lines = _lines(tmp_path)
        assert [line.split(" | ")[3] for line in lines] == ["GET /a", "POST /b"]

    def test_unwritable_directory_does_not_raise(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        not_a_dir = tmp_path / "file.txt"
        not_a_dir.write_text("x", encoding="utf-8")
        _enable(monkeypatch, not_a_dir)
        traffic_log.log_request("GET", "/a", "200", None, None)


_WRITER = """
import sys
from pathlib import Path
from mcp_workspace.traffic_log import _append

directory, writer, count = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
for i in range(count):
    _append(directory, "2026-01-01", f"{writer}-{i:04d}-" + "x" * 200)
"""


def test_concurrent_processes_lose_no_lines(tmp_path: Path) -> None:
    """N processes appending to one daily file lose no lines and mix none."""
    processes, count = 8, 200
    children = [
        subprocess.Popen(  # pylint: disable=consider-using-with
            [sys.executable, "-c", _WRITER, str(tmp_path), f"w{n}", str(count)]
        )
        for n in range(processes)
    ]
    for child in children:
        assert child.wait(timeout=120) == 0

    lines = _lines(tmp_path)
    assert len(lines) == processes * count
    assert all(re.fullmatch(r"w\d-\d{4}-x{200}", line) for line in lines)
    assert len(set(lines)) == processes * count


class TestHeaders:
    """Rate-limit header lookup is case-insensitive."""

    @pytest.mark.parametrize(
        ("headers", "expected"),
        [
            ({"x-ratelimit-resource": "core", "x-ratelimit-remaining": "5"}, "core 5"),
            (
                {"X-RateLimit-Resource": "search", "X-RateLimit-Remaining": "9"},
                "search 9",
            ),
            ({"content-type": "application/json"}, "- -"),
            (None, "- -"),
        ],
    )
    def test_resource_remaining(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        headers: dict[str, str] | None,
        expected: str,
    ) -> None:
        _enable(monkeypatch, tmp_path)
        traffic_log.log_request("GET", "/a", "200", headers, None)
        assert _lines(tmp_path)[0].split(" | ")[5] == expected


class TestErrorStatus:
    """``error_status`` formatting."""

    def test_with_status(self) -> None:
        exc = GithubException(403, {"message": "forbidden"}, None)
        assert traffic_log.error_status(exc) == "ERR GithubException 403"

    def test_without_status(self) -> None:
        assert traffic_log.error_status(TimeoutError()) == "ERR TimeoutError"


class TestCallChain:
    """Frame filtering of the call chain."""

    @staticmethod
    def _chain_via(module: str, source: str, entry: str, **names: Any) -> str:
        namespace = _define(module, source, **names)
        func: Callable[[], str] = namespace[entry]
        return func()

    def test_outermost_first_and_foreign_packages_dropped(self) -> None:
        issues = _define(
            "mcp_workspace.github_operations.issues",
            """
            class IssueManager:
                def get_issue(self):
                    return chain()
            """,
            chain=traffic_log._call_chain,  # pylint: disable=protected-access
        )
        utils = _define(
            "mcp_coder_utils.log_utils",
            """
            def logged():
                return IssueManager().get_issue()
            """,
            IssueManager=issues["IssueManager"],
        )
        chain = self._chain_via(
            "mcp_coder.cli.commands",
            """
            def execute():
                return logged()
            """,
            "execute",
            logged=utils["logged"],
        )
        assert chain == "commands.execute > issues.IssueManager.get_issue"

    def test_wrappers_lambdas_comprehensions_dropped(self) -> None:
        chain = self._chain_via(
            "mcp_coder.checks",
            """
            def deco(func):
                def wrapper():
                    return func()
                return wrapper

            @deco
            def check():
                return (lambda: [g for g in (c() for _ in [0])][0])()

            def c():
                return [chain() for _ in [0]][0]
            """,
            "check",
            chain=traffic_log._call_chain,  # pylint: disable=protected-access
        )
        assert chain == "checks.check > checks.c"

    def test_module_frame_dropped(self) -> None:
        namespace = _define(
            "mcp_coder.main",
            "result = chain()",
            chain=traffic_log._call_chain,  # pylint: disable=protected-access
        )
        assert namespace["result"] == ""

    def test_own_modules_dropped(self) -> None:
        inner = _define(
            "mcp_workspace.github_operations._client",
            """
            def wrapped():
                return chain()
            """,
            chain=traffic_log._call_chain,  # pylint: disable=protected-access
        )
        own = _define(
            "mcp_workspace.traffic_log",
            """
            def log():
                return wrapped()
            """,
            wrapped=inner["wrapped"],
        )
        chain = self._chain_via(
            "mcp_workspace.github_operations.pr_manager",
            """
            def get_pr():
                return log()
            """,
            "get_pr",
            log=own["log"],
        )
        assert chain == "pr_manager.get_pr"
