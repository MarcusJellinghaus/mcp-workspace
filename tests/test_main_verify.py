"""Tests for the ``mcp-workspace verify`` dispatch and parser in main."""

import json
import logging
import os
import subprocess
import sys
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mcp_workspace.main import _main, main

# Exercise the code under test from ``src`` (matching pytest's
# pythonpath=["src"]), never an installed copy in site-packages.
SRC_DIR = str(Path(__file__).resolve().parent.parent / "src")

_EXECUTE_VERIFY = "mcp_workspace.cli.verify.execute_verify"
_FALLBACK = Path("logs") / "mcp_workspace_startup_error.log"


@pytest.fixture(autouse=True)
def _snapshot_logging() -> Generator[None, None, None]:
    """Restore the root logger's handlers and level after each test.

    ``main`` calls the real ``setup_logging``, which replaces root handlers.
    """
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level
    try:
        yield
    finally:
        for handler in root_logger.handlers[:]:
            if handler not in original_handlers:
                root_logger.removeHandler(handler)
                handler.close()
        root_logger.handlers[:] = original_handlers
        root_logger.setLevel(original_level)


def _run_main(monkeypatch: pytest.MonkeyPatch, *args: str) -> int | str | None:
    """Run ``main()`` with ``args`` as the command line; return the exit code."""
    monkeypatch.setattr("sys.argv", ["mcp-workspace", *args])
    with pytest.raises(SystemExit) as exc_info:
        main()
    return exc_info.value.code


class TestVerifyDispatch:
    """``mcp-workspace verify`` runs execute_verify and exits with its code."""

    @pytest.mark.parametrize("code", [0, 1])
    def test_exit_code_from_execute_verify(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, code: int
    ) -> None:
        """The exit code is execute_verify's return value."""
        with patch(_EXECUTE_VERIFY, return_value=code) as mock_verify:
            exit_code = _run_main(
                monkeypatch,
                "verify",
                "--project-dir",
                str(tmp_path),
                "--reference-project",
                "name=broken",
            )
        assert exit_code == code
        mock_verify.assert_called_once_with(
            tmp_path.resolve(), {}, [("broken", "missing path")]
        )

    def test_project_dir_defaults_to_cwd(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Without --project-dir the current directory is verified."""
        monkeypatch.chdir(tmp_path)
        with patch(_EXECUTE_VERIFY, return_value=0) as mock_verify:
            assert _run_main(monkeypatch, "verify") == 0
        assert mock_verify.call_args.args[0] == tmp_path.resolve()

    def test_invalid_project_dir(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A missing --project-dir exits 1 with Error: and no fallback log."""
        monkeypatch.chdir(tmp_path)
        missing = str(tmp_path / "does-not-exist")
        assert _run_main(monkeypatch, "verify", "--project-dir", missing) == 1
        err = capsys.readouterr().err
        assert err.startswith("Error: ")
        assert "--project-dir" in err
        assert not (tmp_path / _FALLBACK).exists()

    def test_unusable_cwd_names_cwd(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """An unusable cwd is reported by its path, not as None."""
        monkeypatch.chdir(tmp_path)
        with patch("mcp_workspace.main._resolve_project_dir", return_value=None):
            assert _run_main(monkeypatch, "verify") == 1
        err = capsys.readouterr().err
        assert err.startswith("Error: ")
        assert repr(str(Path.cwd())) in err
        assert "None" not in err

    def test_execute_verify_raising(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """An exception from execute_verify exits 1 with Error:."""
        with patch(_EXECUTE_VERIFY, side_effect=RuntimeError("boom")):
            exit_code = _run_main(monkeypatch, "verify", "--project-dir", str(tmp_path))
        assert exit_code == 1
        assert "Error: boom" in capsys.readouterr().err

    def test_url_mismatch(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A reference URL mismatch exits 1 with Error:."""
        ref_dir = tmp_path / "ref"
        ref_dir.mkdir()
        workspace = tmp_path / "ws"
        workspace.mkdir()
        with (
            patch(
                "mcp_workspace.main.detect_and_verify_url",
                side_effect=ValueError("URL mismatch for 'ref'"),
            ),
            patch(_EXECUTE_VERIFY, return_value=0) as mock_verify,
        ):
            exit_code = _run_main(
                monkeypatch,
                "verify",
                "--project-dir",
                str(workspace),
                "--reference-project",
                f"name=ref,path={ref_dir},url=https://github.com/o/r",
            )
        assert exit_code == 1
        assert "Error: URL mismatch" in capsys.readouterr().err
        mock_verify.assert_not_called()


class TestVerifyParser:
    """The verify parser is strict and separate from the server parser."""

    def test_unknown_option_exits_2(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A server-only option after verify is a usage error."""
        monkeypatch.chdir(tmp_path)
        with patch(_EXECUTE_VERIFY, return_value=0) as mock_verify:
            assert _run_main(monkeypatch, "verify", "--log-file", "x") == 2
        mock_verify.assert_not_called()

    def test_log_level_case_insensitive(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """--log-level is upper-cased and logging goes to the console only."""
        with (
            patch("mcp_workspace.main.setup_logging") as mock_setup,
            patch(_EXECUTE_VERIFY, return_value=0),
        ):
            exit_code = _run_main(
                monkeypatch,
                "verify",
                "--project-dir",
                str(tmp_path),
                "--log-level",
                "debug",
            )
        assert exit_code == 0
        mock_setup.assert_called_once_with("DEBUG", None)

    def test_invalid_log_level_exits_2(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """An unknown --log-level is a usage error."""
        exit_code = _run_main(
            monkeypatch, "verify", "--project-dir", str(tmp_path), "--log-level", "nope"
        )
        assert exit_code == 2

    def test_verify_help(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """verify --help shows the verify parser, not the server's."""
        assert _run_main(monkeypatch, "verify", "--help") == 0
        out = capsys.readouterr().out
        assert "mcp-workspace verify" in out
        assert "--reference-project" in out
        assert "MCP File System Server" not in out

    def test_server_help_mentions_verify(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The server --help points at the verify subcommand."""
        assert _run_main(monkeypatch, "--help") == 0
        assert "mcp-workspace verify --help" in capsys.readouterr().out


class TestServerModeWithVerifyToken:
    """``verify`` is only a subcommand in first position."""

    @pytest.mark.parametrize(
        "args",
        [
            pytest.param(["--project-dir", "<tmp>", "verify"], id="with-project-dir"),
            pytest.param(["--log-level", "DEBUG", "verify"], id="no-project-dir"),
        ],
    )
    def test_verify_not_first(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, args: list[str]
    ) -> None:
        """verify later on the command line is rejected before startup checks."""
        monkeypatch.chdir(tmp_path)
        argv = [str(tmp_path) if a == "<tmp>" else a for a in args]
        monkeypatch.setattr("sys.argv", ["mcp-workspace", *argv])
        with pytest.raises(ValueError, match="verify must be the first argument"):
            _main()

    def test_stray_positional_still_starts_server(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Other unknown tokens are only warned about, as before."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "sys.argv", ["mcp-workspace", "--project-dir", str(tmp_path), "stray"]
        )
        with (
            patch("mcp_workspace.server.run_server") as mock_run_server,
            patch("mcp_workspace.main.stdlogger") as mock_logger,
        ):
            main()
        mock_run_server.assert_called_once()
        warnings: list[MagicMock] = mock_logger.warning.call_args_list
        assert any("stray" in call.args for call in warnings)


def test_main_import_does_not_load_verify_dependencies() -> None:
    """Importing main must not pull in git, github, yaml or the cli package."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = SRC_DIR + (os.pathsep + existing if existing else "")
    modules = ["git", "github", "yaml", "mcp_workspace.cli"]
    code = (
        "import sys, json, mcp_workspace.main as m; "
        f"print(json.dumps({{'file': m.__file__, 'loaded': "
        f"[n for n in {modules!r} if n in sys.modules]}}))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, f"subprocess failed:\n{proc.stderr}"
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    assert SRC_DIR in data["file"], f"tested wrong copy: {data['file']}"
    assert data["loaded"] == []
