"""Rows of the GITHUB SECURITY section of ``verify``.

Combines two local YAML file checks (Dependabot config, CodeQL workflow) with
the five API-backed rows of ``verify_github_security``. The only module in
``mcp_workspace`` allowed to import ``yaml`` (see .importlinter).
"""

from pathlib import Path
from typing import Any

import yaml

from mcp_workspace.github_operations._security_probes import verify_github_security
from mcp_workspace.github_operations._types import CheckResult

_CODEQL_ACTION_PREFIX = "github/codeql-action"


def _schedule_interval(entry: dict[str, Any]) -> Any:
    """Return a dependabot entry's ``schedule.interval``, or ``"?"`` if absent."""
    schedule = entry.get("schedule")
    if isinstance(schedule, dict):
        return schedule.get("interval", "?")
    return "?"


def _workflow_uses_codeql(path: Path) -> bool:
    """Return True if any job step in the workflow uses github/codeql-action.

    Unreadable, unparseable, or oddly shaped files count as False.
    """
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return False
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, dict):
        return False
    for job in jobs.values():
        steps = job.get("steps") if isinstance(job, dict) else None
        if not isinstance(steps, list):
            continue
        for step in steps:
            uses = step.get("uses") if isinstance(step, dict) else None
            if isinstance(uses, str) and uses.startswith(_CODEQL_ACTION_PREFIX):
                return True
    return False


def _check_dependabot_config(project_dir: Path) -> CheckResult:
    """Check .github/dependabot.yml (or .yaml) for configured ecosystems and schedules.

    Args:
        project_dir: Path to the project directory.

    Returns:
        ``CheckResult`` with ``ok=True`` when at least one ecosystem is
        configured, ``ok=False`` otherwise (missing file, invalid YAML, or no
        ecosystems). Always uses warning severity — this section is
        exit-neutral regardless of what any row reports.
    """
    path = next(
        (
            p
            for p in (
                project_dir / ".github" / "dependabot.yml",
                project_dir / ".github" / "dependabot.yaml",
            )
            if p.exists()
        ),
        None,
    )
    if path is None:
        return CheckResult(ok=False, value="not present", severity="warning")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return CheckResult(ok=False, value=f"invalid YAML ({exc})", severity="warning")
    except (OSError, UnicodeDecodeError):
        return CheckResult(ok=False, value="unreadable", severity="warning")
    updates = data.get("updates") if isinstance(data, dict) else None
    if not isinstance(updates, list) or not updates:
        return CheckResult(
            ok=False, value="no ecosystems configured", severity="warning"
        )
    pairs = [
        (
            entry.get("package-ecosystem", "?"),
            _schedule_interval(entry),
        )
        for entry in updates
        if isinstance(entry, dict)
    ]
    if not pairs:
        return CheckResult(
            ok=False, value="no ecosystems configured", severity="warning"
        )
    intervals = {interval for _, interval in pairs}
    if len(intervals) == 1:
        ecosystems = ", ".join(eco for eco, _ in pairs)
        value = f".github/{path.name} ({ecosystems}: {intervals.pop()})"
    else:
        parts = ", ".join(f"{eco}: {interval}" for eco, interval in pairs)
        value = f".github/{path.name} ({parts})"
    return CheckResult(ok=True, value=value, severity="warning")


def _check_codeql_workflow(project_dir: Path) -> CheckResult:
    """Scan .github/workflows/*.yml|*.yaml for a step using github/codeql-action.

    Args:
        project_dir: Path to the project directory.

    Returns:
        ``CheckResult`` with ``ok=True`` when a workflow step's ``uses:``
        value references ``github/codeql-action``, ``ok=False`` otherwise.
        Detection is content-based, not filename-based. Always
        ``severity="warning"``.
    """
    workflows_dir = project_dir / ".github" / "workflows"
    if workflows_dir.is_dir():
        filenames = sorted(
            p.name for p in workflows_dir.iterdir() if p.suffix in (".yml", ".yaml")
        )
        for filename in filenames:
            if _workflow_uses_codeql(workflows_dir / filename):
                return CheckResult(
                    ok=True, value=f"found in {filename}", severity="warning"
                )
    return CheckResult(
        ok=False,
        value="no workflow step uses github/codeql-action",
        severity="warning",
    )


# Known false positive, accepted: the mcp-workspace probe returns normally on a
# 3xx redirect, so it is reported like a 200 ("scope present").
def _map_security_row(key: str, row: CheckResult) -> CheckResult:
    """Map one probe result to its GITHUB SECURITY row (pass-through + 3 rules).

    Rules: an ``ok=None`` ``"not checked"`` value reads ``"not accessible"``;
    the code scanning 404 (``"scope missing or not configured"``) is demoted
    from ``ok=False`` to ``ok=None``; an ``ok=None`` row with an ``error``
    gets it appended to the value. Anything else passes through unchanged.

    Args:
        key: Probe result key (e.g. ``"code_scanning_alerts"``).
        row: The probe's result for ``key``.

    Returns:
        A copy of ``row`` with the rules applied.
    """
    entry = row.copy()
    if entry["ok"] is None and entry["value"] == "not checked":
        entry["value"] = "not accessible"
    if (
        key == "code_scanning_alerts"
        and entry["ok"] is False
        and entry["value"] == "scope missing or not configured"
    ):
        entry["ok"] = None
    if entry["ok"] is None and entry.get("error"):
        entry["value"] = f"{entry['value']} ({entry['error']})"
    return entry


def github_security_rows(project_dir: Path) -> dict[str, CheckResult]:
    """Build the seven GITHUB SECURITY rows in display order.

    The five API-backed rows come from ``verify_github_security``, each mapped
    through ``_map_security_row``; the two local rows read files under
    ``.github/``. All rows use warning severity, so the section is
    exit-neutral.

    Args:
        project_dir: Path to the project directory.

    Returns:
        Dict keyed ``dependabot_config``, ``dependabot_alerts``,
        ``dependabot_security_updates``, ``secret_scanning``,
        ``secret_scanning_push_protection``, ``codeql_workflow``,
        ``code_scanning_alerts``, in that order.
    """
    api = verify_github_security(project_dir)
    return {
        "dependabot_config": _check_dependabot_config(project_dir),
        "dependabot_alerts": _map_security_row(
            "dependabot_alerts", api["dependabot_alerts"]
        ),
        "dependabot_security_updates": _map_security_row(
            "dependabot_security_updates", api["dependabot_security_updates"]
        ),
        "secret_scanning": _map_security_row("secret_scanning", api["secret_scanning"]),
        "secret_scanning_push_protection": _map_security_row(
            "secret_scanning_push_protection",
            api["secret_scanning_push_protection"],
        ),
        "codeql_workflow": _check_codeql_workflow(project_dir),
        "code_scanning_alerts": _map_security_row(
            "code_scanning_alerts", api["code_scanning_alerts"]
        ),
    }
