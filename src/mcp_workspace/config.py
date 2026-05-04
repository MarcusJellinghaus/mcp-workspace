"""Configuration helpers for GitHub token and test repo resolution."""

import os
import tomllib
from typing import Literal

from mcp_coder_utils.user_app_data import get_user_app_data_dir


def _read_config_value(section: str, key: str) -> str | None:
    """Read a value from the user config file."""
    config_path = get_user_app_data_dir("mcp_coder") / "config.toml"
    if not config_path.exists():
        return None
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        return data.get(section, {}).get(key)  # type: ignore[no-any-return]
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        return None


def get_github_token_with_source() -> (
    tuple[str | None, Literal["env", "config"] | None]
):
    """Resolve GitHub token with source: env var → config file → (None, None)."""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return (token, "env")
    token = _read_config_value("github", "token")
    if token:
        return (token, "config")
    return (None, None)


def get_github_token() -> str | None:
    """Resolve GitHub token: env var → config file → None."""
    return get_github_token_with_source()[0]


def get_test_repo_url() -> str | None:
    """Resolve test repo URL: env var → config file → None."""
    url = os.environ.get("GITHUB_TEST_REPO_URL")
    if url:
        return url
    url = _read_config_value("github", "test_repo_url")
    if url:
        return url
    return None
