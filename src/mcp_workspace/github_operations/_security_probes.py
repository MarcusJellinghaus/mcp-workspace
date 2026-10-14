"""Read-only GitHub repository security-settings probes.

Companion to ``_permission_probes.py``, reusing the tri-state ``CheckResult``
convention from mcp-workspace#301: ``ok=True|False|None``, where ``None``
means "cannot verify", never "off". Unlike ``_permission_probes.py``, these
four checks have an unambiguous three-way split handed to us directly by the
two GitHub API shapes involved, so this module carries no host-aware
URL/hint machinery.
"""

import logging
from pathlib import Path
from typing import Any

from github import Consts
from github.Repository import Repository

from mcp_workspace.github_operations._types import CheckResult
from mcp_workspace.github_operations.base_manager import BaseGitHubManager

logger = logging.getLogger(__name__)

_SECURITY_KEYS: tuple[str, ...] = (
    "dependabot_alerts",
    "dependabot_security_updates",
    "secret_scanning",
    "secret_scanning_push_protection",
)


def _classify_vulnerability_alerts(status: int) -> CheckResult:
    """Classify the raw HTTP status of the Dependabot alerts endpoint.

    Returns:
        CheckResult with ok=True for 204 (enabled), ok=False for 404
        (verified disabled), or ok=None for any other status.
    """
    if status == 204:
        return CheckResult(ok=True, value="enabled", severity="warning")
    if status == 404:
        return CheckResult(ok=False, value="disabled", severity="warning")
    return CheckResult(
        ok=None,
        value="not accessible",
        severity="warning",
        error=f"HTTP {status}",
    )


def _classify_security_feature(feature: Any, display_name: str) -> CheckResult:
    """Classify a ``SecurityAndAnalysisFeature`` sub-field.

    Returns:
        CheckResult with ok=None when the feature is absent (container or
        sub-field), ok=True when its status is "enabled", else ok=False.
    """
    if feature is None:
        return CheckResult(
            ok=None,
            value="not accessible",
            severity="warning",
            error=f"{display_name}: requires Administration: Read",
        )
    if feature.status == "enabled":
        return CheckResult(ok=True, value="enabled", severity="warning")
    return CheckResult(ok=False, value="disabled", severity="warning")


def _probe_dependabot_alerts(repo: Repository) -> CheckResult:
    """Probe Dependabot alerts via a direct ``requestJson`` call.

    Bypasses ``Repository.get_vulnerability_alert()``, which collapses every
    non-204 status into a bare ``False``, and instead classifies the raw
    HTTP status returned by the same endpoint it calls internally.

    Returns:
        CheckResult from classifying the HTTP status, or ok=None with a
        network-error message when the request itself fails.
    """
    try:
        status, _, _ = repo.requester.requestJson(
            "GET",
            f"{repo.url}/vulnerability-alerts",
            headers={"Accept": Consts.vulnerabilityAlertsPreview},
        )
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        return CheckResult(
            ok=None,
            value="not accessible",
            severity="warning",
            error=f"network error: {exc}",
        )
    return _classify_vulnerability_alerts(status)


def verify_github_security(project_dir: Path) -> dict[str, CheckResult]:
    """Probe the four read-only GitHub repository security settings.

    Resolves its own repository independently of ``verify_github()`` (a
    second auth round-trip), then classifies each of the four security
    settings using the Step 1/2 helpers.

    Returns:
        dict[str, CheckResult] with exactly the 4 keys in _SECURITY_KEYS
        order. If the repository cannot be resolved, each entry is
        ok=None, value="not checked", error="repository not accessible".
    """
    try:
        manager = BaseGitHubManager(project_dir=project_dir)
        repo = manager._get_repository()  # pylint: disable=protected-access
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        logger.debug("verify_github_security manager/repo resolution failed: %s", exc)
        repo = None

    if repo is None:
        return {
            key: CheckResult(
                ok=None,
                value="not checked",
                severity="warning",
                error="repository not accessible",
            )
            for key in _SECURITY_KEYS
        }

    security_and_analysis = repo.security_and_analysis
    return {
        "dependabot_alerts": _probe_dependabot_alerts(repo),
        "dependabot_security_updates": _classify_security_feature(
            None
            if security_and_analysis is None
            else security_and_analysis.dependabot_security_updates,
            "Dependabot security updates",
        ),
        "secret_scanning": _classify_security_feature(
            None
            if security_and_analysis is None
            else security_and_analysis.secret_scanning,
            "Secret scanning",
        ),
        "secret_scanning_push_protection": _classify_security_feature(
            None
            if security_and_analysis is None
            else security_and_analysis.secret_scanning_push_protection,
            "Secret scanning push protection",
        ),
    }
