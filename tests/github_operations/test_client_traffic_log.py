"""Tests for the traffic-log wrapper installed by ``build_github_client``."""

import logging
from pathlib import Path
from typing import Any

import pytest
from github.GithubException import GithubException, RateLimitExceededExceedsMaxWait
from github.Requester import Requester

from mcp_workspace.github_operations import _client
from mcp_workspace.github_operations._client import build_github_client

MODULE = "mcp_workspace.github_operations._client"
RAW = "_Requester__requestRaw"
RATE_HEADERS = {"x-ratelimit-resource": "core", "x-ratelimit-remaining": "4211"}


@pytest.fixture
def log_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Turn the traffic log on, writing into ``tmp_path``."""
    monkeypatch.setattr("mcp_workspace.config.get_traffic_log_dir", lambda: tmp_path)
    return tmp_path


def _lines(directory: Path) -> list[str]:
    """Return the lines of the single traffic-log file in ``directory``."""
    files = list(directory.iterdir())
    assert len(files) == 1
    return files[0].read_text(encoding="utf-8").splitlines()


def _request(url: str = "/x", **kwargs: Any) -> Any:
    """Build a client and send one raw request through its requester."""
    client = build_github_client("tok", "https://api.github.com")
    return getattr(client.requester, RAW)(None, "GET", url, {}, None, **kwargs)


def test_installed_pygithub_has_request_raw() -> None:
    """The private name the wrapper relies on exists in the installed PyGithub."""
    assert hasattr(Requester, RAW)


def test_logs_one_line_per_request(
    monkeypatch: pytest.MonkeyPatch, log_dir: Path
) -> None:
    """A 200 writes one line with method, path, status and rate-limit headers."""

    def fake(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self: Requester,
        cnx: Any,
        verb: str,
        url: str,
        requestHeaders: Any,
        input: Any,  # pylint: disable=redefined-builtin
        stream: bool = False,
        follow_302_redirect: bool = False,
    ) -> tuple[int, dict[str, Any], str]:
        return 200, dict(RATE_HEADERS), "body"

    monkeypatch.setattr(Requester, RAW, fake)

    assert _request() == (200, RATE_HEADERS, "body")

    lines = _lines(log_dir)
    assert len(lines) == 1
    assert "GET /x | 200 | core 4211" in lines[0]


def test_logs_each_hop(monkeypatch: pytest.MonkeyPatch, log_dir: Path) -> None:
    """A 301 hop passes the wrapper again: inner hop first, both with the final status."""

    def fake(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self: Requester,
        cnx: Any,
        verb: str,
        url: str,
        requestHeaders: Any,
        input: Any,  # pylint: disable=redefined-builtin
        stream: bool = False,
        follow_302_redirect: bool = False,
    ) -> tuple[int, dict[str, Any], str]:
        if url == "/x":
            result: tuple[int, dict[str, Any], str] = getattr(self, RAW)(
                cnx, verb, "/y", requestHeaders, input
            )
            return result
        return 200, {}, ""

    monkeypatch.setattr(Requester, RAW, fake)

    _request()

    lines = _lines(log_dir)
    assert len(lines) == 2
    assert "GET /y | 200 |" in lines[0]
    assert "GET /x | 200 |" in lines[1]


def test_logs_exception(monkeypatch: pytest.MonkeyPatch, log_dir: Path) -> None:
    """A raised GithubException writes one ERR line and is re-raised."""

    def fake(*args: Any, **kwargs: Any) -> Any:
        raise GithubException(403, {"message": "x"}, {})

    monkeypatch.setattr(Requester, RAW, fake)

    with pytest.raises(GithubException):
        _request()

    lines = _lines(log_dir)
    assert len(lines) == 1
    assert "GET /x | ERR GithubException 403 |" in lines[0]


def test_exception_after_hop_logged_once(
    monkeypatch: pytest.MonkeyPatch, log_dir: Path
) -> None:
    """An exception raised in a hop is logged by the inner wrapper only."""

    def fake(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self: Requester,
        cnx: Any,
        verb: str,
        url: str,
        requestHeaders: Any,
        input: Any,  # pylint: disable=redefined-builtin
        stream: bool = False,
        follow_302_redirect: bool = False,
    ) -> Any:
        if url == "/x":
            return getattr(self, RAW)(cnx, verb, "/y", requestHeaders, input)
        raise RateLimitExceededExceedsMaxWait(403, {"message": "x"}, {})

    monkeypatch.setattr(Requester, RAW, fake)

    with pytest.raises(RateLimitExceededExceedsMaxWait):
        _request()

    lines = _lines(log_dir)
    assert len(lines) == 1
    assert "GET /y | ERR RateLimitExceededExceedsMaxWait" in lines[0]


def test_custom_host_hop_drops_query(
    monkeypatch: pytest.MonkeyPatch, log_dir: Path
) -> None:
    """A 302 hop to another host drops its signed query; the API line keeps its query."""

    def fake(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self: Requester,
        cnx: Any,
        verb: str,
        url: str,
        requestHeaders: Any,
        input: Any,  # pylint: disable=redefined-builtin
        stream: bool = False,
        follow_302_redirect: bool = False,
    ) -> tuple[int, dict[str, Any], str]:
        if cnx is None and url == "/x?archive=zip" and follow_302_redirect:
            result: tuple[int, dict[str, Any], str] = getattr(self, RAW)(
                object(), "GET", "/blob?sig=secret", {}, None, follow_302_redirect=True
            )
            return result
        return 200, {}, ""

    monkeypatch.setattr(Requester, RAW, fake)

    _request("/x?archive=zip", follow_302_redirect=True)

    content = "\n".join(_lines(log_dir))
    assert "sig=" not in content
    assert "GET /blob |" in content
    assert "GET /x?archive=zip | 200 |" in content


def test_not_installed_when_off(tmp_path: Path) -> None:
    """With the log off (fixture default) nothing is wrapped and no file appears."""
    client = build_github_client("tok", "https://api.github.com")

    assert RAW not in vars(client.requester)
    assert not list(tmp_path.iterdir())


def test_missing_private_name_warns_once(
    monkeypatch: pytest.MonkeyPatch,
    log_dir: Path,  # pylint: disable=unused-argument
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If PyGithub drops ``__requestRaw``, warn once and build the client anyway."""
    monkeypatch.setattr(_client, "_warned_missing", False)
    monkeypatch.delattr(Requester, RAW)
    caplog.set_level(logging.WARNING, logger=MODULE)

    build_github_client("tok", "https://api.github.com")
    build_github_client("tok", "https://api.github.com")

    warnings = [
        r for r in caplog.records if r.name == MODULE and "traffic log" in r.message
    ]
    assert len(warnings) == 1


def test_wrapped_requester_is_shared_with_objects(
    monkeypatch: pytest.MonkeyPatch,
    log_dir: Path,  # pylint: disable=unused-argument
) -> None:
    """Objects returned by the client use the same (wrapped) requester instance."""

    def fake(*args: Any, **kwargs: Any) -> tuple[int, dict[str, Any], str]:
        return 200, {}, '{"full_name": "o/r"}'

    monkeypatch.setattr(Requester, RAW, fake)

    client = build_github_client("tok", "https://api.github.com")
    repo = client.get_repo("o/r")

    # pylint: disable=protected-access
    assert repo._requester is client._Github__requester  # type: ignore[attr-defined]
    assert client.requester is client._Github__requester  # type: ignore[attr-defined]
    assert RAW in vars(repo._requester)
