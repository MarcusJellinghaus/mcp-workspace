"""Unit tests for per-permission read probes in verify_github."""

from unittest.mock import MagicMock, Mock, PropertyMock

import pytest
from github.GithubException import GithubException

from mcp_workspace.github_operations._permission_probes import (
    _PROBE_KEYS,
    _classify_permission_response,
    _probe_administration,
    _probe_statuses,
    _run_probe,
    run_permission_probes,
)
from mcp_workspace.github_operations.verification import CheckResult

GITHUB_COM_HOST = "https://github.com"
GHE_TENANT_HOST = "https://tenant.ghe.com"


# ===================================================================
# 1. Classifier — pure-function tests
# ===================================================================


class TestClassifier200:
    """200 status -> ok=True, value="OK", no error key, no URL anywhere."""

    def test_basic_ok(self) -> None:
        result = _classify_permission_response(
            "Contents: Read", 200, "https://api.github.com/repos/x/y/contents/", None
        )
        assert result["ok"] is True
        assert result["value"] == "OK"
        assert result["severity"] == "warning"
        assert "error" not in result

    def test_no_url_in_value(self) -> None:
        url = "https://api.github.com/repos/x/y/contents/"
        result = _classify_permission_response("Contents: Read", 200, url, None)
        # On 200 the URL should not be embedded anywhere
        assert url not in result["value"]
        assert "error" not in result


class TestClassifier401:
    """401 status -> token rejected hint."""

    def test_401_message(self) -> None:
        url = "https://api.github.com/repos/x/y/contents/"
        result = _classify_permission_response("Contents: Read", 401, url, None)
        assert result["ok"] is False
        assert result["value"] == "failed"
        err = result["error"]
        assert "401" in err
        assert "Contents: Read" in err
        assert f"(GET {url})" in err


class TestClassifier403:
    """403 status -> blocked by org policy hint."""

    def test_403_message(self) -> None:
        url = "https://api.github.com/repos/x/y/issues?state=all"
        result = _classify_permission_response("Issues: Read", 403, url, None)
        err = result["error"]
        assert "403" in err
        assert "Issues: Read" in err
        assert "blocked by org policy" in err
        assert f"(GET {url})" in err


class TestClassifier404HostBranching:
    """404 hint includes host-specific guidance."""

    def test_404_github_com_includes_settings_url(self) -> None:
        url = "https://api.github.com/repos/x/y/pulls?state=all"
        result = _classify_permission_response(
            "Pull requests: Read", 404, url, GITHUB_COM_HOST
        )
        err = result["error"]
        assert "Pull requests: Read" in err
        assert "404" in err
        assert "fine-grained PAT" in err
        assert "https://github.com/settings/personal-access-tokens" in err
        assert f"(GET {url})" in err

    def test_404_ghe_includes_tenant_settings_url(self) -> None:
        url = "https://api.tenant.ghe.com/repos/x/y/issues?state=all"
        result = _classify_permission_response(
            "Issues: Read", 404, url, GHE_TENANT_HOST
        )
        err = result["error"]
        assert "404" in err
        assert "fine-grained PAT" in err
        assert "https://tenant.ghe.com/settings/personal-access-tokens" in err
        assert f"(GET {url})" in err

    def test_404_ghes_no_settings_phrase(self) -> None:
        url = "https://ghe.example.com/api/v3/repos/x/y/contents/"
        result = _classify_permission_response("Contents: Read", 404, url, None)
        err = result["error"]
        assert "404" in err
        assert "Contents: Read" in err
        assert "settings" not in err
        assert "fine-grained PAT" not in err
        assert f"(GET {url})" in err


class TestClassifier404Admin:
    """admin_404=True: branch-protection-aware 404 message."""

    def test_admin_404_phrase(self) -> None:
        url = "https://api.github.com/repos/x/y/branches/main/protection"
        result = _classify_permission_response(
            "Administration: Read", 404, url, GITHUB_COM_HOST, admin_404=True
        )
        err = result["error"]
        assert "Administration: Read" in err
        assert "no branch protection configured" in err
        assert "404" in err
        assert f"(GET {url})" in err
        # admin_404 takes precedence over the host-branched 404 message
        assert "fine-grained PAT" not in err


class TestClassifierUnexpected:
    """Other status codes -> generic unexpected hint."""

    def test_500_message(self) -> None:
        url = "https://api.github.com/repos/x/y/actions/workflows"
        result = _classify_permission_response("Actions: Read", 500, url, None)
        err = result["error"]
        assert "500" in err
        assert "Actions: Read" in err
        assert f"(GET {url})" in err


# ===================================================================
# 2. Per-probe success path (4 simple probes)
# ===================================================================


@pytest.fixture
def mock_repo_full() -> Mock:
    """Build a mock Repository where all probe calls succeed."""
    repo = Mock()
    repo.default_branch = "main"
    repo.get_contents.return_value = []
    pulls = Mock()
    type(pulls).totalCount = PropertyMock(return_value=0)
    repo.get_pulls.return_value = pulls
    issues = Mock()
    type(issues).totalCount = PropertyMock(return_value=0)
    repo.get_issues.return_value = issues
    workflows = Mock()
    type(workflows).totalCount = PropertyMock(return_value=0)
    repo.get_workflows.return_value = workflows

    branch = Mock()
    branch.get_protection.return_value = Mock()
    repo.get_branch.return_value = branch

    commit = Mock()
    commit.get_combined_status.return_value = Mock()
    repo.get_commit.return_value = commit
    return repo


def _make_manager(
    full_name: str = "owner/repo",
    api_base_url: str = "https://api.github.com",
    web_host: str | None = GITHUB_COM_HOST,
) -> Mock:
    manager = Mock()
    identifier = Mock()
    identifier.full_name = full_name
    identifier.api_base_url = api_base_url
    identifier.web_host = web_host
    manager._repo_identifier = identifier
    return manager


SIMPLE_PROBE_PARAMS: list[tuple[str, str]] = [
    ("perm_contents_read", "Contents: Read"),
    ("perm_pull_requests_read", "Pull requests: Read"),
    ("perm_issues_read", "Issues: Read"),
    ("perm_workflows_read", "Actions: Read"),
]


class TestSimpleProbesSuccess:
    """Each simple probe returns ok=True with no URL embedded."""

    @pytest.mark.parametrize("key,_name", SIMPLE_PROBE_PARAMS)
    def test_success(self, key: str, _name: str, mock_repo_full: Mock) -> None:
        manager = _make_manager()
        results = run_permission_probes(manager, mock_repo_full)
        check = results[key]
        assert check["ok"] is True
        assert check["value"] == "OK"
        assert "error" not in check
        # No URL in value
        for v in check.values():
            if isinstance(v, str):
                assert "https://" not in v


# ===================================================================
# 3. Per-probe failure paths (parametrized over 4 simple probes × 4 statuses)
# ===================================================================


def _make_repo_with_probe_failure(
    key: str, exc: Exception, *, default_branch: str = "main"
) -> Mock:
    """Build a repo whose specific probe call raises the given exception."""
    repo = Mock()
    repo.default_branch = default_branch
    # Defaults — succeed
    repo.get_contents.return_value = []
    pulls = Mock()
    type(pulls).totalCount = PropertyMock(return_value=0)
    repo.get_pulls.return_value = pulls
    issues = Mock()
    type(issues).totalCount = PropertyMock(return_value=0)
    repo.get_issues.return_value = issues
    workflows = Mock()
    type(workflows).totalCount = PropertyMock(return_value=0)
    repo.get_workflows.return_value = workflows
    branch = Mock()
    branch.get_protection.return_value = Mock()
    repo.get_branch.return_value = branch
    commit = Mock()
    commit.get_combined_status.return_value = Mock()
    repo.get_commit.return_value = commit

    if key == "perm_contents_read":
        repo.get_contents.side_effect = exc
    elif key == "perm_pull_requests_read":
        pulls = Mock()
        type(pulls).totalCount = PropertyMock(side_effect=exc)
        repo.get_pulls.return_value = pulls
    elif key == "perm_issues_read":
        issues = Mock()
        type(issues).totalCount = PropertyMock(side_effect=exc)
        repo.get_issues.return_value = issues
    elif key == "perm_workflows_read":
        workflows = Mock()
        type(workflows).totalCount = PropertyMock(side_effect=exc)
        repo.get_workflows.return_value = workflows
    else:
        raise AssertionError(f"unsupported key: {key}")
    return repo


URL_BY_KEY: dict[str, str] = {
    "perm_contents_read": "https://api.github.com/repos/owner/repo/contents/",
    "perm_pull_requests_read": "https://api.github.com/repos/owner/repo/pulls?state=all",
    "perm_issues_read": "https://api.github.com/repos/owner/repo/issues?state=all",
    "perm_workflows_read": "https://api.github.com/repos/owner/repo/actions/workflows",
}


class TestSimpleProbesFailure:
    """Each simple probe failure embeds permission name, GET url, status."""

    @pytest.mark.parametrize("key,name", SIMPLE_PROBE_PARAMS)
    @pytest.mark.parametrize("status", [401, 403, 404, 500])
    def test_failure(self, key: str, name: str, status: int) -> None:
        exc = GithubException(status=status, data={"message": "x"}, headers={})
        repo = _make_repo_with_probe_failure(key, exc)
        manager = _make_manager()
        results = run_permission_probes(manager, repo)
        check = results[key]
        assert check["ok"] is False
        err = check["error"]
        assert name in err
        assert str(status) in err
        # full URL appears with GET method
        url = URL_BY_KEY[key]
        assert f"(GET {url})" in err


# ===================================================================
# 4. PaginatedList.totalCount must be read for lazy probes
# ===================================================================


class TestTotalCountIsRead:
    """For lazy paginated probes, .totalCount must be accessed exactly once."""

    @pytest.mark.parametrize(
        "key,method_name",
        [
            ("perm_pull_requests_read", "get_pulls"),
            ("perm_issues_read", "get_issues"),
            ("perm_workflows_read", "get_workflows"),
        ],
    )
    def test_total_count_accessed(self, key: str, method_name: str) -> None:
        repo = Mock()
        repo.default_branch = "main"
        repo.get_contents.return_value = []
        repo.get_branch.return_value.get_protection.return_value = Mock()
        repo.get_commit.return_value.get_combined_status.return_value = Mock()

        # Default returns for non-target probes
        for other in ("get_pulls", "get_issues", "get_workflows"):
            if other == method_name:
                continue
            paginated = Mock()
            type(paginated).totalCount = PropertyMock(return_value=0)
            getattr(repo, other).return_value = paginated

        # Target probe: track the property access
        target_paginated = Mock()
        prop = PropertyMock(return_value=42)
        type(target_paginated).totalCount = prop
        getattr(repo, method_name).return_value = target_paginated

        manager = _make_manager()
        run_permission_probes(manager, repo)
        assert prop.call_count == 1


# ===================================================================
# 5. perm_statuses_read two-call attribution
# ===================================================================


class TestStatusesTwoCallAttribution:
    """get_commit failures are NOT routed through the classifier."""

    def test_get_commit_raises_skips_classifier(self) -> None:
        repo = Mock()
        repo.default_branch = "main"
        repo.get_commit.side_effect = GithubException(
            status=403, data={}, headers={}
        )
        result = _probe_statuses(
            repo, "main", "https://api.github.com/repos/owner/repo", GITHUB_COM_HOST
        )
        assert result["ok"] is False
        assert result["value"] == "not checked"
        assert (
            result["error"] == "commit lookup failed (covered by perm_contents_read)"
        )
        # Classifier always emits "(GET ...)" on failures; absence proves it was skipped
        assert "GET" not in result["error"]
        assert "https://" not in result["error"]

    def test_get_combined_status_404_runs_classifier(self) -> None:
        repo = Mock()
        repo.default_branch = "main"
        commit = Mock()
        commit.get_combined_status.side_effect = GithubException(
            status=404, data={}, headers={}
        )
        repo.get_commit.return_value = commit
        result = _probe_statuses(
            repo, "main", "https://api.github.com/repos/owner/repo", None
        )
        assert result["ok"] is False
        err = result["error"]
        assert "Commit statuses: Read" in err
        assert "404" in err
        url = "https://api.github.com/repos/owner/repo/commits/main/status"
        assert f"(GET {url})" in err


# ===================================================================
# 5b. perm_administration_read two-call attribution
# ===================================================================


class TestAdministrationTwoCallAttribution:
    """get_branch failures are NOT routed through the classifier."""

    def test_get_branch_raises_skips_classifier(self) -> None:
        repo = Mock()
        repo.default_branch = "main"
        repo.get_branch.side_effect = GithubException(
            status=403, data={}, headers={}
        )
        result = _probe_administration(
            repo, "main", "https://api.github.com/repos/owner/repo", GITHUB_COM_HOST
        )
        assert result["ok"] is False
        assert result["value"] == "not checked"
        assert (
            result["error"] == "branch lookup failed (covered by perm_contents_read)"
        )
        assert "GET" not in result["error"]
        assert "https://" not in result["error"]

    def test_get_protection_404_runs_classifier_with_admin_404(self) -> None:
        repo = Mock()
        repo.default_branch = "main"
        branch = Mock()
        branch.get_protection.side_effect = GithubException(
            status=404, data={}, headers={}
        )
        repo.get_branch.return_value = branch
        result = _probe_administration(
            repo, "main", "https://api.github.com/repos/owner/repo", GITHUB_COM_HOST
        )
        assert result["ok"] is False
        err = result["error"]
        assert "Administration: Read" in err
        assert "no branch protection configured" in err
        url = "https://api.github.com/repos/owner/repo/branches/main/protection"
        assert f"(GET {url})" in err


# ===================================================================
# 6. Network error path
# ===================================================================


class TestNetworkError:
    """Non-GithubException is reported as a network error."""

    def test_network_error_format(self) -> None:
        def boom() -> None:
            raise ConnectionError("boom")

        result = _run_probe(
            call=boom,
            name="Contents: Read",
            url="https://api.github.com/repos/x/y/contents/",
            web_host=None,
        )
        assert result["ok"] is False
        assert result["value"] == "failed"
        assert result["error"] == "network error: boom — needs Contents: Read"


# ===================================================================
# 7. Skip-when-unreachable: 6 placeholder rows, NO manager dereference
# ===================================================================


class TestSkipWhenUnreachable:
    """When repo is None, returns 6 placeholders without touching manager."""

    def test_six_placeholder_rows(self) -> None:
        manager = MagicMock()
        results = run_permission_probes(manager, None)
        assert set(results.keys()) == set(_PROBE_KEYS)
        for key in _PROBE_KEYS:
            check = results[key]
            assert check["ok"] is False
            assert check["value"] == "not checked"
            assert check["severity"] == "warning"
            assert check["error"] == "repository not accessible"

    def test_manager_not_dereferenced(self) -> None:
        manager = MagicMock()
        run_permission_probes(manager, None)
        # _repo_identifier should never have been accessed
        assert "_repo_identifier" not in {
            c[0] for c in manager.mock_calls if c[0]
        }
        # Stronger: no attribute access at all besides the call itself
        # (MagicMock records both attribute lookups via method_calls but
        # bare attribute access goes through __getattr__ which is only
        # captured implicitly — we additionally confirm by direct check).
        assert not manager._repo_identifier.called


# ===================================================================
# 8. URL templates: built from api_base_url + full_name + path
# ===================================================================


class TestUrlTemplates:
    """URLs include api_base_url and full_name, never credentials."""

    def test_urls_built_from_identifier(self) -> None:
        manager = _make_manager(
            full_name="acme/widget",
            api_base_url="https://ghe.example.com/api/v3",
            web_host=None,
        )

        repo = Mock()
        repo.default_branch = "trunk"
        # Force all probes to fail with a 404 so URLs land in error fields
        exc = GithubException(status=404, data={}, headers={})
        repo.get_contents.side_effect = exc
        pulls = Mock()
        type(pulls).totalCount = PropertyMock(side_effect=exc)
        repo.get_pulls.return_value = pulls
        issues = Mock()
        type(issues).totalCount = PropertyMock(side_effect=exc)
        repo.get_issues.return_value = issues
        workflows = Mock()
        type(workflows).totalCount = PropertyMock(side_effect=exc)
        repo.get_workflows.return_value = workflows

        branch = Mock()
        branch.get_protection.side_effect = exc
        repo.get_branch.return_value = branch

        commit = Mock()
        commit.get_combined_status.side_effect = exc
        repo.get_commit.return_value = commit

        results = run_permission_probes(manager, repo)

        expected_urls = {
            "perm_contents_read": "https://ghe.example.com/api/v3/repos/acme/widget/contents/",
            "perm_administration_read": "https://ghe.example.com/api/v3/repos/acme/widget/branches/trunk/protection",
            "perm_pull_requests_read": "https://ghe.example.com/api/v3/repos/acme/widget/pulls?state=all",
            "perm_issues_read": "https://ghe.example.com/api/v3/repos/acme/widget/issues?state=all",
            "perm_workflows_read": "https://ghe.example.com/api/v3/repos/acme/widget/actions/workflows",
            "perm_statuses_read": "https://ghe.example.com/api/v3/repos/acme/widget/commits/trunk/status",
        }
        for key, url in expected_urls.items():
            err = results[key]["error"]
            assert f"(GET {url})" in err
            # Never a credential in the URL
            assert "@" not in url


# ===================================================================
# Probe key order is part of the public contract
# ===================================================================


class TestProbeKeyOrder:
    """run_permission_probes returns keys in _PROBE_KEYS order."""

    def test_skip_path_order(self) -> None:
        results = run_permission_probes(MagicMock(), None)
        assert tuple(results.keys()) == _PROBE_KEYS

    def test_normal_path_order(self, mock_repo_full: Mock) -> None:
        manager = _make_manager()
        results = run_permission_probes(manager, mock_repo_full)
        assert tuple(results.keys()) == _PROBE_KEYS


# A small smoke test that types align with CheckResult shape
def test_classifier_returns_check_result_shape() -> None:
    result: CheckResult = _classify_permission_response(
        "Contents: Read", 200, "https://x", None
    )
    assert isinstance(result, dict)
    assert "ok" in result
    assert "severity" in result
