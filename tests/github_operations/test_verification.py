"""Unit tests for verify_github() connectivity and branch protection checks."""

import logging
from pathlib import Path
from typing import Literal
from unittest.mock import Mock, PropertyMock, patch

import pytest
from github.GithubException import GithubException

from mcp_workspace.github_operations._permission_probes import _PROBE_KEYS
from mcp_workspace.github_operations.verification import CheckResult, verify_github

MODULE = "mcp_workspace.github_operations.verification"


def _make_identifier(
    hostname: str = "github.com",
    full_name: str = "owner/repo",
    api_base_url: str = "https://api.github.com",
) -> Mock:
    """Build a mock RepositoryIdentifier with explicit api_base_url."""
    m = Mock()
    m.https_url = f"https://{hostname}/{full_name}"
    m.api_base_url = api_base_url
    m.full_name = full_name
    return m


def _make_mock_protection(
    *,
    strict: bool = True,
    contexts: list[str] | None = None,
    allow_force_pushes: bool = False,
    allow_deletions: bool = False,
    has_status_checks: bool = True,
) -> Mock:
    """Create a mock BranchProtection object."""
    protection = Mock()
    if has_status_checks:
        status_checks = Mock()
        status_checks.strict = strict
        status_checks.contexts = (
            contexts if contexts is not None else ["ci/test", "ci/lint"]
        )
        protection.required_status_checks = status_checks
    else:
        protection.required_status_checks = None
    protection.allow_force_pushes = allow_force_pushes
    protection.allow_deletions = allow_deletions
    return protection


def _patch_all_ok(
    project_dir: Path,
    *,
    oauth_scopes: list[str] | None = None,
    user_login: str = "testuser",
    repo_full_name: str = "owner/repo",
    default_branch: str = "main",
    protection: Mock | None = None,
    delete_branch_on_merge: bool = True,
    token_source: Literal["env", "config"] = "env",
) -> dict[str, object]:
    """Run verify_github with all dependencies mocked to succeed."""
    if oauth_scopes is None:
        oauth_scopes = ["repo", "workflow"]

    mock_user = Mock()
    mock_user.login = user_login

    mock_github_client = Mock()
    mock_github_client.get_user.return_value = mock_user
    mock_github_client.oauth_scopes = oauth_scopes

    mock_repo = Mock()
    mock_repo.full_name = repo_full_name
    mock_repo.delete_branch_on_merge = delete_branch_on_merge

    mock_branch = Mock()
    if protection is None:
        protection = _make_mock_protection()
    mock_branch.get_protection.return_value = protection
    mock_repo.get_branch.return_value = mock_branch

    identifier = _make_identifier(full_name=repo_full_name)

    with (
        patch(
            f"{MODULE}.get_github_token_with_source",
            return_value=("ghp_testtoken", token_source),
        ),
        patch(f"{MODULE}.Github", return_value=mock_github_client),
        patch(f"{MODULE}.get_repository_identifier", return_value=identifier),
        patch(f"{MODULE}.BaseGitHubManager") as mock_manager_cls,
    ):
        mock_manager = Mock()
        mock_manager._get_repository.return_value = mock_repo
        mock_manager.get_default_branch.return_value = default_branch
        mock_manager_cls.return_value = mock_manager

        return verify_github(project_dir)


class TestAllConnectivityChecksPass:
    """Test that all connectivity checks pass with valid setup."""

    def test_overall_ok_true(self, tmp_path: Path) -> None:
        result = _patch_all_ok(tmp_path)
        assert result["overall_ok"] is True

    def test_all_checks_ok(self, tmp_path: Path) -> None:
        result = _patch_all_ok(tmp_path)
        for key in (
            "token_configured",
            "authenticated_user",
            "repo_url",
            "repo_accessible",
        ):
            check = result[key]
            assert isinstance(check, dict)
            assert check["ok"] is True

    def test_severity_is_error(self, tmp_path: Path) -> None:
        result = _patch_all_ok(tmp_path)
        for key in (
            "token_configured",
            "authenticated_user",
            "repo_url",
            "repo_accessible",
        ):
            check = result[key]
            assert isinstance(check, dict)
            assert check["severity"] == "error"


class TestTokenNotConfigured:
    """Test behavior when GitHub token is not available."""

    def test_token_configured_fails(self, tmp_path: Path) -> None:
        mock_github_client = Mock()
        mock_github_client.get_user.side_effect = Exception("bad token")
        mock_github_client.oauth_scopes = None

        with (
            patch(
                f"{MODULE}.get_github_token_with_source",
                return_value=(None, None),
            ),
            patch(f"{MODULE}.Github", return_value=mock_github_client),
            patch(f"{MODULE}.get_repository_identifier", return_value=None),
            patch(f"{MODULE}.BaseGitHubManager") as mock_mgr_cls,
        ):
            mock_mgr_cls.side_effect = ValueError("no token")
            result = verify_github(tmp_path)

        check: CheckResult = result["token_configured"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert result["overall_ok"] is False

    def test_overall_ok_false(self, tmp_path: Path) -> None:
        with (
            patch(
                f"{MODULE}.get_github_token_with_source",
                return_value=(None, None),
            ),
            patch(f"{MODULE}.Github") as mock_gh,
            patch(f"{MODULE}.get_repository_identifier", return_value=None),
            patch(f"{MODULE}.BaseGitHubManager") as mock_mgr_cls,
        ):
            mock_gh.return_value.get_user.side_effect = Exception("no token")
            mock_gh.return_value.oauth_scopes = None
            mock_mgr_cls.side_effect = ValueError("no token")
            result = verify_github(tmp_path)

        assert result["overall_ok"] is False


class TestTokenConfiguredScopesReported:
    """Test that OAuth scopes are reported in the token check value."""

    def test_scopes_in_value(self, tmp_path: Path) -> None:
        result = _patch_all_ok(tmp_path, oauth_scopes=["repo", "workflow"])
        check: CheckResult = result["token_configured"]  # type: ignore[assignment]
        assert "repo, workflow" in check["value"]

    def test_empty_scopes(self, tmp_path: Path) -> None:
        result = _patch_all_ok(tmp_path, oauth_scopes=[])
        check: CheckResult = result["token_configured"]  # type: ignore[assignment]
        assert "none" in check["value"].lower() or check["value"].count("scopes") >= 1


class TestAuthFailure:
    """Test behavior when authentication fails."""

    def test_authenticated_user_fails(self, tmp_path: Path) -> None:
        mock_github_client = Mock()
        mock_github_client.get_user.side_effect = Exception("auth failed")
        mock_github_client.oauth_scopes = None

        identifier = _make_identifier()

        mock_repo = Mock()
        mock_repo.full_name = "owner/repo"
        mock_branch = Mock()
        mock_branch.get_protection.return_value = _make_mock_protection()
        mock_repo.get_branch.return_value = mock_branch

        with (
            patch(
                f"{MODULE}.get_github_token_with_source",
                return_value=("ghp_test", "env"),
            ),
            patch(f"{MODULE}.Github", return_value=mock_github_client),
            patch(f"{MODULE}.get_repository_identifier", return_value=identifier),
            patch(f"{MODULE}.BaseGitHubManager") as mock_mgr_cls,
        ):
            mock_manager = Mock()
            mock_manager._get_repository.return_value = mock_repo
            mock_manager.get_default_branch.return_value = "main"
            mock_mgr_cls.return_value = mock_manager
            result = verify_github(tmp_path)

        check: CheckResult = result["authenticated_user"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert result["overall_ok"] is False


class TestAuthFailureScopesUnknown:
    """Test that scopes are unknown when auth fails."""

    def test_scopes_unknown(self, tmp_path: Path) -> None:
        mock_github_client = Mock()
        mock_github_client.get_user.side_effect = Exception("auth failed")
        mock_github_client.oauth_scopes = None

        with (
            patch(
                f"{MODULE}.get_github_token_with_source",
                return_value=("ghp_test", "env"),
            ),
            patch(f"{MODULE}.Github", return_value=mock_github_client),
            patch(f"{MODULE}.get_repository_identifier", return_value=None),
            patch(f"{MODULE}.BaseGitHubManager") as mock_mgr_cls,
        ):
            mock_mgr_cls.side_effect = ValueError("no token")
            result = verify_github(tmp_path)

        check: CheckResult = result["token_configured"]  # type: ignore[assignment]
        assert "unknown" in check["value"].lower()


class TestTokenSource:
    """Test that token_source is surfaced on token_configured."""

    def test_token_source_env(self, tmp_path: Path) -> None:
        result = _patch_all_ok(tmp_path, token_source="env")
        check: CheckResult = result["token_configured"]  # type: ignore[assignment]
        assert check["token_source"] == "env"

    def test_token_source_config(self, tmp_path: Path) -> None:
        result = _patch_all_ok(tmp_path, token_source="config")
        check: CheckResult = result["token_configured"]  # type: ignore[assignment]
        assert check["token_source"] == "config"

    def test_token_source_omitted_when_no_token(self, tmp_path: Path) -> None:
        mock_github_client = Mock()
        mock_github_client.get_user.side_effect = Exception("no token")
        mock_github_client.oauth_scopes = None

        with (
            patch(
                f"{MODULE}.get_github_token_with_source",
                return_value=(None, None),
            ),
            patch(f"{MODULE}.Github", return_value=mock_github_client),
            patch(f"{MODULE}.get_repository_identifier", return_value=None),
            patch(f"{MODULE}.BaseGitHubManager") as mock_mgr_cls,
        ):
            mock_mgr_cls.side_effect = ValueError("no token")
            result = verify_github(tmp_path)

        check: CheckResult = result["token_configured"]  # type: ignore[assignment]
        assert "token_source" not in check

    def test_token_source_set_on_auth_failure(self, tmp_path: Path) -> None:
        mock_github_client = Mock()
        mock_github_client.get_user.side_effect = Exception("Bad credentials")
        mock_github_client.oauth_scopes = None

        with (
            patch(
                f"{MODULE}.get_github_token_with_source",
                return_value=("ghp_bad", "env"),
            ),
            patch(f"{MODULE}.Github", return_value=mock_github_client),
            patch(f"{MODULE}.get_repository_identifier", return_value=None),
            patch(f"{MODULE}.BaseGitHubManager") as mock_mgr_cls,
        ):
            mock_mgr_cls.side_effect = ValueError("no repo")
            result = verify_github(tmp_path)

        auth_check: CheckResult = result["authenticated_user"]  # type: ignore[assignment]
        token_check: CheckResult = result["token_configured"]  # type: ignore[assignment]
        assert auth_check["ok"] is False
        assert token_check["token_source"] == "env"


class TestRepoUrlNotResolvable:
    """Test behavior when repository URL cannot be resolved."""

    def test_repo_url_fails(self, tmp_path: Path) -> None:
        mock_user = Mock()
        mock_user.login = "testuser"

        mock_github_client = Mock()
        mock_github_client.get_user.return_value = mock_user
        mock_github_client.oauth_scopes = ["repo"]

        with (
            patch(
                f"{MODULE}.get_github_token_with_source",
                return_value=("ghp_test", "env"),
            ),
            patch(f"{MODULE}.Github", return_value=mock_github_client),
            patch(f"{MODULE}.get_repository_identifier", return_value=None),
            patch(f"{MODULE}.BaseGitHubManager") as mock_mgr_cls,
        ):
            mock_mgr_cls.side_effect = ValueError("no repo")
            result = verify_github(tmp_path)

        check: CheckResult = result["repo_url"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert result["overall_ok"] is False


class TestRepoNotAccessible:
    """Test behavior when repository is not accessible."""

    def test_repo_accessible_fails(self, tmp_path: Path) -> None:
        mock_user = Mock()
        mock_user.login = "testuser"

        mock_github_client = Mock()
        mock_github_client.get_user.return_value = mock_user
        mock_github_client.oauth_scopes = ["repo"]

        identifier = _make_identifier()

        with (
            patch(
                f"{MODULE}.get_github_token_with_source",
                return_value=("ghp_test", "env"),
            ),
            patch(f"{MODULE}.Github", return_value=mock_github_client),
            patch(f"{MODULE}.get_repository_identifier", return_value=identifier),
            patch(f"{MODULE}.BaseGitHubManager") as mock_mgr_cls,
        ):
            mock_manager = Mock()
            mock_manager._get_repository.return_value = None
            mock_mgr_cls.return_value = mock_manager
            result = verify_github(tmp_path)

        check: CheckResult = result["repo_accessible"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert result["overall_ok"] is False


class TestChecksIndependence:
    """Test that checks run independently — failures don't prevent other checks."""

    def test_token_fails_others_still_run(self, tmp_path: Path) -> None:
        mock_github_client = Mock()
        mock_github_client.get_user.side_effect = Exception("no auth")
        mock_github_client.oauth_scopes = None

        with (
            patch(
                f"{MODULE}.get_github_token_with_source",
                return_value=(None, None),
            ),
            patch(f"{MODULE}.Github", return_value=mock_github_client),
            patch(f"{MODULE}.get_repository_identifier", return_value=None),
            patch(f"{MODULE}.BaseGitHubManager") as mock_mgr_cls,
        ):
            mock_mgr_cls.side_effect = ValueError("no token")
            result = verify_github(tmp_path)

        for key in (
            "token_configured",
            "authenticated_user",
            "repo_url",
            "repo_accessible",
        ):
            assert key in result

    def test_auth_fails_repo_checks_still_run(self, tmp_path: Path) -> None:
        mock_github_client = Mock()
        mock_github_client.get_user.side_effect = Exception("auth failed")
        mock_github_client.oauth_scopes = None

        identifier = _make_identifier()

        mock_repo = Mock()
        mock_repo.full_name = "owner/repo"
        mock_branch = Mock()
        mock_branch.get_protection.return_value = _make_mock_protection()
        mock_repo.get_branch.return_value = mock_branch

        with (
            patch(
                f"{MODULE}.get_github_token_with_source",
                return_value=("ghp_test", "env"),
            ),
            patch(f"{MODULE}.Github", return_value=mock_github_client),
            patch(f"{MODULE}.get_repository_identifier", return_value=identifier),
            patch(f"{MODULE}.BaseGitHubManager") as mock_mgr_cls,
        ):
            mock_manager = Mock()
            mock_manager._get_repository.return_value = mock_repo
            mock_manager.get_default_branch.return_value = "main"
            mock_mgr_cls.return_value = mock_manager
            result = verify_github(tmp_path)

        # Auth failed but repo checks still ran
        assert result["authenticated_user"]["ok"] is False  # type: ignore[index]
        assert "repo_url" in result
        assert "repo_accessible" in result


# ===================================================================
# Branch protection checks (5–9)
# ===================================================================

BRANCH_CHECK_KEYS = (
    "branch_protection",
    "ci_checks_required",
    "strict_mode",
    "force_push",
    "branch_deletion",
)


class TestBranchProtectionAllPass:
    """Test all branch protection checks pass with full protection."""

    def test_all_five_checks_ok(self, tmp_path: Path) -> None:
        protection = _make_mock_protection(
            strict=True,
            contexts=["ci/test", "ci/lint"],
            allow_force_pushes=False,
            allow_deletions=False,
        )
        result = _patch_all_ok(tmp_path, protection=protection)
        for key in BRANCH_CHECK_KEYS:
            check: CheckResult = result[key]  # type: ignore[assignment]
            assert check["ok"] is True, f"{key} should be ok"
            assert check["severity"] == "warning"

    def test_overall_ok_true(self, tmp_path: Path) -> None:
        result = _patch_all_ok(tmp_path)
        assert result["overall_ok"] is True


class TestNoBranchProtection404:
    """Test when get_protection() raises 404 — no protection configured."""

    def _run(self, tmp_path: Path) -> dict[str, object]:
        mock_user = Mock()
        mock_user.login = "testuser"

        mock_github_client = Mock()
        mock_github_client.get_user.return_value = mock_user
        mock_github_client.oauth_scopes = ["repo"]

        mock_branch = Mock()
        mock_branch.get_protection.side_effect = GithubException(
            status=404, data={"message": "Branch not protected"}, headers={}
        )

        mock_repo = Mock()
        mock_repo.full_name = "owner/repo"
        mock_repo.get_branch.return_value = mock_branch

        identifier = _make_identifier()

        with (
            patch(
                f"{MODULE}.get_github_token_with_source",
                return_value=("ghp_test", "env"),
            ),
            patch(f"{MODULE}.Github", return_value=mock_github_client),
            patch(f"{MODULE}.get_repository_identifier", return_value=identifier),
            patch(f"{MODULE}.BaseGitHubManager") as mock_mgr_cls,
        ):
            mock_manager = Mock()
            mock_manager._get_repository.return_value = mock_repo
            mock_manager.get_default_branch.return_value = "main"
            mock_mgr_cls.return_value = mock_manager
            return verify_github(tmp_path)

    def test_all_five_not_ok(self, tmp_path: Path) -> None:
        result = self._run(tmp_path)
        for key in BRANCH_CHECK_KEYS:
            check: CheckResult = result[key]  # type: ignore[assignment]
            assert check["ok"] is False, f"{key} should not be ok"
            assert check["severity"] == "warning"

    def test_overall_ok_still_true(self, tmp_path: Path) -> None:
        result = self._run(tmp_path)
        assert result["overall_ok"] is True


class TestNoStatusChecksConfigured:
    """Test when required_status_checks is None."""

    def test_ci_checks_not_ok(self, tmp_path: Path) -> None:
        protection = _make_mock_protection(has_status_checks=False)
        result = _patch_all_ok(tmp_path, protection=protection)
        check: CheckResult = result["ci_checks_required"]  # type: ignore[assignment]
        assert check["ok"] is False

    def test_strict_mode_not_ok(self, tmp_path: Path) -> None:
        protection = _make_mock_protection(has_status_checks=False)
        result = _patch_all_ok(tmp_path, protection=protection)
        check: CheckResult = result["strict_mode"]  # type: ignore[assignment]
        assert check["ok"] is False


class TestStrictModeDisabled:
    """Test when strict mode is False."""

    def test_strict_mode_not_ok(self, tmp_path: Path) -> None:
        protection = _make_mock_protection(strict=False)
        result = _patch_all_ok(tmp_path, protection=protection)
        check: CheckResult = result["strict_mode"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert "disabled" in check["value"].lower()


class TestForcePushEnabled:
    """Test when force push is allowed."""

    def test_force_push_not_ok(self, tmp_path: Path) -> None:
        protection = _make_mock_protection(allow_force_pushes=True)
        result = _patch_all_ok(tmp_path, protection=protection)
        check: CheckResult = result["force_push"]  # type: ignore[assignment]
        assert check["ok"] is False


class TestBranchDeletionEnabled:
    """Test when branch deletion is allowed."""

    def test_branch_deletion_not_ok(self, tmp_path: Path) -> None:
        protection = _make_mock_protection(allow_deletions=True)
        result = _patch_all_ok(tmp_path, protection=protection)
        check: CheckResult = result["branch_deletion"]  # type: ignore[assignment]
        assert check["ok"] is False


class TestBranchProtectionWhenRepoNotAccessible:
    """Test branch protection checks when repo is not accessible (check 4 failed)."""

    def test_all_five_present_and_not_ok(self, tmp_path: Path) -> None:
        mock_user = Mock()
        mock_user.login = "testuser"

        mock_github_client = Mock()
        mock_github_client.get_user.return_value = mock_user
        mock_github_client.oauth_scopes = ["repo"]

        identifier = _make_identifier()

        with (
            patch(
                f"{MODULE}.get_github_token_with_source",
                return_value=("ghp_test", "env"),
            ),
            patch(f"{MODULE}.Github", return_value=mock_github_client),
            patch(f"{MODULE}.get_repository_identifier", return_value=identifier),
            patch(f"{MODULE}.BaseGitHubManager") as mock_mgr_cls,
        ):
            mock_manager = Mock()
            mock_manager._get_repository.return_value = None
            mock_mgr_cls.return_value = mock_manager
            result = verify_github(tmp_path)

        for key in BRANCH_CHECK_KEYS:
            check: CheckResult = result[key]  # type: ignore[assignment]
            assert check["ok"] is False
            assert "error" in check


class TestDefaultBranchNameInProtectionValue:
    """Test that the default branch name appears in protection check value."""

    def test_branch_name_in_value(self, tmp_path: Path) -> None:
        result = _patch_all_ok(tmp_path, default_branch="develop")
        check: CheckResult = result["branch_protection"]  # type: ignore[assignment]
        assert "develop" in check["value"]


# ===================================================================
# Check 10: auto_delete_branches
# ===================================================================


class TestAutoDeleteBranches:
    """Test auto_delete_branches check (check 10)."""

    def test_enabled(self, tmp_path: Path) -> None:
        result = _patch_all_ok(tmp_path, delete_branch_on_merge=True)
        check: CheckResult = result["auto_delete_branches"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["value"] == "auto-delete on merge"
        assert check["severity"] == "warning"

    def test_disabled(self, tmp_path: Path) -> None:
        result = _patch_all_ok(tmp_path, delete_branch_on_merge=False)
        check: CheckResult = result["auto_delete_branches"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["value"] == "not enabled"
        assert check["severity"] == "warning"

    def test_present_when_no_branch_protection(self, tmp_path: Path) -> None:
        mock_user = Mock()
        mock_user.login = "testuser"

        mock_github_client = Mock()
        mock_github_client.get_user.return_value = mock_user
        mock_github_client.oauth_scopes = ["repo"]

        mock_branch = Mock()
        mock_branch.get_protection.side_effect = GithubException(
            status=404, data={"message": "Branch not protected"}, headers={}
        )

        mock_repo = Mock()
        mock_repo.full_name = "owner/repo"
        mock_repo.get_branch.return_value = mock_branch
        mock_repo.delete_branch_on_merge = True

        identifier = _make_identifier()

        with (
            patch(
                f"{MODULE}.get_github_token_with_source",
                return_value=("ghp_test", "env"),
            ),
            patch(f"{MODULE}.Github", return_value=mock_github_client),
            patch(f"{MODULE}.get_repository_identifier", return_value=identifier),
            patch(f"{MODULE}.BaseGitHubManager") as mock_mgr_cls,
        ):
            mock_manager = Mock()
            mock_manager._get_repository.return_value = mock_repo
            mock_manager.get_default_branch.return_value = "main"
            mock_mgr_cls.return_value = mock_manager
            result = verify_github(tmp_path)

        check: CheckResult = result["auto_delete_branches"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["value"] == "auto-delete on merge"

    def test_repo_not_accessible(self, tmp_path: Path) -> None:
        mock_user = Mock()
        mock_user.login = "testuser"

        mock_github_client = Mock()
        mock_github_client.get_user.return_value = mock_user
        mock_github_client.oauth_scopes = ["repo"]

        identifier = _make_identifier()

        with (
            patch(
                f"{MODULE}.get_github_token_with_source",
                return_value=("ghp_test", "env"),
            ),
            patch(f"{MODULE}.Github", return_value=mock_github_client),
            patch(f"{MODULE}.get_repository_identifier", return_value=identifier),
            patch(f"{MODULE}.BaseGitHubManager") as mock_mgr_cls,
        ):
            mock_manager = Mock()
            mock_manager._get_repository.return_value = None
            mock_mgr_cls.return_value = mock_manager
            result = verify_github(tmp_path)

        check: CheckResult = result["auto_delete_branches"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert check["value"] == "unknown"
        assert "error" in check


class TestOverallOkTrueWhenOnlyWarningsFail:
    """Test that overall_ok is True when only warning-severity checks fail."""

    def test_overall_ok_true_with_protection_failures(self, tmp_path: Path) -> None:
        protection = _make_mock_protection(
            strict=False,
            allow_force_pushes=True,
            allow_deletions=True,
            has_status_checks=False,
        )
        result = _patch_all_ok(tmp_path, protection=protection)
        # Branch protection found but all sub-checks fail
        assert result["overall_ok"] is True


# ===================================================================
# Step 6: api_base_url result entry + auth probe base_url kwarg
# ===================================================================


def _patch_for_auth_probe(
    project_dir: Path,
    *,
    identifier: Mock | None,
) -> tuple[dict[str, object], Mock]:
    """Run verify_github and return (result, mock_github_class) for auth-probe assertions."""
    mock_user = Mock()
    mock_user.login = "testuser"

    mock_github_client = Mock()
    mock_github_client.get_user.return_value = mock_user
    mock_github_client.oauth_scopes = ["repo"]

    mock_repo = Mock()
    mock_repo.full_name = "owner/repo"
    mock_repo.delete_branch_on_merge = True
    mock_branch = Mock()
    mock_branch.get_protection.return_value = _make_mock_protection()
    mock_repo.get_branch.return_value = mock_branch

    with (
        patch(
            f"{MODULE}.get_github_token_with_source",
            return_value=("ghp_test", "env"),
        ),
        patch(f"{MODULE}.Github", return_value=mock_github_client) as mock_github_class,
        patch(f"{MODULE}.get_repository_identifier", return_value=identifier),
        patch(f"{MODULE}.BaseGitHubManager") as mock_mgr_cls,
    ):
        mock_manager = Mock()
        mock_manager._get_repository.return_value = mock_repo
        mock_manager.get_default_branch.return_value = "main"
        mock_mgr_cls.return_value = mock_manager
        result = verify_github(project_dir)

    return result, mock_github_class


class TestAuthProbeBaseUrlGithubCom:
    """Auth-probe Github(...) is called with base_url=https://api.github.com for github.com."""

    def test_base_url_is_github_com_api(self, tmp_path: Path) -> None:
        identifier = _make_identifier(
            hostname="github.com", api_base_url="https://api.github.com"
        )
        _, mock_github_class = _patch_for_auth_probe(tmp_path, identifier=identifier)
        assert (
            mock_github_class.call_args.kwargs["base_url"] == "https://api.github.com"
        )


class TestAuthProbeBaseUrlGhe:
    """Auth-probe is called with the GHE-tenant API URL when identifier is GHE."""

    def test_base_url_is_ghe_tenant(self, tmp_path: Path) -> None:
        identifier = _make_identifier(
            hostname="tenant.ghe.com",
            api_base_url="https://api.tenant.ghe.com",
        )
        _, mock_github_class = _patch_for_auth_probe(tmp_path, identifier=identifier)
        assert (
            mock_github_class.call_args.kwargs["base_url"]
            == "https://api.tenant.ghe.com"
        )

    def test_base_url_is_ghes(self, tmp_path: Path) -> None:
        identifier = _make_identifier(
            hostname="ghe.example.com",
            api_base_url="https://ghe.example.com/api/v3",
        )
        _, mock_github_class = _patch_for_auth_probe(tmp_path, identifier=identifier)
        assert (
            mock_github_class.call_args.kwargs["base_url"]
            == "https://ghe.example.com/api/v3"
        )


class TestAuthProbeBaseUrlFallback:
    """When identifier is None, auth probe falls back to api.github.com."""

    def test_base_url_fallback(self, tmp_path: Path) -> None:
        _, mock_github_class = _patch_for_auth_probe(tmp_path, identifier=None)
        assert (
            mock_github_class.call_args.kwargs["base_url"] == "https://api.github.com"
        )


class TestApiBaseUrlResultEntrySuccess:
    """result['api_base_url'] is ok=True with the identifier's API URL on success."""

    def test_success_shape(self, tmp_path: Path) -> None:
        identifier = _make_identifier(
            hostname="tenant.ghe.com",
            api_base_url="https://api.tenant.ghe.com",
        )
        result, _ = _patch_for_auth_probe(tmp_path, identifier=identifier)
        check: CheckResult = result["api_base_url"]  # type: ignore[assignment]
        assert check["ok"] is True
        assert check["value"] == "https://api.tenant.ghe.com"
        assert check["severity"] == "error"


class TestApiBaseUrlResultEntryFallback:
    """When identifier is None, api_base_url is a fallback warning entry."""

    def test_fallback_shape(self, tmp_path: Path) -> None:
        result, _ = _patch_for_auth_probe(tmp_path, identifier=None)
        check: CheckResult = result["api_base_url"]  # type: ignore[assignment]
        assert check["ok"] is False
        assert "fallback" in check["value"].lower()
        assert check["severity"] == "warning"
        assert "error" in check
        assert check["error"]


class TestApiBaseUrlIsFirstKey:
    """api_base_url must be the first key in the result dict."""

    def test_first_key_success(self, tmp_path: Path) -> None:
        identifier = _make_identifier()
        result, _ = _patch_for_auth_probe(tmp_path, identifier=identifier)
        assert next(iter(result.keys())) == "api_base_url"

    def test_first_key_fallback(self, tmp_path: Path) -> None:
        result, _ = _patch_for_auth_probe(tmp_path, identifier=None)
        assert next(iter(result.keys())) == "api_base_url"


class TestOverallOkNotPoisonedByFallback:
    """The api_base_url fallback (severity=warning) must NOT poison overall_ok by itself."""

    def test_fallback_alone_does_not_poison(self, tmp_path: Path) -> None:
        result, _ = _patch_for_auth_probe(tmp_path, identifier=None)

        # overall_ok IS False here, but the failure source is repo_url (severity=error),
        # not the api_base_url warning entry.
        assert result["overall_ok"] is False

        repo_url: CheckResult = result["repo_url"]  # type: ignore[assignment]
        assert repo_url["ok"] is False
        assert repo_url["severity"] == "error"

        api_base: CheckResult = result["api_base_url"]  # type: ignore[assignment]
        assert api_base["ok"] is False
        assert api_base["severity"] == "warning"


# ===================================================================
# Step 7: token_fingerprint + auth-probe DEBUG logging
# ===================================================================


_FINGERPRINT_TOKEN = "ghp_testtoken_abcdef_longer_than_8_xyz9"
_RAW_SECRET_TOKEN = "ghp_RAW_SECRET_TOKEN_VALUE_FOR_TEST_xyz"
_RAW_SECRET_SUBSTR = "RAW_SECRET_TOKEN_VALUE_FOR_TEST"


def _patch_with_token_and_auth_behavior(
    project_dir: Path,
    *,
    token: str | None,
    get_user_side_effect: Exception | None,
    identifier: Mock | None,
) -> dict[str, object]:
    """Run verify_github with explicit token and auth-probe behavior."""
    mock_user = Mock()
    mock_user.login = "testuser"

    mock_github_client = Mock()
    if get_user_side_effect is not None:
        mock_github_client.get_user.side_effect = get_user_side_effect
        mock_github_client.oauth_scopes = None
    else:
        mock_github_client.get_user.return_value = mock_user
        mock_github_client.oauth_scopes = ["repo"]

    mock_repo = Mock()
    mock_repo.full_name = "owner/repo"
    mock_repo.delete_branch_on_merge = True
    mock_branch = Mock()
    mock_branch.get_protection.return_value = _make_mock_protection()
    mock_repo.get_branch.return_value = mock_branch

    with (
        patch(
            f"{MODULE}.get_github_token_with_source",
            return_value=(token, "env" if token is not None else None),
        ),
        patch(f"{MODULE}.Github", return_value=mock_github_client),
        patch(f"{MODULE}.get_repository_identifier", return_value=identifier),
        patch(f"{MODULE}.BaseGitHubManager") as mock_mgr_cls,
    ):
        if identifier is None or token is None:
            mock_mgr_cls.side_effect = ValueError("no")
        else:
            mock_manager = Mock()
            mock_manager._get_repository.return_value = mock_repo
            mock_manager.get_default_branch.return_value = "main"
            mock_mgr_cls.return_value = mock_manager
        return verify_github(project_dir)


class TestTokenFingerprintPopulated:
    """token_fingerprint is populated whenever a token loaded."""

    def test_fingerprint_on_success(self, tmp_path: Path) -> None:
        identifier = _make_identifier()
        result = _patch_with_token_and_auth_behavior(
            tmp_path,
            token=_FINGERPRINT_TOKEN,
            get_user_side_effect=None,
            identifier=identifier,
        )
        check: CheckResult = result["token_configured"]  # type: ignore[assignment]
        assert "token_fingerprint" in check
        assert check["token_fingerprint"] == "ghp_...xyz9"
        # No len=N suffix and no SHA digest in the fingerprint shape
        assert "len=" not in check["token_fingerprint"]

    def test_fingerprint_on_auth_failure(self, tmp_path: Path) -> None:
        result = _patch_with_token_and_auth_behavior(
            tmp_path,
            token=_FINGERPRINT_TOKEN,
            get_user_side_effect=GithubException(
                status=401, data={"message": "Bad credentials"}, headers={}
            ),
            identifier=None,
        )
        check: CheckResult = result["token_configured"]  # type: ignore[assignment]
        assert check["token_fingerprint"] == "ghp_...xyz9"

    def test_fingerprint_omitted_when_no_token(self, tmp_path: Path) -> None:
        result = _patch_with_token_and_auth_behavior(
            tmp_path,
            token=None,
            get_user_side_effect=Exception("no token"),
            identifier=None,
        )
        check: CheckResult = result["token_configured"]  # type: ignore[assignment]
        assert "token_fingerprint" not in check


class TestAuthProbeDebugGithubException:
    """DEBUG log on auth probe GithubException carries status/data/headers/base_url/token fingerprint."""

    def test_debug_log_content(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG, logger=MODULE)
        identifier = _make_identifier()
        _patch_with_token_and_auth_behavior(
            tmp_path,
            token=_FINGERPRINT_TOKEN,
            get_user_side_effect=GithubException(
                status=401,
                data={"message": "Bad credentials"},
                headers={"X-GitHub-Request-Id": "abc"},
            ),
            identifier=identifier,
        )
        assert "status=401" in caplog.text
        assert "Bad credentials" in caplog.text
        assert "X-GitHub-Request-Id" in caplog.text
        assert "base_url=" in caplog.text
        assert "token=ghp_..." in caplog.text


class TestAuthProbeDebugGenericException:
    """DEBUG log on auth probe generic Exception logs base_url and the exception message."""

    def test_debug_log_content(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG, logger=MODULE)
        identifier = _make_identifier()
        _patch_with_token_and_auth_behavior(
            tmp_path,
            token=_FINGERPRINT_TOKEN,
            get_user_side_effect=RuntimeError("connection reset by peer"),
            identifier=identifier,
        )
        assert "connection reset by peer" in caplog.text
        assert "base_url=" in caplog.text
        # rich-DEBUG branch did not fire
        assert "status=" not in caplog.text


class TestRawTokenNotLogged:
    """Raw token must never appear in logs or in the result dict on any path."""

    @staticmethod
    def _assert_token_not_in_result(result: dict[str, object]) -> None:
        assert _RAW_SECRET_SUBSTR not in repr(result)
        for v in result.values():
            if isinstance(v, dict):
                if "value" in v:
                    assert _RAW_SECRET_SUBSTR not in str(v["value"])
                if "error" in v:
                    assert _RAW_SECRET_SUBSTR not in str(v["error"])

    def test_failure_path_github_exception(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG, logger=MODULE)
        identifier = _make_identifier()
        result = _patch_with_token_and_auth_behavior(
            tmp_path,
            token=_RAW_SECRET_TOKEN,
            get_user_side_effect=GithubException(
                status=401, data={"message": "Bad credentials"}, headers={}
            ),
            identifier=identifier,
        )
        assert _RAW_SECRET_SUBSTR not in caplog.text
        self._assert_token_not_in_result(result)

    def test_failure_path_generic_exception(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG, logger=MODULE)
        identifier = _make_identifier()
        result = _patch_with_token_and_auth_behavior(
            tmp_path,
            token=_RAW_SECRET_TOKEN,
            get_user_side_effect=RuntimeError("connection reset"),
            identifier=identifier,
        )
        assert _RAW_SECRET_SUBSTR not in caplog.text
        self._assert_token_not_in_result(result)

    def test_success_path(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG, logger=MODULE)
        identifier = _make_identifier()
        result = _patch_with_token_and_auth_behavior(
            tmp_path,
            token=_RAW_SECRET_TOKEN,
            get_user_side_effect=None,
            identifier=identifier,
        )
        assert _RAW_SECRET_SUBSTR not in caplog.text
        self._assert_token_not_in_result(result)
        token_check: CheckResult = result["token_configured"]  # type: ignore[assignment]
        assert token_check["token_fingerprint"] == "ghp_..._xyz"


# ===================================================================
# Permission probes integration with verify_github
# ===================================================================


class TestPermissionProbeKeyOrdering:
    """All 6 probe keys appear in order between auto_delete_branches and overall_ok."""

    def test_keys_present_in_order(self, tmp_path: Path) -> None:
        result = _patch_all_ok(tmp_path)
        keys = list(result.keys())
        for k in _PROBE_KEYS:
            assert k in keys
        # Order: auto_delete_branches < all probes (in _PROBE_KEYS order) < overall_ok
        ad_idx = keys.index("auto_delete_branches")
        ov_idx = keys.index("overall_ok")
        probe_indices = [keys.index(k) for k in _PROBE_KEYS]
        assert all(ad_idx < idx < ov_idx for idx in probe_indices)
        # Within the probes, order matches _PROBE_KEYS exactly
        assert probe_indices == sorted(probe_indices)
        # And matches _PROBE_KEYS order specifically
        ordered_probe_keys = [k for k in keys if k in _PROBE_KEYS]
        assert tuple(ordered_probe_keys) == _PROBE_KEYS


class TestPermissionProbeOverallOkUnaffected:
    """6 failed probes (all warning severity) must NOT flip overall_ok."""

    def test_overall_ok_true_when_probes_fail(self, tmp_path: Path) -> None:
        # Build a repo where every probe call raises 403 — yet error checks pass
        mock_user = Mock()
        mock_user.login = "testuser"
        mock_github_client = Mock()
        mock_github_client.get_user.return_value = mock_user
        mock_github_client.oauth_scopes = ["repo"]

        mock_repo = Mock()
        mock_repo.full_name = "owner/repo"
        mock_repo.delete_branch_on_merge = True
        mock_repo.default_branch = "main"

        # Make each probe-relevant call raise 403 — including get_protection so
        # the Administration probe genuinely fails alongside the other five.
        denial = GithubException(status=403, data={}, headers={})
        mock_branch = Mock()
        mock_branch.get_protection.side_effect = denial
        mock_repo.get_branch.return_value = mock_branch
        # Branch protection checks (5–9) share get_protection with the probe;
        # they degrade to warning severity on failure, so overall_ok is unaffected.
        mock_repo.get_contents.side_effect = denial
        # For the lazy-paginated probes, totalCount must raise
        pulls = Mock()
        type(pulls).totalCount = PropertyMock(side_effect=denial)
        mock_repo.get_pulls.return_value = pulls
        issues = Mock()
        type(issues).totalCount = PropertyMock(side_effect=denial)
        mock_repo.get_issues.return_value = issues
        workflows = Mock()
        type(workflows).totalCount = PropertyMock(side_effect=denial)
        mock_repo.get_workflows.return_value = workflows
        mock_commit = Mock()
        mock_commit.get_combined_status.side_effect = denial
        mock_repo.get_commit.return_value = mock_commit

        identifier = _make_identifier()

        with (
            patch(
                f"{MODULE}.get_github_token_with_source",
                return_value=("ghp_test", "env"),
            ),
            patch(f"{MODULE}.Github", return_value=mock_github_client),
            patch(f"{MODULE}.get_repository_identifier", return_value=identifier),
            patch(f"{MODULE}.BaseGitHubManager") as mock_mgr_cls,
        ):
            mock_manager = Mock()
            mock_manager._get_repository.return_value = mock_repo
            mock_manager.get_default_branch.return_value = "main"
            # _repo_identifier is a property used by run_permission_probes
            mock_manager._repo_identifier = identifier
            mock_mgr_cls.return_value = mock_manager
            result = verify_github(tmp_path)

        # All 6 probes are present and failed
        for k in _PROBE_KEYS:
            check: CheckResult = result[k]  # type: ignore[assignment]
            assert check["severity"] == "warning"
            assert check["ok"] is False
        # overall_ok depends only on error-severity checks, all of which pass.
        assert result["overall_ok"] is True


class TestPermissionProbeSkipWhenUnreachable:
    """When repo_accessible.ok=False, probes return 6 placeholder rows."""

    def test_six_placeholder_rows_no_pygithub_calls(self, tmp_path: Path) -> None:
        mock_user = Mock()
        mock_user.login = "testuser"
        mock_github_client = Mock()
        mock_github_client.get_user.return_value = mock_user
        mock_github_client.oauth_scopes = ["repo"]

        identifier = _make_identifier()

        # Sentinel mock — if any probe reaches into manager._github_client or
        # any repo method, this records a call; we assert call_count == 0 below.
        sentinel = Mock(name="any_pygithub_call")

        with (
            patch(
                f"{MODULE}.get_github_token_with_source",
                return_value=("ghp_test", "env"),
            ),
            patch(f"{MODULE}.Github", return_value=mock_github_client),
            patch(f"{MODULE}.get_repository_identifier", return_value=identifier),
            patch(f"{MODULE}.BaseGitHubManager") as mock_mgr_cls,
        ):
            mock_manager = Mock()
            # repo unreachable
            mock_manager._get_repository.return_value = None
            # Wire any access through sentinel — if probes touch the manager
            # or its github client, we'd see it.
            mock_manager._github_client = sentinel
            mock_mgr_cls.return_value = mock_manager
            result = verify_github(tmp_path)

        # All 6 probe keys present in correct order
        keys = list(result.keys())
        ordered_probe_keys = [k for k in keys if k in _PROBE_KEYS]
        assert tuple(ordered_probe_keys) == _PROBE_KEYS

        for k in _PROBE_KEYS:
            check: CheckResult = result[k]  # type: ignore[assignment]
            assert check["ok"] is False
            assert check["value"] == "not checked"
            assert check["severity"] == "warning"
            assert check["error"] == "repository not accessible"

        # Sentinel proves no PyGithub access happened from the probe orchestrator.
        assert sentinel.mock_calls == []
