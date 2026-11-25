"""Section formatters for ``mcp-workspace verify`` and ``mcp-coder verify``.

Turns the dicts returned by ``verify_git``, ``verify_github``,
``github_security_rows`` and ``verify_file_access`` into rows for
``mcp_coder_utils.verify_render``. Imports only the standard library and
``verify_render``, so mcp_coder can import it without loading PyGithub or
GitPython.
"""

from collections.abc import Mapping
from typing import Any

from mcp_coder_utils.verify_render import Line, Row, hint_row

_LABEL_MAP: dict[str, str] = {
    # GitHub section
    "api_base_url": "API base URL",
    "network_proxy": "Network / proxy",
    "token_configured": "Token configured",
    "authenticated_user": "Authenticated user",
    "repo_url": "Repo URL",
    "repo_accessible": "Repo accessible",
    "branch_protection": "Branch protection",
    "require_pull_request": "Require pull request",
    "ci_checks_required": "CI checks required",
    "strict_mode": "Strict mode",
    "force_push": "Force push",
    "branch_deletion": "Branch deletion",
    "auto_delete_branches": "Auto-delete branches",
    "perm_contents_read": "Contents: Read",
    "perm_administration_read": "Administration: Read",
    "perm_pull_requests_read": "Pull requests: Read",
    "perm_issues_read": "Issues: Read",
    "perm_workflows_read": "Actions: Read",
    "perm_statuses_read": "Commit statuses: Read",
    # GitHub security section
    "dependabot_config": "Dependabot config",
    "dependabot_alerts": "Dependabot alerts",
    "dependabot_security_updates": "Dependabot security",
    "secret_scanning": "Secret scanning",
    "secret_scanning_push_protection": "Secret push protection",
    "codeql_workflow": "CodeQL workflow",
    "code_scanning_alerts": "Code scanning alerts",
    # Git section
    "git_binary": "Git binary",
    "git_repo": "Repository",
    "user_identity": "Git identity",
    "signing_intent": "Signing enabled",
    "signing_consistency": "Signing consistency",
    "signing_format": "Signing format",
    "signing_key": "Signing key",
    "signing_binary": "Signing binary",
    "signing_key_accessible": "Signing key accessible",
    "agent_reachable": "GPG agent",
    "allowed_signers": "Allowed signers file",
    "verify_head": "HEAD signature",
    "actual_signature": "End-to-end sign test",
}


_BRANCH_PROTECTION_CHILDREN = frozenset(
    {
        "require_pull_request",
        "ci_checks_required",
        "strict_mode",
        "force_push",
        "branch_deletion",
    }
)


def _format_section(result: Mapping[str, Any], symbols: dict[str, str]) -> list[Line]:
    """Build the rows of a verification section.

    Args:
        result: Dict from a domain verify function
        symbols: Dict with 'success', 'failure', 'warning' keys

    Returns:
        The section's lines (without the title header), ready for rendering.
    """
    lines: list[Line] = []
    bp_ok: bool | None = None  # track branch_protection parent state
    permissions_header_emitted: bool = False
    # NOTE: relies on dict insertion order — branch_protection must precede its
    # children in the result dict. This is guaranteed by verify_github() in
    # mcp-workspace.
    for key, entry in result.items():
        if key == "overall_ok":
            continue
        if not isinstance(entry, dict):
            continue
        label = _LABEL_MAP.get(key, key)
        ok = entry.get("ok")
        value = str(entry.get("value", ""))
        if key == "branch_protection":
            bp_ok = ok
        elif key in _BRANCH_PROTECTION_CHILDREN:
            if bp_ok is not True:
                continue  # suppress children when parent failed or is unverifiable
            if key == "strict_mode":
                lines.append(Row(label, "", value, 4))
            else:
                if ok is True:
                    symbol = symbols["success"]
                elif ok is False:
                    symbol = symbols["failure"]
                else:
                    symbol = symbols["warning"]
                row_value = value
                error = entry.get("error")
                if error and ok is not True:
                    row_value = f"{value} ({error})"
                lines.append(Row(label, symbol, row_value, 4))
            continue
        if key.startswith("perm_") and not permissions_header_emitted:
            lines.append("")
            lines.append("  [Permissions]")
            permissions_header_emitted = True
        if ok is True:
            symbol = symbols["success"]
        elif ok is False:
            symbol = symbols["failure"]
        else:
            symbol = symbols["warning"]
        row_value = value
        error = entry.get("error")
        if error and (ok is False or (ok is None and key == "branch_protection")):
            row_value = f"{value} ({error})"
        indent = 4 if key.startswith("perm_") else 2
        lines.append(Row(label, symbol, row_value, indent))
        if key == "token_configured" and entry.get("token_source"):
            src = entry["token_source"]
            suffix = (
                "GITHUB_TOKEN env var" if src == "env" else "~/.mcp_coder/config.toml"
            )
            fingerprint = entry.get("token_fingerprint")
            if fingerprint:
                suffix = f"{suffix} ({fingerprint})"
            lines.append(hint_row(f"from {suffix}"))
        if ok is False and "install_hint" in entry:
            lines.append(hint_row(f"-> {entry['install_hint']}"))
    return lines


def format_git_section(
    result: Mapping[str, Any], symbols: dict[str, str]
) -> list[Line]:
    """Build the rows of the GIT section from a ``verify_git`` result.

    Args:
        result: Dict returned by ``verify_git``.
        symbols: Dict with 'success', 'failure', 'warning' keys.

    Returns:
        The section's lines (without the title header).
    """
    return _format_section(result, symbols)


def format_github_section(
    result: Mapping[str, Any], symbols: dict[str, str]
) -> list[Line]:
    """Build the rows of the GITHUB section from a ``verify_github`` result.

    Args:
        result: Dict returned by ``verify_github``.
        symbols: Dict with 'success', 'failure', 'warning' keys.

    Returns:
        The section's lines (without the title header).
    """
    return _format_section(result, symbols)


def format_github_security_section(
    result: Mapping[str, Any], symbols: dict[str, str]
) -> list[Line]:
    """Build the rows of the GITHUB SECURITY section from ``github_security_rows``.

    Args:
        result: Dict returned by ``github_security_rows``.
        symbols: Dict with 'success', 'failure', 'warning' keys.

    Returns:
        The section's lines (without the title header).
    """
    return _format_section(result, symbols)


def format_file_access_section(
    result: Mapping[str, Any],
    symbols: dict[str, str],
    *,
    label: str = ".mcp-file-access",
) -> list[Line]:
    """Build the FILE ACCESS row for one project from ``verify_file_access``.

    Only an invalid rules file wraps, since its problem list can be long.

    Args:
        result: ``FileAccessVerification`` returned by ``verify_file_access``.
        symbols: Dict with 'success', 'failure', 'warning' keys.
        label: Row label, e.g. the project name.

    Returns:
        A single-row list (without the title header).
    """
    entry = result["rules_file"]
    ok = entry.get("ok")
    if ok is True:
        marker = symbols["success"]
    elif ok is False:
        marker = symbols["failure"]
    else:
        marker = symbols["warning"]
    value = str(entry.get("value", ""))
    if ok is False and entry.get("error"):
        value = f"{value} ({entry['error']})"
    return [Row(label, marker, value, wrap=ok is False)]
