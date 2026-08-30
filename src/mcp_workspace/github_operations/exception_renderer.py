"""Render GitHub-related exceptions as single-line strings for display."""

import re

from github.GithubException import GithubException

from ._diagnostics import extract_graphql_errors

_MAX_RENDERED_CHARS = 200
_MAX_GRAPHQL_ERRORS_SHOWN = 2


def _cap(text: str) -> str:
    """Return `text` capped at _MAX_RENDERED_CHARS, with '...' appended if cut."""
    if len(text) > _MAX_RENDERED_CHARS:
        return text[:_MAX_RENDERED_CHARS] + "..."
    return text


def _render_graphql_errors(pairs: list[tuple[str | None, str]]) -> str:
    """Return (type, message) pairs rendered as a single line, status omitted.

    The cap applies per message rather than to the whole line, so the trailing
    '(+N more)' count always survives.
    """
    parts = []
    for err_type, message in pairs[:_MAX_GRAPHQL_ERRORS_SHOWN]:
        msg = _cap(re.sub(r"\s+", " ", message).strip())
        parts.append(
            f"GraphQL {err_type} — {msg}" if err_type else f"GraphQL error — {msg}"
        )
    rendered = "; ".join(parts)
    extra = len(pairs) - _MAX_GRAPHQL_ERRORS_SHOWN
    return rendered + (f" (+{extra} more)" if extra > 0 else "")


def render_exception_for_display(exc: Exception) -> str:
    """Render an exception as a single-line string for the [unavailable] section.

    GraphQL error bodies — an `errors` array with no top-level `message` — are
    rendered from their error entries without the status, which PyGithub
    synthesises for GraphQL and which therefore asserts an HTTP response that
    never happened. Everything else keeps the REST rendering.

    Returns:
        The portion that follows '<section>: '. Truncated at 200 chars with
        '...' appended if exceeded — per message on the GraphQL arm, so the
        '(+N more)' suffix is never cut, and per line elsewhere.
    """
    type_name = type(exc).__name__
    if isinstance(exc, GithubException):
        data = exc.data if isinstance(exc.data, dict) else None
        if data and "errors" in data and "message" not in data:
            pairs = extract_graphql_errors(data)
            if pairs:
                return _render_graphql_errors(pairs)
        raw = data.get("message") if data else None
        msg = re.sub(r"\s+", " ", raw).strip() if raw else ""
        rendered = f"{type_name} {exc.status}" + (f" — {msg}" if msg else "")
    else:
        msg = re.sub(r"\s+", " ", str(exc)).strip()
        rendered = f"{type_name} — {msg or '(no message)'}"
    return _cap(rendered)
