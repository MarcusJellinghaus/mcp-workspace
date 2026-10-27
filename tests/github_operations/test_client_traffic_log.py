"""Tests for the traffic-log hooks installed by ``build_github_client``."""

import io
import json
import logging
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
import urllib3
from github.GithubException import GithubException, RateLimitExceededExceedsMaxWait
from github.Requester import Requester
from urllib3.exceptions import ReadTimeoutError

from mcp_workspace.github_operations import _client
from mcp_workspace.github_operations._client import (
    _LoggingGithubRetry,
    build_github_client,
)

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


# --- retry lines: direct ``increment`` calls ---------------------------------

RATE_LIMIT_MESSAGE = "API rate limit exceeded for user ID 1."
NOT_ACCESSIBLE_MESSAGE = "Resource not accessible by integration"


def _stub(
    status: int, headers: dict[str, str] | None = None, message: str = ""
) -> urllib3.HTTPResponse:
    """Build a response stub with a JSON message body."""
    body = io.BytesIO(json.dumps({"message": message}).encode())
    return urllib3.HTTPResponse(
        body=body, headers=headers or {}, status=status, preload_content=False
    )


def _rate_limit_headers() -> dict[str, str]:
    """Headers of a primary rate limit resetting 600s from now."""
    return {
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": str(int(time.time()) + 600),
    }


def test_increment_logs_retry_without_response(log_dir: Path) -> None:
    """A read timeout writes one ``retry ReadTimeoutError`` line without rate data."""
    _LoggingGithubRetry(total=2).increment(
        "GET", "/x", error=ReadTimeoutError(None, "/x", "timed out")  # type: ignore[arg-type]
    )

    lines = _lines(log_dir)
    assert len(lines) == 1
    assert "GET /x | retry ReadTimeoutError | - - | - |" in lines[0]


def test_increment_rate_limit_over_cap_writes_nothing(log_dir: Path) -> None:
    """A primary limit over the wait cap raises and writes no retry line."""
    retry = _LoggingGithubRetry(total=2, max_rate_limit_wait=60)

    with pytest.raises(RateLimitExceededExceedsMaxWait):
        retry.increment(
            "GET", "/x", response=_stub(403, _rate_limit_headers(), RATE_LIMIT_MESSAGE)
        )

    assert not list(log_dir.iterdir())


def test_increment_non_rate_limit_403_writes_nothing(log_dir: Path) -> None:
    """A 403 that is not a rate limit raises and writes no retry line."""
    with pytest.raises(GithubException):
        _LoggingGithubRetry(total=2).increment(
            "GET", "/x", response=_stub(403, message=NOT_ACCESSIBLE_MESSAGE)
        )

    assert not list(log_dir.iterdir())


def test_increment_log_off_writes_no_file(tmp_path: Path) -> None:
    """With the log off (fixture default) a retry writes no file."""
    _LoggingGithubRetry(total=2).increment("GET", "/x", response=_stub(500))

    assert not list(tmp_path.iterdir())


def test_increment_foreign_host_drops_query(log_dir: Path) -> None:
    """A retry on a pool for another host drops the signed query."""
    retry = _LoggingGithubRetry(total=2, api_host="api.github.com")

    retry.increment(
        "GET",
        "/blob?sig=secret",
        response=_stub(500),
        _pool=Mock(host="blob.example.net"),
    )

    content = "\n".join(_lines(log_dir))
    assert "sig=" not in content
    assert "GET /blob | retry 500 |" in content


def test_increment_api_host_keeps_query(log_dir: Path) -> None:
    """A retry on the API host's pool keeps its query."""
    retry = _LoggingGithubRetry(total=2, api_host="api.github.com")

    retry.increment(
        "GET",
        "/x?page=2",
        response=_stub(500, dict(RATE_HEADERS)),
        _pool=Mock(host="api.github.com"),
    )

    lines = _lines(log_dir)
    assert len(lines) == 1
    assert "GET /x?page=2 | retry 500 | core 4211 | - |" in lines[0]


def test_new_keeps_api_host() -> None:
    """``new()`` carries ``api_host`` into the copy."""
    retry = _LoggingGithubRetry(total=2, api_host="api.github.com")

    assert retry.new(total=1).api_host == "api.github.com"


def test_build_github_client_passes_api_host() -> None:
    """The factory derives ``api_host`` from ``base_url``."""
    with patch(f"{MODULE}.Github") as mock_github:
        build_github_client("tok", "https://api.github.com")

    assert mock_github.call_args.kwargs["retry"].api_host == "api.github.com"


# --- end-to-end through urllib3 ----------------------------------------------

Script = list[tuple[int, dict[str, str], dict[str, Any]]]


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[int, Script]]:
    """Serve a scripted sequence of responses on ``127.0.0.1``; yield (port, script)."""
    script: Script = []

    class Handler(BaseHTTPRequestHandler):
        """Pop the next scripted response for every request."""

        def do_GET(self) -> None:  # pylint: disable=invalid-name
            """Answer with the next scripted response."""
            status, headers, body = script.pop(0)
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args: Any) -> None:
            """Keep test output quiet."""

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    try:
        yield httpd.server_address[1], script
    finally:
        httpd.shutdown()
        httpd.server_close()


def _get(port: int) -> Any:
    """Send ``GET /x`` through a real client with backoff sleeps skipped."""
    client = build_github_client("tok", f"http://127.0.0.1:{port}")
    with patch("urllib3.util.retry.time.sleep"):
        return client.requester.requestJsonAndCheck("GET", "/x")


def test_e2e_500_then_200(log_dir: Path, server: tuple[int, Script]) -> None:
    """A retried 500 writes one ``retry 500`` line, then the 200 line."""
    port, script = server
    script.extend([(500, {}, {}), (200, {}, {})])

    _get(port)

    lines = _lines(log_dir)
    assert len(lines) == 2
    assert "GET /x | retry 500 |" in lines[0]
    assert "GET /x | 200 |" in lines[1]


def test_e2e_rate_limit_over_cap(log_dir: Path, server: tuple[int, Script]) -> None:
    """A primary limit over the cap writes one ERR line and no retry line."""
    port, script = server
    script.append((403, _rate_limit_headers(), {"message": RATE_LIMIT_MESSAGE}))

    with pytest.raises(RateLimitExceededExceedsMaxWait):
        _get(port)

    lines = _lines(log_dir)
    assert len(lines) == 1
    assert "GET /x | ERR RateLimitExceededExceedsMaxWait 403 |" in lines[0]


def test_e2e_redirect_then_rate_limit(
    log_dir: Path, server: tuple[int, Script]
) -> None:
    """A 301 hop ending in a rate-limit error writes exactly one ERR line."""
    port, script = server
    script.extend(
        [
            (301, {"Location": f"http://127.0.0.1:{port}/y"}, {}),
            (403, _rate_limit_headers(), {"message": RATE_LIMIT_MESSAGE}),
        ]
    )

    with pytest.raises(RateLimitExceededExceedsMaxWait):
        _get(port)

    lines = _lines(log_dir)
    assert len(lines) == 1
    assert "GET /y | ERR RateLimitExceededExceedsMaxWait 403 |" in lines[0]


def test_e2e_non_rate_limit_403(log_dir: Path, server: tuple[int, Script]) -> None:
    """A 403 that is not a rate limit writes exactly one ERR line."""
    port, script = server
    script.append((403, {}, {"message": NOT_ACCESSIBLE_MESSAGE}))

    with pytest.raises(GithubException):
        _get(port)

    lines = _lines(log_dir)
    assert len(lines) == 1
    status = lines[0].split(" | ")[4]
    assert status.startswith("ERR ")
    assert status.endswith(" 403")
