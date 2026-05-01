"""Pure helpers for git_operations.verification.

Contains decision/classification helpers that operate on already-collected
inputs (config values, file existence). Has no direct subprocess use; the
:mod:`mcp_workspace.git_operations.verification` module remains the sole
chokepoint for ``subprocess`` calls in this package.
"""

from __future__ import annotations

from typing import Literal, NotRequired, Optional, TypedDict

PROBE_PAYLOAD = "mcp-workspace verify_git probe"


class CheckResult(TypedDict):
    """Result of a single verification check."""

    ok: bool
    value: str
    severity: Literal["error", "warning"]
    error: NotRequired[str]
    install_hint: NotRequired[str]


def build_user_identity_result(
    name: Optional[str], email: Optional[str]
) -> "CheckResult":
    """Construct the user_identity CheckResult from raw config values."""
    missing = [
        label
        for label, value in (("user.name", name), ("user.email", email))
        if value is None
    ]
    if missing:
        return CheckResult(
            ok=False,
            value=f"missing: {', '.join(missing)}",
            severity="error",
            error=f"git config missing: {', '.join(missing)}",
            install_hint=(
                "Set user.name and user.email via "
                "'git config --global user.{name,email}'"
            ),
        )
    return CheckResult(
        ok=True,
        value=f"{name} <{email}>",
        severity="error",
    )


def build_signing_intent_result(flags_truthy: dict[str, bool]) -> "CheckResult":
    """Construct the signing_intent CheckResult from per-flag truthy map."""
    if not any(flags_truthy.values()):
        return CheckResult(
            ok=True,
            value="not configured",
            severity="warning",
            install_hint=(
                "Enable signing with 'git config --global commit.gpgsign true' "
                "(and set user.signingkey)."
            ),
        )
    enabled = [k for k, v in flags_truthy.items() if v]
    return CheckResult(
        ok=True,
        value=f"detected: {', '.join(enabled)}",
        severity="warning",
    )


def build_signing_consistency_result(flags_truthy: dict[str, bool]) -> "CheckResult":
    """Construct the signing_consistency CheckResult from the flag map."""
    if not flags_truthy.get("commit.gpgsign"):
        return CheckResult(
            ok=True,
            value="not applicable",
            severity="warning",
        )
    rebase_label = (
        "rebase ok" if flags_truthy["rebase.gpgSign"] else "rebase.gpgSign unset"
    )
    tag_label = "tag ok" if flags_truthy["tag.gpgsign"] else "tag.gpgsign unset"
    consistency_errors: list[str] = []
    if not flags_truthy["rebase.gpgSign"]:
        consistency_errors.append(
            "rebase.gpgSign unset → rebased commits unsigned on git < 2.36"
        )
    if not flags_truthy["tag.gpgsign"]:
        consistency_errors.append("tag.gpgsign unset → tags will be unsigned")
    consistency = CheckResult(
        ok=not consistency_errors,
        value=f"{rebase_label}; {tag_label}",
        severity="warning",
    )
    if consistency_errors:
        consistency["error"] = "; ".join(consistency_errors)
    return consistency


def classify_signing_format(
    raw_format: Optional[str],
) -> tuple[str, "CheckResult"]:
    """Resolve the configured signing format and build its CheckResult.

    Returns a tuple ``(resolved_format, check_result)``. ``resolved_format``
    is one of ``"openpgp"``, ``"ssh"``, ``"x509"`` (defaulting to
    ``"openpgp"`` when unset or invalid).
    """
    if raw_format is None:
        return "openpgp", CheckResult(
            ok=True,
            value="openpgp (default)",
            severity="error",
        )
    if raw_format in ("openpgp", "ssh", "x509"):
        return raw_format, CheckResult(
            ok=True,
            value=raw_format,
            severity="error",
        )
    return "openpgp", CheckResult(
        ok=False,
        value=f"unknown: {raw_format}",
        severity="error",
        error=f"gpg.format must be openpgp, ssh, or x509 (got '{raw_format}')",
    )


def build_signing_key_result(
    signing_key: Optional[str], commit_gpgsign: bool
) -> "CheckResult":
    """Construct the signing_key CheckResult per Decision #10 severity rules."""
    if signing_key is None:
        sev: Literal["error", "warning"] = "error" if commit_gpgsign else "warning"
        return CheckResult(
            ok=False,
            value="not set",
            severity=sev,
            error="user.signingkey is not configured",
            install_hint=(
                "Set user.signingkey via 'git config --global user.signingkey <ID>'"
            ),
        )
    return CheckResult(
        ok=True,
        value="configured",
        severity="error",
    )


def signing_binary_install_hint(format_resolved: str) -> str:
    """Return the install hint string for the resolved signing format."""
    return {
        "openpgp": (
            "Install Gpg4win (Windows) or 'gpg' (Linux/Mac), or set gpg.format=ssh"
        ),
        "ssh": "Install OpenSSH >= 8.0 (provides ssh-keygen)",
        "x509": "Install gpgsm (part of GnuPG) or set gpg.format=openpgp",
    }.get(format_resolved, "")
