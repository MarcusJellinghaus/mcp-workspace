"""GitHub connectivity and branch protection verification.

Provides verify_github() which runs structured checks against the GitHub API
and returns per-check results. All checks use PyGithub — no gh CLI dependency.
"""

import logging
from pathlib import Path

from github.GithubException import GithubException
from github.Repository import Repository
from mcp_coder_utils.user_app_data import get_user_app_data_dir

from mcp_workspace.config import get_github_token_with_source
from mcp_workspace.git_operations.remotes import get_repository_identifier
from mcp_workspace.github_operations._client import build_github_client
from mcp_workspace.github_operations._diagnostics import extract_diagnostic_headers
from mcp_workspace.github_operations._network import (
    _collect_network_diagnostics,
    has_applicable_proxy,
    maybe_log_network_diagnostics,
)
from mcp_workspace.github_operations._permission_probes import run_permission_probes
from mcp_workspace.github_operations._ruleset_protection import (
    ProtectionFacts,
    facts_from_classic,
    merge,
)
from mcp_workspace.github_operations._types import (
    CheckResult,
    ProtectionOutcome,
    is_branch_not_protected,
    short_reason,
)
from mcp_workspace.github_operations.base_manager import BaseGitHubManager
from mcp_workspace.utils.token_fingerprint import format_token_fingerprint

__all__ = ["CheckResult", "verify_github"]

logger = logging.getLogger(__name__)

_PROTECTION_KEYS: tuple[str, ...] = (
    "branch_protection",
    "require_pull_request",
    "ci_checks_required",
    "strict_mode",
    "force_push",
    "branch_deletion",
)


def _protection_rows(ok: bool | None, value: str, error: str) -> dict[str, CheckResult]:
    """Build one identical warning row per branch-protection key.

    Args:
        ok: Check outcome shared by every row.
        value: Display value shared by every row.
        error: Error message shared by every row.

    Returns:
        Mapping from each branch-protection key to the same warning-severity
        ``CheckResult``.
    """
    return {
        k: CheckResult(ok=ok, value=value, severity="warning", error=error)
        for k in _PROTECTION_KEYS
    }


def _fetch_protection(
    manager: BaseGitHubManager, repo: Repository
) -> ProtectionOutcome:
    """Fetch the default branch's protection once, recording where it failed.

    Args:
        manager: Manager used to resolve the default branch name.
        repo: Repository whose default branch protection is fetched.

    Returns:
        ``ProtectionOutcome`` holding the fetched protection, or the stage
        and exception where the fetch failed.
    """
    branch_name: str | None = None
    try:
        branch_name = manager.get_default_branch()
        branch = repo.get_branch(branch_name)
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        logger.debug("Branch lookup failed branch=%s exc=%s", branch_name, exc)
        return ProtectionOutcome(branch_name, "get_branch", None, exc)
    try:
        return ProtectionOutcome(
            branch_name, "get_protection", branch.get_protection(), None
        )
    except GithubException as exc:
        logger.debug(
            "get_protection failed branch=%s status=%s data=%s headers=%s",
            branch_name,
            exc.status,
            exc.data,
            extract_diagnostic_headers(exc),
        )
        return ProtectionOutcome(branch_name, "get_protection", None, exc)
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        logger.debug("get_protection failed branch=%s exc=%s", branch_name, exc)
        return ProtectionOutcome(branch_name, "get_protection", None, exc)


def _classify_protection_failure(
    stage: str, exc: Exception
) -> tuple[bool | None, str, str]:
    """Return (ok, value, error) shared by all six branch-protection rows."""
    if is_branch_not_protected(exc):
        return False, "not configured", "no branch protection"
    reason = short_reason(exc)
    error = f"{stage} failed: {reason}"
    if stage == "get_protection" and isinstance(exc, GithubException):
        if exc.status == 401:
            return None, "not verifiable — token rejected (401)", error
        if exc.status == 403:
            return None, "not verifiable — token lacks Administration: Read", error
    return None, f"not verifiable — {reason}", error


def _protection_result(outcome: ProtectionOutcome) -> dict[str, CheckResult]:
    """Build the six branch-protection rows from the classic fetch outcome.

    Args:
        outcome: Result of the classic branch protection fetch.

    Returns:
        Mapping from each branch-protection key to its ``CheckResult``.
    """
    classic: ProtectionFacts | None
    reason: str | None = None
    error = ""
    if outcome.protection is not None:
        classic = facts_from_classic(outcome.protection)
    elif is_branch_not_protected(outcome.exception):
        classic = ProtectionFacts()
    else:
        classic = None
        _, reason, error = _classify_protection_failure(
            outcome.stage, outcome.exception  # type: ignore[arg-type]
        )
    merged = merge(classic, ProtectionFacts())
    if merged.protected is False:
        return _protection_rows(False, "not configured", "no branch protection")
    return _rows_from_facts(
        merged, f"{outcome.branch} protected", reason=reason, error=error
    )


def _rows_from_facts(
    facts: ProtectionFacts, label: str, *, reason: str | None, error: str
) -> dict[str, CheckResult]:
    """Map merged protection facts to one warning row per branch-protection key.

    Args:
        facts: Merged protection facts; a ``None`` flag means not verifiable.
        label: Value of the ``branch_protection`` row when protected.
        reason: Value of every not-verifiable row.
        error: Error shared by every row; omitted when empty.

    Returns:
        Mapping from each branch-protection key to its ``CheckResult``.
    """

    def row(flag: bool | None, yes: str, no: str) -> CheckResult:
        if flag is None:
            check = CheckResult(
                ok=None, value=reason or "not verifiable", severity="warning"
            )
        else:
            check = CheckResult(ok=flag, value=yes if flag else no, severity="warning")
        if error:
            check["error"] = error
        return check

    return {
        "branch_protection": row(facts.protected, label, "not configured"),
        "require_pull_request": row(facts.require_pr, "required", "not required"),
        "ci_checks_required": row(
            facts.checks_required,
            f"{len(facts.contexts)} checks configured",
            "not configured",
        ),
        "strict_mode": row(facts.strict, "enabled", "disabled"),
        "force_push": row(facts.force_push_blocked, "disabled", "enabled"),
        "branch_deletion": row(facts.deletion_blocked, "disabled", "enabled"),
    }


def verify_github(project_dir: Path) -> dict[str, object]:
    """Verify GitHub connectivity and branch protection.

    Runs the connectivity checks (token, auth, repo URL, repo access), the
    six branch-protection rows and the repo-level settings independently.
    Each check reports its own result regardless of earlier failures.
    A check that could not be verified reports ``ok=None``.

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
    # Proxy / reachability probe (≤3s TCP) + verify-local short-circuit.
    # ------------------------------------------------------------------
    diag = _collect_network_diagnostics(api_base_url)
    result["network_proxy"] = CheckResult(
        ok=(diag["tcp_probe"] == "ok"),
        value=(
            f"api={diag['host']}:443 tcp={diag['tcp_probe']} "
            f"proxy_env={diag['proxy_env']} pac={diag['pac']}"
        ),
        severity="warning",  # never fail overall_ok on this
    )
    # Skip the two slow PyGithub calls only when the host is unreachable *and*
    # no http/https proxy applies — a proxy would give PyGithub a transport the
    # direct TCP probe never tested.
    skip = diag["tcp_probe"] != "ok" and not has_applicable_proxy(api_base_url)

    # ------------------------------------------------------------------
    # Checks 1 & 2: token configured + authenticated user
    # ------------------------------------------------------------------
    scope_str: str | None = None
    if skip:
        result["authenticated_user"] = CheckResult(
            ok=False,
            value="skipped — host unreachable",
            severity="warning",
        )
    else:
        try:
            github_client = build_github_client(token, api_base_url)  # type: ignore[arg-type]
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
        except (
            Exception
        ) as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            maybe_log_network_diagnostics(exc, api_base_url)
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
    if skip:
        result["repo_accessible"] = CheckResult(
            ok=False,
            value="skipped — host unreachable",
            severity="warning",
        )
    else:
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
        except (
            Exception
        ) as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            logger.debug("Repository access check failed: %s", exc)
            result["repo_accessible"] = CheckResult(
                ok=False,
                value="not accessible",
                severity="error",
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Branch protection: six rows
    # ------------------------------------------------------------------
    repo_obj = result.get("repo_accessible")
    repo_is_ok = isinstance(repo_obj, dict) and repo_obj.get("ok") is True

    outcome: ProtectionOutcome | None = None
    if repo_is_ok and repo is not None and manager is not None:
        outcome = _fetch_protection(manager, repo)

    if outcome is None:
        result.update(_protection_rows(None, "unknown", "repository not accessible"))
    else:
        result.update(_protection_result(outcome))

    # ------------------------------------------------------------------
    # auto_delete_branches (repo-level setting)
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
            ok=None,
            value="unknown",
            severity="warning",
            error="repository not accessible",
        )

    # ------------------------------------------------------------------
    # Per-permission read probes (6 fine-grained PAT permissions).
    # ------------------------------------------------------------------
    result.update(
        run_permission_probes(
            manager,  # type: ignore[arg-type]
            repo if repo_is_ok else None,
            protection_outcome=outcome,
        )
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
