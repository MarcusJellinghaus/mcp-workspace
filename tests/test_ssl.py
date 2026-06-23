"""Tests for ``mcp_workspace._ssl.ensure_truststore()``."""

import importlib
import logging
import sys
import types
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from mcp_workspace import _ssl


@pytest.fixture(autouse=True)
def _reset_activated_flag() -> Generator[None, None, None]:
    """Reset the module-level ``_activated`` flag before and after each test."""
    _ssl._activated = False
    yield
    _ssl._activated = False


@pytest.fixture
def stub_truststore() -> Generator[MagicMock, None, None]:
    """Install a stub ``truststore`` module exposing a mock ``inject_into_ssl``."""
    original = sys.modules.get("truststore")
    stub = types.ModuleType("truststore")
    inject_mock = MagicMock(name="inject_into_ssl")
    stub.inject_into_ssl = inject_mock  # type: ignore[attr-defined]
    sys.modules["truststore"] = stub
    try:
        yield inject_mock
    finally:
        if original is None:
            sys.modules.pop("truststore", None)
        else:
            sys.modules["truststore"] = original


def test_idempotent_calls_inject_once(stub_truststore: MagicMock) -> None:
    """Calling ``ensure_truststore()`` multiple times invokes inject only once."""
    _ssl.ensure_truststore()
    _ssl.ensure_truststore()
    _ssl.ensure_truststore()

    assert stub_truststore.call_count == 1
    assert _ssl._activated is True


def test_no_op_when_truststore_unavailable(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """When ``truststore`` is not importable, function logs a warning and no-ops."""
    monkeypatch.setitem(sys.modules, "truststore", None)

    with caplog.at_level(logging.WARNING, logger="mcp_workspace._ssl"):
        _ssl.ensure_truststore()

    assert _ssl._activated is False
    assert any(
        "truststore not installed" in record.message for record in caplog.records
    )


def test_import_does_not_activate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-importing ``mcp_workspace._ssl`` must NOT activate truststore."""
    stub = types.ModuleType("truststore")
    inject_mock = MagicMock(name="inject_into_ssl")
    stub.inject_into_ssl = inject_mock  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "truststore", stub)

    reloaded = importlib.reload(_ssl)
    try:
        assert inject_mock.call_count == 0
        assert reloaded._activated is False
    finally:
        importlib.reload(_ssl)


def test_inject_failure_does_not_raise(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """If ``inject_into_ssl()`` raises, the exception is swallowed and logged."""
    stub = types.ModuleType("truststore")

    def boom() -> None:
        raise RuntimeError("nope")

    stub.inject_into_ssl = boom  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "truststore", stub)

    with caplog.at_level(logging.WARNING, logger="mcp_workspace._ssl"):
        _ssl.ensure_truststore()

    assert _ssl._activated is False
    assert any(
        "truststore.inject_into_ssl() failed" in record.message
        and "nope" in record.message
        for record in caplog.records
    )


def test_main_activates_truststore_before_server_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``main()`` activates truststore eagerly, after logging and before the server.

    This is the primary, design-enforced guarantee (issue #212): the entry point
    activates the OS trust store before any TLS handshake can occur, covering
    both PyGithub and the raw ``requests`` download path — independent of how or
    whether any GitHub client is later constructed.
    """
    monkeypatch.setattr(sys, "argv", ["mcp-workspace", "--project-dir", str(tmp_path)])

    parent = Mock()
    mock_setup_logging = MagicMock(name="setup_logging")
    mock_ensure_truststore = MagicMock(name="ensure_truststore")
    mock_run_server = MagicMock(name="run_server")
    parent.attach_mock(mock_setup_logging, "setup_logging")
    parent.attach_mock(mock_ensure_truststore, "ensure_truststore")
    parent.attach_mock(mock_run_server, "run_server")

    with (
        patch("mcp_workspace.main.setup_logging", mock_setup_logging),
        patch("mcp_workspace.main.ensure_truststore", mock_ensure_truststore),
        patch("mcp_workspace.server.run_server", mock_run_server),
    ):
        from mcp_workspace.main import main

        main()

    call_names = [c[0] for c in parent.mock_calls]
    assert call_names.index("setup_logging") < call_names.index("ensure_truststore")
    assert call_names.index("ensure_truststore") < call_names.index("run_server")
