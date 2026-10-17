"""Tests for the two-stage startup sequence and fallback error logging."""

import json
import logging
import sys
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _snapshot_logging() -> Generator[None, None, None]:
    """Snapshot and restore root logger handlers/level around each test.

    These tests call the real `setup_logging`, which mutates the root
    logger's handlers in place. The test runner also attaches its own
    `FileHandler` (pointed at the OS null device) to the root logger for
    every test; it is stripped here so `_main()`'s "no file handler
    configured yet" check sees the same starting state as production,
    where no such handler exists. The snapshot is taken before it is
    removed, so the `finally` block restores it afterwards.
    """
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level
    for handler in list(root_logger.handlers):
        if isinstance(handler, logging.FileHandler):
            root_logger.removeHandler(handler)
    try:
        yield
    finally:
        for handler in root_logger.handlers[:]:
            if handler not in original_handlers:
                root_logger.removeHandler(handler)
                handler.close()
        root_logger.handlers[:] = original_handlers
        root_logger.setLevel(original_level)


def test_missing_project_dir_falls_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A missing --project-dir falls back to the startup error log."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["mcp-workspace"])

    from mcp_workspace.main import main

    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1

    fallback = tmp_path / "logs" / "mcp_workspace_startup_error.log"
    assert fallback.exists()
    assert "--project-dir" in fallback.read_text()


def test_invalid_project_dir_falls_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A --project-dir pointing nowhere falls back to the startup error log."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        ["mcp-workspace", "--project-dir", str(tmp_path / "does-not-exist")],
    )

    from mcp_workspace.main import main

    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1

    fallback = tmp_path / "logs" / "mcp_workspace_startup_error.log"
    assert fallback.exists()
    assert "--project-dir" in fallback.read_text()


def test_invalid_log_level_logs_to_normal_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An invalid --log-level is reported in the normal log, not the fallback."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "mcp-workspace",
            "--project-dir",
            str(tmp_path),
            "--log-level",
            "BOGUS",
        ],
    )

    from mcp_workspace.main import main

    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1

    normal_logs = list((tmp_path / "logs").glob("mcp_workspace_*.log"))
    assert len(normal_logs) == 1
    assert "BOGUS" in normal_logs[0].read_text()

    fallback = tmp_path / "logs" / "mcp_workspace_startup_error.log"
    assert not fallback.exists()


def test_invalid_file_size_limit_logs_to_normal_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A non-positive --file-size-limit is reported in the normal log."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "mcp-workspace",
            "--project-dir",
            str(tmp_path),
            "--file-size-limit",
            "0",
        ],
    )

    from mcp_workspace.main import main

    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1

    normal_logs = list((tmp_path / "logs").glob("mcp_workspace_*.log"))
    assert len(normal_logs) == 1
    assert "file-size-limit" in normal_logs[0].read_text()


def test_trailing_log_level_flag_falls_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A trailing bare --log-level fails the pre-parser itself; falls back."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        ["mcp-workspace", "--project-dir", str(tmp_path), "--log-level"],
    )

    from mcp_workspace.main import main

    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1

    fallback = tmp_path / "logs" / "mcp_workspace_startup_error.log"
    assert fallback.exists()
    text = fallback.read_text()
    assert "--log-level" in text
    assert "expected one argument" in text


def test_trailing_project_dir_flag_falls_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A trailing bare --project-dir fails the pre-parser itself; falls back."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["mcp-workspace", "--project-dir"])

    from mcp_workspace.main import main

    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1

    fallback = tmp_path / "logs" / "mcp_workspace_startup_error.log"
    assert fallback.exists()
    text = fallback.read_text()
    assert "--project-dir" in text
    assert "expected one argument" in text


def test_bare_reference_project_flag_logs_to_normal_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A trailing bare --reference-project fails only the full parser."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        ["mcp-workspace", "--project-dir", str(tmp_path), "--reference-project"],
    )

    from mcp_workspace.main import main

    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1

    normal_logs = list((tmp_path / "logs").glob("mcp_workspace_*.log"))
    assert len(normal_logs) == 1
    assert normal_logs[0].read_text().strip() != ""

    fallback = tmp_path / "logs" / "mcp_workspace_startup_error.log"
    assert not fallback.exists()


def test_unwritable_log_dir_falls_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An unwritable project-dir log directory falls back to a writable cwd."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "logs").write_text("not a directory")

    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(
        "sys.argv", ["mcp-workspace", "--project-dir", str(project_dir)]
    )

    from mcp_workspace.main import main

    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1

    fallback = cwd / "logs" / "mcp_workspace_startup_error.log"
    assert fallback.exists()
    text = fallback.read_text()
    assert "Startup failed" in text
    assert "logs" in text
    assert "additionally, invalid --log-level" not in text


def test_invalid_log_level_and_unwritable_log_dir_preserves_both_messages(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An invalid --log-level plus an unwritable log dir reports both problems."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "logs").write_text("not a directory")

    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(
        "sys.argv",
        [
            "mcp-workspace",
            "--project-dir",
            str(project_dir),
            "--log-level",
            "BOGUS",
        ],
    )

    from mcp_workspace.main import main

    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1

    fallback = cwd / "logs" / "mcp_workspace_startup_error.log"
    assert fallback.exists()
    text = fallback.read_text()
    assert "BOGUS" in text
    assert "additionally, invalid --log-level" in text


def test_fallback_log_appends_on_repeated_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Repeated startup failures append to the same fallback log."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["mcp-workspace"])

    from mcp_workspace.main import main

    with pytest.raises(SystemExit):
        main()
    with pytest.raises(SystemExit):
        main()

    fallback = tmp_path / "logs" / "mcp_workspace_startup_error.log"
    text = fallback.read_text()
    assert text.count("--project-dir") >= 2


def test_run_server_crash_logs_traceback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A crash inside run_server() is logged with its traceback."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["mcp-workspace", "--project-dir", str(tmp_path)])

    from mcp_workspace.main import main

    with patch("mcp_workspace.server.run_server", side_effect=RuntimeError("boom")):
        with pytest.raises(SystemExit) as exc_info:
            main()
    assert exc_info.value.code == 1

    normal_logs = list((tmp_path / "logs").glob("mcp_workspace_*.log"))
    assert len(normal_logs) == 1
    text = normal_logs[0].read_text()
    assert "boom" in text
    assert "Traceback" in text


@pytest.mark.parametrize("flag", ["--help", "--version"])
def test_help_and_version_exit_zero_no_log_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, flag: str
) -> None:
    """--help and --version exit 0 without writing any log file."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["mcp-workspace", flag])

    from mcp_workspace.main import main

    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0

    assert not (tmp_path / "logs").exists()


def test_console_only_startup_error_still_writes_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A fatal error with --console-only still gets a fallback log file."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["mcp-workspace", "--console-only"])

    from mcp_workspace.main import main

    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1

    fallback = tmp_path / "logs" / "mcp_workspace_startup_error.log"
    assert fallback.exists()


def test_unknown_argument_is_ignored_and_warned(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An unrecognized flag is ignored, warned, and reported in the INFO line."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "mcp-workspace",
            "--project-dir",
            str(tmp_path),
            "--totally-unknown-flag",
            "value",
        ],
    )

    from mcp_workspace import __version__
    from mcp_workspace.main import main

    with patch("mcp_workspace.server.run_server") as mock_run_server:
        main()

    mock_run_server.assert_called_once()

    normal_logs = list((tmp_path / "logs").glob("mcp_workspace_*.log"))
    assert len(normal_logs) == 1
    text = normal_logs[0].read_text()
    lines = text.splitlines()
    warning_lines = [
        line for line in lines if "WARNING" in line and "--totally-unknown-flag" in line
    ]
    assert len(warning_lines) == 1
    info_lines = [line for line in lines if "INFO" in line and __version__ in line]
    assert len(info_lines) == 1
    assert json.dumps(sys.executable)[1:-1] in info_lines[0]
    assert json.dumps(str(tmp_path))[1:-1] in info_lines[0]


def test_no_unknown_arguments_logs_empty_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With no unrecognized flags, the INFO line lists an empty ignored-args list."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["mcp-workspace", "--project-dir", str(tmp_path)])

    from mcp_workspace.main import main

    with patch("mcp_workspace.server.run_server") as mock_run_server:
        main()

    mock_run_server.assert_called_once()

    normal_logs = list((tmp_path / "logs").glob("mcp_workspace_*.log"))
    assert len(normal_logs) == 1
    text = normal_logs[0].read_text()
    assert "ignored_args=[]" in text


def test_startup_error_goes_to_stderr_not_stdout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Startup error text is written to stderr, never stdout."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "mcp-workspace",
            "--project-dir",
            str(tmp_path),
            "--log-level",
            "BOGUS",
        ],
    )

    from mcp_workspace.main import main

    with pytest.raises(SystemExit):
        main()

    captured = capsys.readouterr()
    assert "BOGUS" in captured.err
    assert captured.out == ""
