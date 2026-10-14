"""Read-only GitHub repository security-settings probes.

Companion to ``_permission_probes.py``, reusing the tri-state ``CheckResult``
convention from mcp-workspace#301: ``ok=True|False|None``, where ``None``
means "cannot verify", never "off". Unlike ``_permission_probes.py``, these
four checks have an unambiguous three-way split handed to us directly by the
two GitHub API shapes involved, so this module carries no host-aware
URL/hint machinery.
"""

from typing import Any

from mcp_workspace.github_operations._types import CheckResult

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
