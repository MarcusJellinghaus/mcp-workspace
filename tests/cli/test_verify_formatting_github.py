"""Tests for the GITHUB and GITHUB SECURITY verify section formatters."""

from typing import Any

import pytest
from mcp_coder_utils.verify_render import STATUS_SYMBOLS

from mcp_workspace.cli.verify_formatting import (
    _LABEL_MAP,
    format_github_section,
    format_github_security_section,
)

from .verify_test_helpers import (
    MARKER_RE,
    SYMBOLS,
    VALUE_COL,
    assert_section_aligned,
    assert_value_at_column,
    has_row,
    render,
    row,
)


class TestBranchProtectionNesting:
    """Branch protection parent/children rendering."""

    def test_children_indented_when_parent_ok(self) -> None:
        """Children render at 4-space indent under parent when ok=True."""
        result: dict[str, Any] = {
            "branch_protection": {"ok": True, "value": "main protected"},
            "require_pull_request": {"ok": True, "value": "required"},
            "ci_checks_required": {"ok": True, "value": "8 checks configured"},
            "strict_mode": {"ok": True, "value": "enabled"},
            "force_push": {"ok": True, "value": "disabled"},
            "branch_deletion": {"ok": True, "value": "disabled"},
            "overall_ok": True,
        }
        output = render(format_github_section(result, SYMBOLS))
        assert output.splitlines() == [
            row("Branch protection", "[OK]", "main protected"),
            row("Require pull request", "[OK]", "required", indent=4),
            row("CI checks required", "[OK]", "8 checks configured", indent=4),
            row("Strict mode", "", "enabled", indent=4),
            row("Force push", "[OK]", "disabled", indent=4),
            row("Branch deletion", "[OK]", "disabled", indent=4),
        ]

    def test_children_suppressed_when_parent_fails(self) -> None:
        """Only the parent line appears when branch_protection ok=False."""
        child = {"ok": False, "value": "unknown", "error": "no protection"}
        result: dict[str, Any] = {
            "branch_protection": {
                "ok": False,
                "value": "not configured",
                "severity": "warning",
            },
            "require_pull_request": dict(child),
            "ci_checks_required": dict(child),
            "strict_mode": dict(child),
            "force_push": dict(child),
            "branch_deletion": dict(child),
            "overall_ok": False,
        }
        output = render(format_github_section(result, SYMBOLS))
        assert output == row("Branch protection", "[ERR]", "not configured")

    def test_children_suppressed_when_parent_unverifiable(self) -> None:
        """Parent shows [WARN] plus its error note; children suppressed."""
        value = "not verifiable — token lacks Administration: Read"
        error = (
            "get_protection failed: HTTP 403: "
            "Resource not accessible by personal access token"
        )
        entry = {"ok": None, "value": value, "error": error, "severity": "warning"}
        result: dict[str, Any] = {
            "branch_protection": dict(entry),
            "require_pull_request": dict(entry),
            "ci_checks_required": dict(entry),
            "strict_mode": dict(entry),
            "force_push": dict(entry),
            "branch_deletion": dict(entry),
            "overall_ok": True,
        }
        output = render(format_github_section(result, SYMBOLS))
        assert output == row("Branch protection", "[WARN]", f"{value} ({error})")

    def test_strict_mode_no_symbol(self) -> None:
        """strict_mode renders value only — no status marker."""
        result: dict[str, Any] = {
            "branch_protection": {"ok": True, "value": "main protected"},
            "strict_mode": {"ok": True, "value": "enabled"},
            "overall_ok": True,
        }
        lines = render(format_github_section(result, SYMBOLS)).splitlines()
        strict_line = next(line for line in lines if "Strict mode" in line)
        assert strict_line == row("Strict mode", "", "enabled", indent=4)
        assert MARKER_RE.search(strict_line) is None

    def test_unverifiable_child_shows_error(self) -> None:
        """ok=None child under an [OK] parent shows [WARN] with its error note."""
        result: dict[str, Any] = {
            "branch_protection": {"ok": True, "value": "main protected"},
            "require_pull_request": {
                "ok": None,
                "value": "not verifiable — HTTP 403",
                "error": "rulesets not verifiable: HTTP 403",
            },
            "overall_ok": True,
        }
        output = render(format_github_section(result, SYMBOLS))
        expected = row(
            "Require pull request",
            "[WARN]",
            "not verifiable — HTTP 403 (rulesets not verifiable: HTTP 403)",
            indent=4,
        )
        assert expected in output.splitlines()

    def test_unverifiable_parent_shows_error(self) -> None:
        """ok=None branch_protection shows its error; other ok=None rows do not."""
        result: dict[str, Any] = {
            "branch_protection": {
                "ok": None,
                "value": "not verifiable — HTTP 403",
                "error": "rulesets not verifiable: HTTP 403",
            },
            "auto_delete_branches": {
                "ok": None,
                "value": "unknown",
                "error": "repository not accessible",
            },
            "overall_ok": True,
        }
        output = render(format_github_section(result, SYMBOLS))
        assert output.splitlines() == [
            row(
                "Branch protection",
                "[WARN]",
                "not verifiable — HTTP 403 (rulesets not verifiable: HTTP 403)",
            ),
            row("Auto-delete branches", "[WARN]", "unknown"),
        ]

    def test_ok_rows_hide_error(self) -> None:
        """ok=True parent and child rows never show their error note."""
        result: dict[str, Any] = {
            "branch_protection": {
                "ok": True,
                "value": "main protected (ruleset)",
                "error": "get_protection failed: HTTP 403",
            },
            "require_pull_request": {
                "ok": True,
                "value": "required",
                "error": "get_protection failed: HTTP 403",
            },
            "overall_ok": True,
        }
        output = render(format_github_section(result, SYMBOLS))
        assert "get_protection failed" not in output

    def test_children_without_parent_suppressed(self) -> None:
        """Children with no preceding branch_protection row are not rendered."""
        result: dict[str, Any] = {
            "require_pull_request": {"ok": True, "value": "required"},
            "overall_ok": True,
        }
        assert not format_github_section(result, SYMBOLS)


class TestGitHubLabelMappings:
    """GitHub label mappings."""

    _GITHUB_KEYS = (
        "api_base_url",
        "network_proxy",
        "token_configured",
        "authenticated_user",
        "repo_url",
        "repo_accessible",
        "branch_protection",
        "ci_checks_required",
        "strict_mode",
        "force_push",
        "branch_deletion",
        "require_pull_request",
        "auto_delete_branches",
        "perm_contents_read",
        "perm_administration_read",
        "perm_pull_requests_read",
        "perm_issues_read",
        "perm_workflows_read",
        "perm_statuses_read",
    )

    def test_all_github_keys_in_label_map(self) -> None:
        """All GitHub check keys exist in _LABEL_MAP."""
        for key in self._GITHUB_KEYS:
            assert key in _LABEL_MAP, f"Missing key: {key}"

    def test_renders_github_labels(self) -> None:
        """Human-readable labels replace the raw GitHub keys."""
        proxy = "api=api.x.ghe.com:443 tcp=timeout proxy_env=HTTPS_PROXY pac=present"
        result: dict[str, Any] = {
            "token_configured": {"ok": True, "value": "YES"},
            "repo_accessible": {"ok": True, "value": "owner/repo"},
            "network_proxy": {"ok": False, "value": proxy},
            "overall_ok": True,
        }
        output = render(format_github_section(result, SYMBOLS))
        assert output.splitlines() == [
            row("Token configured", "[OK]", "YES"),
            row("Repo accessible", "[OK]", "owner/repo"),
            row("Network / proxy", "[ERR]", proxy),
        ]
        assert "network_proxy" not in output

    def test_github_error_entry(self) -> None:
        """Entry with ok=False renders [ERR] and its error."""
        result: dict[str, Any] = {
            "token_configured": {
                "ok": False,
                "value": "not set",
                "error": "GITHUB_TOKEN not found",
            },
            "overall_ok": False,
        }
        output = render(format_github_section(result, SYMBOLS))
        assert output == row(
            "Token configured", "[ERR]", "not set (GITHUB_TOKEN not found)"
        )


class TestAutoDeleteBranches:
    """auto_delete_branches renders at the top level of the GITHUB section."""

    @pytest.mark.parametrize(
        "entry, marker, value",
        [
            ({"ok": True, "value": "enabled"}, "[OK]", "enabled"),
            ({"ok": False, "value": "disabled"}, "[ERR]", "disabled"),
            (
                {
                    "ok": False,
                    "value": "unknown",
                    "error": "repository not accessible",
                },
                "[ERR]",
                "unknown (repository not accessible)",
            ),
        ],
    )
    def test_value_cases(self, entry: dict[str, Any], marker: str, value: str) -> None:
        """2-space indent, symbol from ok, value, optional error suffix."""
        result: dict[str, Any] = {
            "auto_delete_branches": entry,
            "overall_ok": entry["ok"] is True,
        }
        output = render(format_github_section(result, SYMBOLS))
        assert output == row("Auto-delete branches", marker, value)

    def test_renders_when_branch_protection_failed(self) -> None:
        """auto_delete_branches is not suppressed when branch_protection failed."""
        result: dict[str, Any] = {
            "branch_protection": {"ok": False, "value": "main is not protected"},
            "auto_delete_branches": {"ok": True, "value": "enabled"},
            "overall_ok": False,
        }
        output = render(format_github_section(result, SYMBOLS))
        assert row("Auto-delete branches", "[OK]", "enabled") in output.splitlines()


class TestApiBaseUrlRendering:
    """api_base_url row rendering in the GITHUB section."""

    @pytest.mark.parametrize(
        "entry, marker, value",
        [
            pytest.param(
                {"ok": True, "value": "https://api.example.ghe.com"},
                "[OK]",
                "https://api.example.ghe.com",
                id="success-renders-ok",
            ),
            pytest.param(
                {
                    "ok": False,
                    "severity": "warning",
                    "value": "https://api.github.com (fallback - identifier unresolved)",
                    "error": "Could not determine repository URL from git remote",
                },
                "[ERR]",
                "https://api.github.com (fallback - identifier unresolved) "
                "(Could not determine repository URL from git remote)",
                id="fallback-severity-warning-renders-err",
            ),
        ],
    )
    def test_value_cases(self, entry: dict[str, Any], marker: str, value: str) -> None:
        """api_base_url renders symbol from ok and precedes Token configured."""
        result: dict[str, Any] = {
            "api_base_url": entry,
            "token_configured": {"ok": True, "value": "configured"},
            "overall_ok": entry["ok"] is True,
        }
        output = render(format_github_section(result, SYMBOLS))
        assert output.splitlines() == [
            row("API base URL", marker, value),
            row("Token configured", "[OK]", "configured"),
        ]


class TestTokenSourceHint:
    """token_source / token_fingerprint hint below the Token configured row."""

    @staticmethod
    def _result(token_source: str, fingerprint: str | None = None) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "ok": True,
            "value": "configured (scopes: repo, workflow)",
            "token_source": token_source,
        }
        if fingerprint is not None:
            entry["token_fingerprint"] = fingerprint
        return {"token_configured": entry, "overall_ok": True}

    @pytest.mark.parametrize(
        "token_source, hint",
        [
            ("env", "from GITHUB_TOKEN env var"),
            ("config", "from ~/.mcp_coder/config.toml"),
        ],
    )
    def test_source_renders_second_line(self, token_source: str, hint: str) -> None:
        """The source hint starts at the value column."""
        output = render(format_github_section(self._result(token_source), SYMBOLS))
        assert output.splitlines() == [
            row("Token configured", "[OK]", "configured (scopes: repo, workflow)"),
            " " * VALUE_COL + hint,
        ]

    @pytest.mark.parametrize(
        "fingerprint, expected",
        [
            pytest.param(
                "ghp_...a3f9",
                "from ~/.mcp_coder/config.toml (ghp_...a3f9)",
                id="normal-token",
            ),
            pytest.param(
                "****", "from ~/.mcp_coder/config.toml (****)", id="short-token"
            ),
            pytest.param(None, "from ~/.mcp_coder/config.toml", id="absent"),
        ],
    )
    def test_fingerprint_suffix(self, fingerprint: str | None, expected: str) -> None:
        """Fingerprint is appended in parens to the 'from <source>' hint."""
        output = render(
            format_github_section(self._result("config", fingerprint), SYMBOLS)
        )
        assert output.splitlines()[1] == " " * VALUE_COL + expected

    def test_env_source_with_fingerprint(self) -> None:
        """Env source carries the fingerprint suffix too."""
        output = render(
            format_github_section(self._result("env", "ghp_...a3f9"), SYMBOLS)
        )
        assert output.splitlines()[1] == (
            " " * VALUE_COL + "from GITHUB_TOKEN env var (ghp_...a3f9)"
        )

    def test_no_hint_without_token_source(self) -> None:
        """No hint line when token_source is absent."""
        result: dict[str, Any] = {
            "token_configured": {"ok": True, "value": "configured"},
            "overall_ok": True,
        }
        output = render(format_github_section(result, SYMBOLS))
        assert output == row("Token configured", "[OK]", "configured")


_PERM_LABELS: tuple[str, ...] = (
    "Contents: Read",
    "Administration: Read",
    "Pull requests: Read",
    "Issues: Read",
    "Actions: Read",
    "Commit statuses: Read",
)

_PERM_KEYS: tuple[str, ...] = (
    "perm_contents_read",
    "perm_administration_read",
    "perm_pull_requests_read",
    "perm_issues_read",
    "perm_workflows_read",
    "perm_statuses_read",
)


class TestPermissionProbes:
    """[Permissions] subsection rendering."""

    @staticmethod
    def _all_ok_result() -> dict[str, Any]:
        result: dict[str, Any] = {
            "auto_delete_branches": {"ok": True, "value": "enabled"},
        }
        for key in _PERM_KEYS:
            result[key] = {"ok": True, "value": "granted"}
        result["overall_ok"] = True
        return result

    def test_all_ok(self) -> None:
        """Every perm_* row renders [OK] granted at indent 4."""
        output = render(format_github_section(self._all_ok_result(), SYMBOLS))
        for label in _PERM_LABELS:
            assert has_row(output, label, "[OK]", "granted"), label
        assert assert_section_aligned(output) == 7

    def test_one_missing(self) -> None:
        """A denied permission renders [ERR] with its error; others stay [OK]."""
        result = self._all_ok_result()
        result["perm_workflows_read"] = {
            "ok": False,
            "value": "denied",
            "error": "https://docs.github.com/...#workflows",
        }
        output = render(format_github_section(result, SYMBOLS))
        assert has_row(
            output,
            "Actions: Read",
            "[ERR]",
            "denied (https://docs.github.com/...#workflows)",
        )
        for label in _PERM_LABELS:
            if label != "Actions: Read":
                assert has_row(output, label, "[OK]", "granted"), label
        assert_section_aligned(output)

    def test_repo_inaccessible(self) -> None:
        """Unchecked permissions render [ERR] with the shared error."""
        err = "repository not accessible"
        result: dict[str, Any] = {
            "auto_delete_branches": {"ok": True, "value": "enabled"},
        }
        for key in _PERM_KEYS:
            result[key] = {"ok": False, "value": "not checked", "error": err}
        result["overall_ok"] = False
        output = render(format_github_section(result, SYMBOLS))
        for label in _PERM_LABELS:
            assert has_row(output, label, "[ERR]", f"not checked ({err})"), label
        assert_section_aligned(output)

    def test_header_appears_once_after_auto_delete_branches(self) -> None:
        """A blank line and [Permissions] header precede the first perm_* row."""
        lines = format_github_section(self._all_ok_result(), SYMBOLS)
        assert lines.count("  [Permissions]") == 1
        assert lines[1:3] == ["", "  [Permissions]"]
        output = render(lines).splitlines()
        assert output[1] == ""
        assert output[2] == "  [Permissions]"

    def test_actions_read_at_indent_4(self) -> None:
        """perm_* rows sit at indent 4 and share the section's columns."""
        output = render(format_github_section(self._all_ok_result(), SYMBOLS))
        assert any(line.startswith("    Actions: Read ") for line in output.split("\n"))


def test_github_permissions_section_aligned_with_token_hint() -> None:
    """GITHUB widens to fit "Commit statuses: Read" at indent 4; hint follows."""
    granted = {"ok": True, "value": "granted"}
    result: dict[str, Any] = {
        "token_configured": {"ok": True, "value": "YES", "token_source": "env"},
        "repo_accessible": {"ok": True, "value": "owner/repo"},
        **{f"perm_{k}_read": dict(granted) for k in ("contents", "statuses")},
        "overall_ok": True,
    }
    text = render(format_github_section(result, STATUS_SYMBOLS))
    col = 33  # label width 23 = len("Commit statuses: Read") + 2 extra indent
    assert assert_section_aligned(text) == 4
    for line in text.splitlines():
        if "[OK]" in line:
            assert_value_at_column(line, col)
    hint = next(line for line in text.splitlines() if "GITHUB_TOKEN" in line)
    assert hint == " " * col + "from GITHUB_TOKEN env var"


class TestGitHubSecuritySection:
    """format_github_security_section renders the security labels."""

    def test_security_labels_render(self) -> None:
        """Every security key maps to its label."""
        result: dict[str, Any] = {
            "dependabot_config": {"ok": True, "value": ".github/dependabot.yml"},
            "dependabot_alerts": {"ok": True, "value": "enabled"},
            "dependabot_security_updates": {"ok": None, "value": "unknown"},
            "secret_scanning": {"ok": True, "value": "enabled"},
            "secret_scanning_push_protection": {"ok": False, "value": "disabled"},
            "codeql_workflow": {"ok": True, "value": ".github/workflows/codeql.yml"},
            "code_scanning_alerts": {"ok": True, "value": "scope present"},
        }
        output = render(format_github_security_section(result, SYMBOLS))
        assert output.splitlines() == [
            row("Dependabot config", "[OK]", ".github/dependabot.yml"),
            row("Dependabot alerts", "[OK]", "enabled"),
            row("Dependabot security", "[WARN]", "unknown"),
            row("Secret scanning", "[OK]", "enabled"),
            row("Secret push protection", "[ERR]", "disabled"),
            row("CodeQL workflow", "[OK]", ".github/workflows/codeql.yml"),
            row("Code scanning alerts", "[OK]", "scope present"),
        ]
