"""Opt-in GitHub traffic log: one line per HTTP request with the caller chain.

Stdlib only (plus ``mcp_workspace.config``): ``main.py`` imports this module and
must not load PyGithub or ``requests``. Never writes tokens, auth headers or
request/response bodies.
"""

import os
import sys
import threading
import time
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from types import FrameType
from typing import Any
from urllib.parse import urlsplit

from mcp_workspace import config

if sys.platform == "win32":
    import msvcrt  # pylint: disable=import-error
else:
    import fcntl  # pylint: disable=import-error

_command = ""
_thread_lock = threading.Lock()

_LOCK_TRIES = 50
_LOCK_WAIT_SECONDS = 0.002

_PACKAGES = frozenset({"mcp_coder", "mcp_workspace"})
_SKIP_MODULES = frozenset(
    {"mcp_workspace.traffic_log", "mcp_workspace.github_operations._client"}
)
_DROP = ("<locals>.wrapper", "<listcomp>", "<genexpr>", "<lambda>", "<module>")


def set_traffic_log_context(command: str) -> None:
    """Register the command name written on every line (set once at startup).

    Args:
        command: Command name, e.g. ``"mcp-workspace server"``.
    """
    global _command  # pylint: disable=global-statement
    _command = command


def log_request(
    method: str,
    url: str,
    status: str,
    headers: Mapping[str, Any] | None,
    started: float | None,
) -> None:
    """Append one traffic line when the log is on. Never raises.

    ``started`` is the caller's ``time.monotonic()`` before the request; the duration
    is computed here. ``None`` (retry lines) prints ``-``.

    Args:
        method: HTTP method.
        url: Absolute URL or path; the host is stripped, the query kept.
        status: Status text, e.g. ``"200"``, ``"retry 502"`` or ``"ERR ..."``.
        headers: Response headers, or None when there is no response.
        started: ``time.monotonic()`` taken before the request, or None.
    """
    directory = config.get_traffic_log_dir()
    if directory is None:
        return
    try:
        now = datetime.now().astimezone()
        parts = urlsplit(url)
        path = parts.path + ("?" + parts.query if parts.query else "")
        duration = (
            f"{round((time.monotonic() - started) * 1000)}ms"
            if started is not None
            else "-"
        )
        rate = (
            f"{_header(headers, 'x-ratelimit-resource')} "
            f"{_header(headers, 'x-ratelimit-remaining')}"
        )
        line = " | ".join(
            [
                now.isoformat(timespec="milliseconds"),
                str(os.getpid()),
                _command,
                f"{method} {path}",
                status,
                rate,
                duration,
                _call_chain(),
            ]
        )
        _append(directory, now.strftime("%Y-%m-%d"), line)
    except Exception:  # pylint: disable=broad-exception-caught
        pass


def error_status(exc: BaseException) -> str:
    """Return ``ERR <Type>`` plus `` <status>`` when ``exc.status`` is an int.

    Args:
        exc: The exception raised by the request.

    Returns:
        Status text for the traffic line.
    """
    text = f"ERR {type(exc).__name__}"
    status = getattr(exc, "status", None)
    if isinstance(status, int):
        text += f" {status}"
    return text


def _call_chain() -> str:
    """Return the caller chain of our own packages, outermost first."""
    frame: FrameType | None = sys._getframe(1)  # pylint: disable=protected-access
    names: list[str] = []
    while frame is not None:
        module = frame.f_globals.get("__name__", "")
        qual = frame.f_code.co_qualname
        if (
            module.partition(".")[0] in _PACKAGES
            and module not in _SKIP_MODULES
            and not any(drop in qual for drop in _DROP)
        ):
            names.append(f"{module.rpartition('.')[2]}.{qual}")
        frame = frame.f_back
    return " > ".join(reversed(names))


def _header(headers: Mapping[str, Any] | None, name: str) -> str:
    """Return header ``name`` (case-insensitive), or ``-`` if missing."""
    for key, value in (headers or {}).items():
        if str(key).lower() == name:
            return str(value)
    return "-"


def _try_lock(fd: int) -> bool:
    """Take the non-blocking file lock, retrying briefly.

    Returns:
        True when the lock is held, False when it could not be taken.
    """
    for _ in range(_LOCK_TRIES):
        try:
            if sys.platform == "win32":
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            time.sleep(_LOCK_WAIT_SECONDS)
    return False


def _unlock(fd: int) -> None:
    """Release the file lock taken by ``_try_lock``."""
    if sys.platform == "win32":
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)


def _append(directory: Path, day: str, line: str) -> None:
    """Append ``line`` to the daily file in one ``os.write`` under a thread and file lock.

    Windows ``O_APPEND`` is not atomic across processes (seek, then write), so
    the file lock keeps concurrent writers from overwriting each other's lines.
    Skips the line when the file lock cannot be taken.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"github_requests_{day}.log"
    data = (line + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0)
    with _thread_lock:
        fd = os.open(path, flags)
        try:
            if not _try_lock(fd):
                return
            try:
                os.write(fd, data)
            finally:
                _unlock(fd)
        finally:
            os.close(fd)
