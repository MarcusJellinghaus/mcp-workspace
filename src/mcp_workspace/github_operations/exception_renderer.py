"""Render GitHub-related exceptions as single-line strings for display."""

import re

from github.GithubException import GithubException


def render_exception_for_display(exc: Exception) -> str:
    """Render an exception as a single-line string for the [unavailable] section.

    Returns:
        The portion that follows '<section>: '. Truncated at 200 chars
        with '...' appended if exceeded.
    """
    type_name = type(exc).__name__
    if isinstance(exc, GithubException):
        raw = exc.data.get("message") if isinstance(exc.data, dict) else None
        msg = re.sub(r"\s+", " ", raw).strip() if raw else ""
        rendered = f"{type_name} {exc.status}" + (f" — {msg}" if msg else "")
    else:
        msg = re.sub(r"\s+", " ", str(exc)).strip()
        rendered = f"{type_name} — {msg or '(no message)'}"
    return (rendered[:200] + "...") if len(rendered) > 200 else rendered
