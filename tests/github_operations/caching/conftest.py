"""Shared fixtures for caching tests."""

from pathlib import Path

import pytest

from mcp_workspace.github_operations.caching import _store


@pytest.fixture(autouse=True)
def cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the app-data dir to ``tmp_path`` so no test touches the real one."""
    monkeypatch.setattr(_store, "get_user_app_data_dir", lambda _app: tmp_path)
    return tmp_path
