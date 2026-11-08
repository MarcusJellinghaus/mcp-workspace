"""Remove credentials embedded in URLs before text leaves the server."""

import re

_USERINFO_RE = re.compile(r"(?<=://)[^/@\s]+@")


def scrub_credentials(text: str) -> str:
    """Remove userinfo ('user:token@') from every URL in text.

    Returns:
        ``text`` with userinfo stripped from every URL.
    """
    return _USERINFO_RE.sub("", text)
