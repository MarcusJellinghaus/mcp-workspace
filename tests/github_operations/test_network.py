"""Unit tests for the network-diagnostics helper."""

import logging
import socket
from typing import Any

import pytest
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import Timeout as RequestsTimeout

from mcp_workspace.github_operations import _network
from mcp_workspace.github_operations._network import (
    _collect_network_diagnostics,
    _proxy_host_port,
    _tcp_probe,
    maybe_log_network_diagnostics,
)

MODULE = "mcp_workspace.github_operations._network"


def _make_create_connection(exc: BaseException | None) -> Any:
    """Return a fake socket.create_connection raising exc (or returning a stub)."""

    def _fake(*_args: Any, **_kwargs: Any) -> Any:
        if exc is not None:
            raise exc

        class _StubConn:
            def close(self) -> None:
                pass

        return _StubConn()

    return _fake


def test_tcp_probe_dns_error_caught_before_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """gaierror (an OSError subclass) must map to dns_error, not refused."""
    monkeypatch.setattr(
        f"{MODULE}.socket.create_connection",
        _make_create_connection(socket.gaierror("no such host")),
    )
    assert _tcp_probe("api.example.com") == "dns_error"


def test_tcp_probe_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """socket.timeout maps to timeout."""
    monkeypatch.setattr(
        f"{MODULE}.socket.create_connection",
        _make_create_connection(socket.timeout("timed out")),
    )
    assert _tcp_probe("api.example.com") == "timeout"


def test_tcp_probe_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """ConnectionRefusedError maps to refused."""
    monkeypatch.setattr(
        f"{MODULE}.socket.create_connection",
        _make_create_connection(ConnectionRefusedError("refused")),
    )
    assert _tcp_probe("api.example.com") == "refused"


def test_tcp_probe_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """A successful connection maps to ok."""
    monkeypatch.setattr(
        f"{MODULE}.socket.create_connection",
        _make_create_connection(None),
    )
    assert _tcp_probe("api.example.com") == "ok"


def test_proxy_host_port_strips_credentials() -> None:
    """A proxy URL with user:pass@ reduces to host:port without credentials."""
    assert _proxy_host_port("http://user:pass@proxy.corp:8080") == "proxy.corp:8080"


def test_collect_network_diagnostics_strips_proxy_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Collected python_proxies expose host:port only, no credentials."""
    monkeypatch.setattr(
        f"{MODULE}.getproxies",
        lambda: {"https": "http://user:pass@proxy.corp:8080"},
    )
    monkeypatch.setattr(
        f"{MODULE}.socket.create_connection",
        _make_create_connection(None),
    )
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("NO_PROXY", raising=False)

    diag = _collect_network_diagnostics("https://api.example.com")

    assert diag["api_base_url"] == "https://api.example.com"
    assert diag["host"] == "api.example.com"
    assert diag["python_proxies"] == "proxy.corp:8080"
    assert "pass" not in diag["python_proxies"]
    assert diag["proxy_env"] == "none"
    assert diag["tcp_probe"] == "ok"


def test_maybe_log_fires_once_for_connection_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A ConnectionError logs exactly one WARNING across two calls."""
    _network._reset_network_diagnostics_guard()
    monkeypatch.setattr(f"{MODULE}.getproxies", dict)
    monkeypatch.setattr(
        f"{MODULE}.socket.create_connection",
        _make_create_connection(ConnectionRefusedError("refused")),
    )

    with caplog.at_level(logging.WARNING, logger=MODULE):
        maybe_log_network_diagnostics(
            RequestsConnectionError("boom"), "https://api.example.com"
        )
        maybe_log_network_diagnostics(
            RequestsConnectionError("boom again"), "https://api.example.com"
        )

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "GitHub API host unreachable" in warnings[0].getMessage()


def test_maybe_log_fires_for_timeout(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A requests Timeout also triggers the diagnostics line."""
    _network._reset_network_diagnostics_guard()
    monkeypatch.setattr(f"{MODULE}.getproxies", dict)
    monkeypatch.setattr(
        f"{MODULE}.socket.create_connection",
        _make_create_connection(socket.timeout("timed out")),
    )

    with caplog.at_level(logging.WARNING, logger=MODULE):
        maybe_log_network_diagnostics(
            RequestsTimeout("slow"), "https://api.example.com"
        )

    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1


def test_maybe_log_ignores_unrelated_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A non-ConnectionError/Timeout exception logs nothing."""
    _network._reset_network_diagnostics_guard()

    with caplog.at_level(logging.WARNING, logger=MODULE):
        maybe_log_network_diagnostics(
            ValueError("unrelated"), "https://api.example.com"
        )

    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []
