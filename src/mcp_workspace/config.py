"""Configuration helpers for GitHub token and test repo resolution."""

import functools
import logging
import os
import tomllib
from pathlib import Path
from typing import Any, Literal

from mcp_coder_utils.user_app_data import get_user_app_data_dir

logger = logging.getLogger(__name__)


def _load_config() -> dict[str, Any]:
    """Load the user config file.

    Returns:
        The parsed TOML data, or an empty dict if the file is missing
        or unreadable.
    """
    config_path = get_user_app_data_dir("mcp_coder") / "config.toml"
    if not config_path.exists():
        return {}
    try:
        return tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        return {}


def _read_config_list(section: str, key: str) -> list[str]:
    """Read a list of strings from the user config file.

    Fails closed: a value that is not a list of strings logs a warning
    and yields an empty list. Empty strings are dropped.

    Returns:
        The configured strings, or an empty list if missing or invalid.
    """
    section_data = _load_config().get(section, {})
    value = section_data.get(key) if isinstance(section_data, dict) else None
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        logger.warning(
            "Ignoring [%s] %s in config.toml: expected a list of strings",
            section,
            key,
        )
        return []
    return [v for v in value if v]


def get_trusted_commenters() -> frozenset[str]:
    """Read the commenter allowlist from ``[github] trusted_commenters``.

    Read from the user config file on every call; no env-var override, so
    a repo or PR cannot add itself.

    Returns:
        Lowercased logins, or an empty set if missing or invalid.
    """
    return frozenset(
        v.lower() for v in _read_config_list("github", "trusted_commenters")
    )


@functools.cache
def get_traffic_log_dir() -> Path | None:
    """Resolve the GitHub traffic log directory from ``[github]`` once per process.

    ``traffic_log`` must be the boolean ``true``; any other value turns the
    log off. A missing, empty or non-string ``traffic_log_dir`` falls back to
    the default directory. Callers use ``config.get_traffic_log_dir()`` via
    the module attribute, so tests can replace it.

    Returns:
        The directory when ``traffic_log = true``, else None (log off).
    """
    section = _load_config().get("github", {})
    if not isinstance(section, dict) or section.get("traffic_log") is not True:
        return None
    value = section.get("traffic_log_dir")
    if isinstance(value, str) and value:
        return Path(value)
    return get_user_app_data_dir("mcp_coder") / "logs" / "github_traffic"


def _read_config_value(section: str, key: str) -> str | None:
    """Read a value from the user config file.

    Returns:
        The configured value, or None if the file or key is missing
        or unreadable.
    """
    section_data = _load_config().get(section, {})
    if not isinstance(section_data, dict):
        return None
    return section_data.get(key)


def get_github_token_with_source() -> (
    tuple[str | None, Literal["env", "config"] | None]
):
    """Resolve GitHub token and its source: env var, then config file.

    Returns:
        Tuple of (token, source) where source is "env" or "config",
        or (None, None) if no token is found.
    """
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return (token, "env")
    token = _read_config_value("github", "token")
    if token:
        return (token, "config")
    return (None, None)


def get_github_token() -> str | None:
    """Resolve GitHub token: env var, then config file.

    Returns:
        The token string, or None if not configured.
    """
    return get_github_token_with_source()[0]


def get_test_repo_url() -> str | None:
    """Resolve test repo URL: env var, then config file.

    Returns:
        The URL string, or None if not configured.
    """
    url = os.environ.get("GITHUB_TEST_REPO_URL")
    if url:
        return url
    url = _read_config_value("github", "test_repo_url")
    if url:
        return url
    return None
