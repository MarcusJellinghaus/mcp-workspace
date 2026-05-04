"""GitHub connectivity and branch protection verification.

Provides verify_github() which runs structured checks against the GitHub API
and returns per-check results. All checks use PyGithub — no gh CLI dependency.
"""

import logging
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict

from github import Auth, Github
from github.GithubException import GithubException
from mcp_coder_utils.user_app_data import get_user_app_data_dir

from mcp_workspace.config import get_github_token_with_source
from mcp_workspace.git_operations.remotes import get_repository_identifier
from mcp_workspace.github_operations._diagnostics import extract_diagnostic_headers
from mcp_workspace.github_operations.base_manager import BaseGitHubManager
from mcp_workspace.utils.token_fingerprint import format_token_fingerprint

logger = logging.getLogger(__name__)


class CheckResult(TypedDict):
    """Result of a single verification check."""

    ok: bool
    value: str
    severity: Literal["error", "warning"]
    error: NotRequired[str]
    install_hint: NotRequired[str]
    token_source: NotRequired[Literal["env", "config"]]
    token_fingerprint: NotRequired[str]


def verify_github(project_dir: Path) -> dict[str, object]:
    """Verify GitHub connectivity and branch protection.

    Runs checks 1–4 (token, auth, repo URL, repo access) independently.
    Each check reports its own result regardless of earlier failures.

    Args:
        project_dir: Path to the project directory containing a git repository.

    Returns:
        Dict with ``overall_ok`` bool and per-check ``CheckResult`` entries.
    """
    result: dict[str, object] = {}

    token, source = get_github_token_with_source()

    # ------------------------------------------------------------------
    # Resolve repository identifier first — auth probe needs api_base_url.
    # ------------------------------------------------------------------
    try:
        identifier = get_repository_identifier(project_dir)
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        logger.debug("Repository identifier lookup failed: %s", exc)
        identifier = None

    api_base_url = (
        identifier.api_base_url if identifier is not None else "https://api.github.com"
    )

    if identifier is not None:
        result["api_base_url"] = CheckResult(
            ok=True,
            value=api_base_url,
            severity="error",
        )
    else:
        result["api_base_url"] = CheckResult(
            ok=False,
            value=f"{api_base_url} (fallback - identifier unresolved)",
            severity="warning",
            error="Could not determine repository URL from git remote",
        )

    # ------------------------------------------------------------------
    # Checks 1 & 2: token configured + authenticated user
    # ------------------------------------------------------------------
    scope_str: str | None = None
    try:
        github_client = Github(auth=Auth.Token(token), base_url=api_base_url)  # type: ignore[arg-type]
        user = github_client.get_user()
        result["authenticated_user"] = CheckResult(
            ok=True,
            value=user.login,
            severity="error",
        )
        scopes = github_client.oauth_scopes
        if scopes is not None:
            scope_str = ", ".join(scopes) if scopes else "none"
    except GithubException as e:
        logger.debug(
            "verify_github auth probe GithubException base_url=%s status=%s data=%s headers=%s token=%s",
            api_base_url,
            e.status,
            e.data,
            extract_diagnostic_headers(e),
            format_token_fingerprint(token) if token else "<none>",
        )
        result["authenticated_user"] = CheckResult(
            ok=False,
            value="authentication failed",
            severity="error",
            error=str(e),
        )
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        logger.debug(
            "verify_github auth probe Exception base_url=%s exc=%s",
            api_base_url,
            exc,
        )
        result["authenticated_user"] = CheckResult(
            ok=False,
            value="authentication failed",
            severity="error",
            error=str(exc),
        )

    if token is None:
        config_path = get_user_app_data_dir("mcp_coder") / "config.toml"
        result["token_configured"] = CheckResult(
            ok=False,
            value="not configured",
            severity="error",
            error="GitHub token not found",
            install_hint=(
                f"Set GITHUB_TOKEN environment variable or add [github] token "
                f"to {config_path}"
            ),
        )
    else:
        token_check = CheckResult(
            ok=True,
            value=f"configured (scopes: {scope_str or 'unknown'})",
            severity="error",
        )
        if source is not None:
            token_check["token_source"] = source
        fingerprint = format_token_fingerprint(token)
        if fingerprint:
            token_check["token_fingerprint"] = fingerprint
        result["token_configured"] = token_check

    # ------------------------------------------------------------------
    # Check 3: repository URL resolvable
    # ------------------------------------------------------------------
    if identifier is not None:
        result["repo_url"] = CheckResult(
            ok=True,
            value=identifier.https_url,
            severity="error",
        )
    else:
        result["repo_url"] = CheckResult(
            ok=False,
            value="not resolvable",
            severity="error",
            error="Could not determine repository URL from git remote",
        )

    # ------------------------------------------------------------------
    # Check 4: repository accessible
    # ------------------------------------------------------------------
    manager = None
    repo = None
    try:
        manager = BaseGitHubManager(project_dir=project_dir, github_token=token)
        repo = manager._get_repository()
        if repo is not None:
            result["repo_accessible"] = CheckResult(
                ok=True,
                value=repo.full_name,
                severity="error",
            )
        else:
            result["repo_accessible"] = CheckResult(
                ok=False,
                value="not accessible",
                severity="error",
                error="Repository returned None from GitHub API",
            )
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        logger.debug("Repository access check failed: %s", exc)
        result["repo_accessible"] = CheckResult(
            ok=False,
            value="not accessible",
            severity="error",
            error=str(exc),
        )

    # ------------------------------------------------------------------
    # Checks 5–9: branch protection
    # ------------------------------------------------------------------
    repo_obj = result.get("repo_accessible")
    repo_is_ok = isinstance(repo_obj, dict) and repo_obj.get("ok") is True

    if not repo_is_ok or repo is None or manager is None:
        for key in (
            "branch_protection",
            "ci_checks_required",
            "strict_mode",
            "force_push",
            "branch_deletion",
        ):
            result[key] = CheckResult(
                ok=False,
                value="unknown",
                severity="warning",
                error="repository not accessible",
            )
    else:
        try:
            default_branch_name = manager.get_default_branch()
            branch = repo.get_branch(default_branch_name)
            protection = branch.get_protection()
        except GithubException as exc:
            _reason = "no branch protection" if exc.status == 404 else str(exc)
            for key in (
                "branch_protection",
                "ci_checks_required",
                "strict_mode",
                "force_push",
                "branch_deletion",
            ):
                result[key] = CheckResult(
                    ok=False,
                    value="not configured",
                    severity="warning",
                    error=_reason,
                )
        except (
            Exception
        ) as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            _reason = str(exc)
            for key in (
                "branch_protection",
                "ci_checks_required",
                "strict_mode",
                "force_push",
                "branch_deletion",
            ):
                result[key] = CheckResult(
                    ok=False,
                    value="not configured",
                    severity="warning",
                    error=_reason,
                )
        else:
            # Check 5: branch_protection
            result["branch_protection"] = CheckResult(
                ok=True,
                value=f"{default_branch_name} protected",
                severity="warning",
            )

            # Check 6: ci_checks_required
            # PyGithub types this as RequiredStatusChecks but returns None
            # when the GitHub API sends null
            status_checks: Any = protection.required_status_checks
            if status_checks is not None:
                contexts = status_checks.contexts
                result["ci_checks_required"] = CheckResult(
                    ok=True,
                    value=f"{len(contexts)} checks configured",
                    severity="warning",
                )
            else:
                result["ci_checks_required"] = CheckResult(
                    ok=False,
                    value="not configured",
                    severity="warning",
                )

            # Check 7: strict_mode
            if status_checks is not None and status_checks.strict:
                result["strict_mode"] = CheckResult(
                    ok=True,
                    value="enabled",
                    severity="warning",
                )
            else:
                result["strict_mode"] = CheckResult(
                    ok=False,
                    value="disabled",
                    severity="warning",
                )

            # Check 8: force_push
            force_push_allowed = protection.allow_force_pushes
            if not force_push_allowed:
                result["force_push"] = CheckResult(
                    ok=True,
                    value="disabled",
                    severity="warning",
                )
            else:
                result["force_push"] = CheckResult(
                    ok=False,
                    value="enabled",
                    severity="warning",
                )

            # Check 9: branch_deletion
            deletion_allowed = protection.allow_deletions
            if not deletion_allowed:
                result["branch_deletion"] = CheckResult(
                    ok=True,
                    value="disabled",
                    severity="warning",
                )
            else:
                result["branch_deletion"] = CheckResult(
                    ok=False,
                    value="enabled",
                    severity="warning",
                )

    # ------------------------------------------------------------------
    # Check 10: auto_delete_branches (repo-level setting)
    # ------------------------------------------------------------------
    if repo_is_ok and repo is not None:
        if repo.delete_branch_on_merge:
            result["auto_delete_branches"] = CheckResult(
                ok=True,
                value="auto-delete on merge",
                severity="warning",
            )
        else:
            result["auto_delete_branches"] = CheckResult(
                ok=False,
                value="not enabled",
                severity="warning",
            )
    else:
        result["auto_delete_branches"] = CheckResult(
            ok=False,
            value="unknown",
            severity="warning",
            error="repository not accessible",
        )

    # ------------------------------------------------------------------
    # overall_ok: all error-severity checks must pass
    # ------------------------------------------------------------------
    error_checks: list[CheckResult] = []
    for check_val in result.values():
        if isinstance(check_val, dict) and check_val.get("severity") == "error":
            error_checks.append(check_val)  # type: ignore[arg-type]
    result["overall_ok"] = all(c["ok"] for c in error_checks)

    return result
