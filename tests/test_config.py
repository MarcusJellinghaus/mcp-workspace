"""Tests for mcp_workspace.config module."""

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_workspace.config import (
    _read_config_list,
    _read_config_value,
    get_github_token,
    get_github_token_with_source,
    get_test_repo_url,
    get_traffic_log_dir,
    get_trusted_commenters,
)


class TestReadConfigValue:
    """Tests for _read_config_value()."""

    def test_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        missing = tmp_path / "config.toml"
        with patch(
            "mcp_workspace.config.get_user_app_data_dir",
            return_value=tmp_path,
        ):
            assert _read_config_value("github", "token") is None

    def test_returns_value_when_present(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('[github]\ntoken = "ghp_test123"\n', encoding="utf-8")
        with patch(
            "mcp_workspace.config.get_user_app_data_dir",
            return_value=tmp_path,
        ):
            assert _read_config_value("github", "token") == "ghp_test123"

    def test_returns_none_for_missing_section(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('[other]\nkey = "value"\n', encoding="utf-8")
        with patch(
            "mcp_workspace.config.get_user_app_data_dir",
            return_value=tmp_path,
        ):
            assert _read_config_value("github", "token") is None

    def test_returns_none_for_missing_key(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('[github]\nother_key = "value"\n', encoding="utf-8")
        with patch(
            "mcp_workspace.config.get_user_app_data_dir",
            return_value=tmp_path,
        ):
            assert _read_config_value("github", "token") is None

    def test_returns_none_for_malformed_toml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text("this is not valid toml {{{}}", encoding="utf-8")
        with patch(
            "mcp_workspace.config.get_user_app_data_dir",
            return_value=tmp_path,
        ):
            assert _read_config_value("github", "token") is None


class TestGetGithubToken:
    """Tests for get_github_token()."""

    def test_returns_env_var_when_set(self) -> None:
        with patch.dict("os.environ", {"GITHUB_TOKEN": "env_token"}):
            assert get_github_token() == "env_token"

    def test_falls_back_to_config_file(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('[github]\ntoken = "file_token"\n', encoding="utf-8")
        with (
            patch.dict("os.environ", {}, clear=True),
            patch(
                "mcp_workspace.config.get_user_app_data_dir",
                return_value=tmp_path,
            ),
        ):
            assert get_github_token() == "file_token"

    def test_env_var_takes_precedence(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('[github]\ntoken = "file_token"\n', encoding="utf-8")
        with (
            patch.dict("os.environ", {"GITHUB_TOKEN": "env_token"}),
            patch(
                "mcp_workspace.config.get_user_app_data_dir",
                return_value=tmp_path,
            ),
        ):
            assert get_github_token() == "env_token"

    def test_returns_none_when_neither_source(self, tmp_path: Path) -> None:
        missing = tmp_path / "config.toml"
        with (
            patch.dict("os.environ", {}, clear=True),
            patch(
                "mcp_workspace.config.get_user_app_data_dir",
                return_value=tmp_path,
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
        config_file.write_text('[github]\ntoken = "file_token"\n', encoding="utf-8")
        with (
            patch.dict("os.environ", {}, clear=True),
            patch(
                "mcp_workspace.config.get_user_app_data_dir",
                return_value=tmp_path,
            ),
        ):
            assert get_github_token_with_source() == ("file_token", "config")

    def test_env_var_takes_precedence(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('[github]\ntoken = "file_token"\n', encoding="utf-8")
        with (
            patch.dict("os.environ", {"GITHUB_TOKEN": "env_token"}),
            patch(
                "mcp_workspace.config.get_user_app_data_dir",
                return_value=tmp_path,
            ),
        ):
            assert get_github_token_with_source() == ("env_token", "env")

    def test_returns_none_when_neither_source(self, tmp_path: Path) -> None:
        missing = tmp_path / "config.toml"
        with (
            patch.dict("os.environ", {}, clear=True),
            patch(
                "mcp_workspace.config.get_user_app_data_dir",
                return_value=tmp_path,
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
                "mcp_workspace.config.get_user_app_data_dir",
                return_value=tmp_path,
            ),
        ):
            assert get_test_repo_url() == "https://github.com/org/testrepo"

    def test_returns_none_when_neither_source(self, tmp_path: Path) -> None:
        missing = tmp_path / "config.toml"
        with (
            patch.dict("os.environ", {}, clear=True),
            patch(
                "mcp_workspace.config.get_user_app_data_dir",
                return_value=tmp_path,
            ),
        ):
            assert get_test_repo_url() is None


def _write_config(tmp_path: Path, text: str) -> None:
    (tmp_path / "config.toml").write_text(text, encoding="utf-8")


class TestReadConfigList:
    """Tests for _read_config_list()."""

    def test_returns_empty_when_file_missing(self, tmp_path: Path) -> None:
        with patch(
            "mcp_workspace.config.get_user_app_data_dir",
            return_value=tmp_path,
        ):
            assert _read_config_list("github", "trusted_commenters") == []

    def test_returns_empty_for_malformed_toml(self, tmp_path: Path) -> None:
        _write_config(tmp_path, "this is not valid toml {{{}}")
        with patch(
            "mcp_workspace.config.get_user_app_data_dir",
            return_value=tmp_path,
        ):
            assert _read_config_list("github", "trusted_commenters") == []

    def test_returns_list_without_empty_entries(self, tmp_path: Path) -> None:
        _write_config(tmp_path, '[github]\ntrusted_commenters = ["a", "", "b"]\n')
        with patch(
            "mcp_workspace.config.get_user_app_data_dir",
            return_value=tmp_path,
        ):
            assert _read_config_list("github", "trusted_commenters") == ["a", "b"]


class TestGetTrustedCommenters:
    """Tests for get_trusted_commenters()."""

    def test_missing_file_returns_empty(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        with (
            caplog.at_level(logging.WARNING, logger="mcp_workspace.config"),
            patch(
                "mcp_workspace.config.get_user_app_data_dir",
                return_value=tmp_path,
            ),
        ):
            assert get_trusted_commenters() == frozenset()
        assert not caplog.records

    def test_missing_key_returns_empty_without_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        _write_config(tmp_path, '[github]\ntoken = "ghp_test"\n')
        with (
            caplog.at_level(logging.WARNING, logger="mcp_workspace.config"),
            patch(
                "mcp_workspace.config.get_user_app_data_dir",
                return_value=tmp_path,
            ),
        ):
            assert get_trusted_commenters() == frozenset()
        assert not caplog.records

    def test_lowercases_and_drops_empty(self, tmp_path: Path) -> None:
        _write_config(
            tmp_path,
            '[github]\ntrusted_commenters = ["Alice", "dependabot[bot]", ""]\n',
        )
        with patch(
            "mcp_workspace.config.get_user_app_data_dir",
            return_value=tmp_path,
        ):
            assert get_trusted_commenters() == frozenset({"alice", "dependabot[bot]"})

    def test_string_value_fails_closed_with_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        _write_config(tmp_path, '[github]\ntrusted_commenters = "alice"\n')
        with (
            caplog.at_level(logging.WARNING, logger="mcp_workspace.config"),
            patch(
                "mcp_workspace.config.get_user_app_data_dir",
                return_value=tmp_path,
            ),
        ):
            assert get_trusted_commenters() == frozenset()
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_non_string_entry_fails_closed_with_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        _write_config(tmp_path, '[github]\ntrusted_commenters = ["alice", 1]\n')
        with (
            caplog.at_level(logging.WARNING, logger="mcp_workspace.config"),
            patch(
                "mcp_workspace.config.get_user_app_data_dir",
                return_value=tmp_path,
            ),
        ):
            assert get_trusted_commenters() == frozenset()
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_env_vars_have_no_effect(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TRUSTED_COMMENTERS", "alice")
        monkeypatch.setenv("GITHUB_TRUSTED_COMMENTERS", "alice")
        with patch(
            "mcp_workspace.config.get_user_app_data_dir",
            return_value=tmp_path,
        ):
            assert get_trusted_commenters() == frozenset()


class TestGetTrafficLogDir:
    """Tests for get_traffic_log_dir()."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self) -> None:
        get_traffic_log_dir.cache_clear()

    def _resolve(self, tmp_path: Path) -> Path | None:
        with patch(
            "mcp_workspace.config.get_user_app_data_dir",
            return_value=tmp_path,
        ):
            return get_traffic_log_dir()

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert self._resolve(tmp_path) is None

    @pytest.mark.parametrize(
        "text",
        [
            "[github]\ntraffic_log = false\n",
            '[github]\ntoken = "ghp_test"\n',
            '[github]\ntraffic_log = "true"\n',
        ],
        ids=["false", "key-missing", "string-true"],
    )
    def test_not_enabled_returns_none(self, tmp_path: Path, text: str) -> None:
        _write_config(tmp_path, text)
        assert self._resolve(tmp_path) is None

    def test_enabled_without_dir_returns_default(self, tmp_path: Path) -> None:
        _write_config(tmp_path, "[github]\ntraffic_log = true\n")
        assert self._resolve(tmp_path) == tmp_path / "logs" / "github_traffic"

    def test_enabled_with_dir_returns_dir(self, tmp_path: Path) -> None:
        _write_config(
            tmp_path, '[github]\ntraffic_log = true\ntraffic_log_dir = "D:/logs/gh"\n'
        )
        assert self._resolve(tmp_path) == Path("D:/logs/gh")

    @pytest.mark.parametrize("value", ["5", '""'], ids=["int", "empty"])
    def test_invalid_dir_returns_default(self, tmp_path: Path, value: str) -> None:
        _write_config(
            tmp_path, f"[github]\ntraffic_log = true\ntraffic_log_dir = {value}\n"
        )
        assert self._resolve(tmp_path) == tmp_path / "logs" / "github_traffic"

    def test_result_is_cached(self, tmp_path: Path) -> None:
        _write_config(tmp_path, "[github]\ntraffic_log = true\n")
        with patch(
            "mcp_workspace.config.get_user_app_data_dir",
            return_value=tmp_path,
        ):
            first = get_traffic_log_dir()
            _write_config(tmp_path, "[github]\ntraffic_log = false\n")
            assert get_traffic_log_dir() == first
        assert first == tmp_path / "logs" / "github_traffic"

    def test_trusted_commenters_stays_uncached(self, tmp_path: Path) -> None:
        _write_config(
            tmp_path, '[github]\ntraffic_log = true\ntrusted_commenters = ["alice"]\n'
        )
        with patch(
            "mcp_workspace.config.get_user_app_data_dir",
            return_value=tmp_path,
        ):
            get_traffic_log_dir()
            assert get_trusted_commenters() == frozenset({"alice"})
            _write_config(
                tmp_path, '[github]\ntraffic_log = true\ntrusted_commenters = ["bob"]\n'
            )
            assert get_trusted_commenters() == frozenset({"bob"})
