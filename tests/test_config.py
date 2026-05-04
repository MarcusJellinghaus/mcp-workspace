"""Tests for mcp_workspace.config module."""

from pathlib import Path
from unittest.mock import patch

from mcp_workspace.config import (
    _read_config_value,
    get_github_token,
    get_github_token_with_source,
    get_test_repo_url,
)


class TestReadConfigValue:
    """Tests for _read_config_value()."""

    def test_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        missing = tmp_path / "config.toml"
        with patch(
            "mcp_workspace.config.get_user_config_path",
            return_value=missing,
        ):
            assert _read_config_value("github", "token") is None

    def test_returns_value_when_present(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[github]\ntoken = "ghp_test123"\n', encoding="utf-8"
        )
        with patch(
            "mcp_workspace.config.get_user_config_path",
            return_value=config_file,
        ):
            assert _read_config_value("github", "token") == "ghp_test123"

    def test_returns_none_for_missing_section(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('[other]\nkey = "value"\n', encoding="utf-8")
        with patch(
            "mcp_workspace.config.get_user_config_path",
            return_value=config_file,
        ):
            assert _read_config_value("github", "token") is None

    def test_returns_none_for_missing_key(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[github]\nother_key = "value"\n', encoding="utf-8"
        )
        with patch(
            "mcp_workspace.config.get_user_config_path",
            return_value=config_file,
        ):
            assert _read_config_value("github", "token") is None

    def test_returns_none_for_malformed_toml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text("this is not valid toml {{{}}", encoding="utf-8")
        with patch(
            "mcp_workspace.config.get_user_config_path",
            return_value=config_file,
        ):
            assert _read_config_value("github", "token") is None


class TestGetGithubToken:
    """Tests for get_github_token()."""

    def test_returns_env_var_when_set(self) -> None:
        with patch.dict("os.environ", {"GITHUB_TOKEN": "env_token"}):
            assert get_github_token() == "env_token"

    def test_falls_back_to_config_file(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[github]\ntoken = "file_token"\n', encoding="utf-8"
        )
        with (
            patch.dict("os.environ", {}, clear=True),
            patch(
                "mcp_workspace.config.get_user_config_path",
                return_value=config_file,
            ),
        ):
            assert get_github_token() == "file_token"

    def test_env_var_takes_precedence(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[github]\ntoken = "file_token"\n', encoding="utf-8"
        )
        with (
            patch.dict("os.environ", {"GITHUB_TOKEN": "env_token"}),
            patch(
                "mcp_workspace.config.get_user_config_path",
                return_value=config_file,
            ),
        ):
            assert get_github_token() == "env_token"

    def test_returns_none_when_neither_source(self, tmp_path: Path) -> None:
        missing = tmp_path / "config.toml"
        with (
            patch.dict("os.environ", {}, clear=True),
            patch(
                "mcp_workspace.config.get_user_config_path",
                return_value=missing,
            ),
        ):
            assert get_github_token() is None


class TestGetGithubTokenWithSource:
    """Tests for get_github_token_with_source()."""

    def test_returns_env_var_when_set(self) -> None:
        with patch.dict("os.environ", {"GITHUB_TOKEN": "env_token"}):
            assert get_github_token_with_source() == ("env_token", "env")

    def test_falls_back_to_config_file(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[github]\ntoken = "file_token"\n', encoding="utf-8"
        )
        with (
            patch.dict("os.environ", {}, clear=True),
            patch(
                "mcp_workspace.config.get_user_config_path",
                return_value=config_file,
            ),
        ):
            assert get_github_token_with_source() == ("file_token", "config")

    def test_env_var_takes_precedence(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[github]\ntoken = "file_token"\n', encoding="utf-8"
        )
        with (
            patch.dict("os.environ", {"GITHUB_TOKEN": "env_token"}),
            patch(
                "mcp_workspace.config.get_user_config_path",
                return_value=config_file,
            ),
        ):
            assert get_github_token_with_source() == ("env_token", "env")

    def test_returns_none_when_neither_source(self, tmp_path: Path) -> None:
        missing = tmp_path / "config.toml"
        with (
            patch.dict("os.environ", {}, clear=True),
            patch(
                "mcp_workspace.config.get_user_config_path",
                return_value=missing,
            ),
        ):
            assert get_github_token_with_source() == (None, None)


class TestGetTestRepoUrl:
    """Tests for get_test_repo_url()."""

    def test_returns_env_var_when_set(self) -> None:
        with patch.dict(
            "os.environ", {"GITHUB_TEST_REPO_URL": "https://github.com/org/repo"}
        ):
            assert get_test_repo_url() == "https://github.com/org/repo"

    def test_falls_back_to_config_file(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[github]\ntest_repo_url = "https://github.com/org/testrepo"\n',
            encoding="utf-8",
        )
        with (
            patch.dict("os.environ", {}, clear=True),
            patch(
                "mcp_workspace.config.get_user_config_path",
                return_value=config_file,
            ),
        ):
            assert get_test_repo_url() == "https://github.com/org/testrepo"

    def test_returns_none_when_neither_source(self, tmp_path: Path) -> None:
        missing = tmp_path / "config.toml"
        with (
            patch.dict("os.environ", {}, clear=True),
            patch(
                "mcp_workspace.config.get_user_config_path",
                return_value=missing,
            ),
        ):
            assert get_test_repo_url() is None
