"""Tests for the pure classifier functions in _security_probes."""

from unittest.mock import Mock

import pytest
from github import Consts

from mcp_workspace.github_operations._security_probes import (
    _SECURITY_KEYS,
    _classify_security_feature,
    _classify_vulnerability_alerts,
    _probe_dependabot_alerts,
)


class TestClassifyVulnerabilityAlerts:
    """Tests for _classify_vulnerability_alerts."""

    def test_204_is_enabled(self) -> None:
        result = _classify_vulnerability_alerts(204)
        assert result["ok"] is True
        assert result["value"] == "enabled"

    def test_404_is_disabled(self) -> None:
        result = _classify_vulnerability_alerts(404)
        assert result["ok"] is False
        assert result["value"] == "disabled"

    @pytest.mark.parametrize("status", [401, 403, 500])
    def test_other_status_not_accessible(self, status: int) -> None:
        result = _classify_vulnerability_alerts(status)
        assert result["ok"] is None
        assert result["value"] == "not accessible"
        assert f"HTTP {status}" in result["error"]


class TestClassifySecurityFeature:
    """Tests for _classify_security_feature."""

    def test_none_feature_not_accessible(self) -> None:
        result = _classify_security_feature(None, "Dependabot security updates")
        assert result["ok"] is None
        assert result["value"] == "not accessible"
        assert "Dependabot security updates" in result["error"]

    def test_enabled_feature(self) -> None:
        feature = Mock(status="enabled")
        result = _classify_security_feature(feature, "Secret scanning")
        assert result["ok"] is True
        assert result["value"] == "enabled"
        assert "error" not in result

    def test_disabled_feature(self) -> None:
        feature = Mock(status="disabled")
        result = _classify_security_feature(feature, "Secret scanning")
        assert result["ok"] is False
        assert result["value"] == "disabled"


def test_security_keys_order() -> None:
    assert _SECURITY_KEYS == (
        "dependabot_alerts",
        "dependabot_security_updates",
        "secret_scanning",
        "secret_scanning_push_protection",
    )


class TestProbeDependabotAlerts:
    """Tests for _probe_dependabot_alerts."""

    def _make_repo(self) -> Mock:
        repo = Mock()
        repo.url = "https://api.github.com/repos/owner/repo"
        return repo

    def test_204_is_enabled(self) -> None:
        repo = self._make_repo()
        repo.requester.requestJson.return_value = (204, {}, "")
        result = _probe_dependabot_alerts(repo)
        assert result["ok"] is True
        assert result["value"] == "enabled"

    def test_404_is_disabled(self) -> None:
        repo = self._make_repo()
        repo.requester.requestJson.return_value = (404, {}, "")
        result = _probe_dependabot_alerts(repo)
        assert result["ok"] is False
        assert result["value"] == "disabled"

    def test_403_not_accessible(self) -> None:
        repo = self._make_repo()
        repo.requester.requestJson.return_value = (403, {}, "")
        result = _probe_dependabot_alerts(repo)
        assert result["ok"] is None
        assert result["value"] == "not accessible"
        assert "403" in result["error"]

    def test_network_error_not_accessible(self) -> None:
        repo = self._make_repo()
        repo.requester.requestJson.side_effect = ConnectionError("boom")
        result = _probe_dependabot_alerts(repo)
        assert result["ok"] is None
        assert result["value"] == "not accessible"
        assert "boom" in result["error"]

    def test_calls_requestJson_directly_not_get_vulnerability_alert(self) -> None:
        repo = self._make_repo()
        repo.requester.requestJson.return_value = (204, {}, "")
        _probe_dependabot_alerts(repo)
        args, kwargs = repo.requester.requestJson.call_args
        assert args[0] == "GET"
        assert kwargs["headers"]["Accept"] == Consts.vulnerabilityAlertsPreview
        repo.get_vulnerability_alert.assert_not_called()
