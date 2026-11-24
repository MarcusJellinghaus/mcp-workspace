"""Tests for the shared row rendering, GIT and FILE ACCESS verify formatters."""

from typing import Any

import pytest
from mcp_coder_utils.verify_render import Row

from mcp_workspace.cli.verify_formatting import (
    _LABEL_MAP,
    format_file_access_section,
    format_git_section,
    format_github_section,
)

from .verify_test_helpers import (
    DEFAULT_LABEL_WIDTH,
    SYMBOLS,
    VALUE_COL,
    assert_value_at_column,
    render,
    row,
)


class TestFormatSection:
    """Basic row rendering shared by all git/GitHub sections."""

    def test_ok_entry_formatted_with_success_symbol(self) -> None:
        """Entries with ok=True show [OK] symbol and value."""
        result: dict[str, Any] = {
            "git_binary": {"ok": True, "value": "git 2.45.0"},
            "overall_ok": True,
        }
        output = render(format_git_section(result, SYMBOLS))
        assert output == row("Git binary", "[OK]", "git 2.45.0")

    def test_failed_entry_formatted_with_failure_symbol(self) -> None:
        """Entries with ok=False show [ERR] symbol and value."""
        result: dict[str, Any] = {
            "repo_url": {"ok": False, "value": "unknown"},
            "overall_ok": False,
        }
        output = render(format_github_section(result, SYMBOLS))
        assert output == row("Repo URL", "[ERR]", "unknown")

    def test_skipped_entry_formatted(self) -> None:
        """Entries with ok=None show [WARN] and hide the error."""
        result: dict[str, Any] = {
            "signing_key": {"ok": None, "value": "skipped", "error": "not needed"},
            "overall_ok": True,
        }
        output = render(format_git_section(result, SYMBOLS))
        assert output == row("Signing key", "[WARN]", "skipped")

    def test_error_shown_on_failure(self) -> None:
        """Error message appended when ok=False and error is present."""
        result: dict[str, Any] = {
            "git_repo": {"ok": False, "value": "missing", "error": "not a repo"},
            "overall_ok": False,
        }
        output = render(format_git_section(result, SYMBOLS))
        assert output == row("Repository", "[ERR]", "missing (not a repo)")

    def test_install_hint_rendered_when_failed(self) -> None:
        """install_hint renders as a '-> hint' row at the value column."""
        result: dict[str, Any] = {
            "git_binary": {
                "ok": False,
                "value": "not found",
                "install_hint": "install git from git-scm.com",
            },
            "overall_ok": False,
        }
        lines = render(format_git_section(result, SYMBOLS)).splitlines()
        assert lines == [
            row("Git binary", "[ERR]", "not found"),
            " " * VALUE_COL + "-> install git from git-scm.com",
        ]

    @pytest.mark.parametrize("ok", [True, None])
    def test_install_hint_hidden_unless_failed(self, ok: bool | None) -> None:
        """install_hint is not rendered for ok=True or ok=None."""
        result: dict[str, Any] = {
            "git_binary": {"ok": ok, "value": "x", "install_hint": "install git"},
            "overall_ok": True,
        }
        output = render(format_git_section(result, SYMBOLS))
        assert "install git" not in output
        assert len(output.splitlines()) == 1

    def test_overall_ok_and_non_dict_entries_skipped(self) -> None:
        """overall_ok and non-dict values produce no rows."""
        result: dict[str, Any] = {
            "git_binary": {"ok": True, "value": "git 2.45.0"},
            "note": "not a check",
            "count": 3,
            "overall_ok": True,
        }
        lines = format_git_section(result, SYMBOLS)
        assert len(lines) == 1
        output = render(lines)
        assert "overall_ok" not in output
        assert "not a check" not in output

    def test_unknown_key_passes_through_unmapped(self) -> None:
        """Keys missing from the label map render under their raw name."""
        result: dict[str, Any] = {"custom_check": {"ok": True, "value": "fine"}}
        output = render(format_git_section(result, SYMBOLS))
        assert output == row("custom_check", "[OK]", "fine")

    def test_git_section_entries_flat(self) -> None:
        """Git section entries stay at 2-space indent."""
        result: dict[str, Any] = {
            "git_binary": {"ok": True, "value": "git 2.45.0"},
            "user_identity": {"ok": True, "value": "Jane <jane@example.com>"},
            "overall_ok": True,
        }
        for line in render(format_git_section(result, SYMBOLS)).splitlines():
            assert line.startswith("  ")
            assert not line.startswith("   ")


class TestGitLabelMappings:
    """GIT section label mappings and rendering."""

    _GIT_KEYS = (
        "git_binary",
        "git_repo",
        "user_identity",
        "signing_intent",
        "signing_consistency",
        "signing_format",
        "signing_key",
        "signing_binary",
        "signing_key_accessible",
        "agent_reachable",
        "allowed_signers",
        "verify_head",
        "actual_signature",
    )

    def test_all_git_keys_in_label_map(self) -> None:
        """All git check keys exist in _LABEL_MAP."""
        for key in self._GIT_KEYS:
            assert key in _LABEL_MAP, f"Missing key: {key}"

    def test_renders_git_section(self) -> None:
        """Git labels, markers and error suffix render."""
        result: dict[str, Any] = {
            "git_binary": {"ok": True, "value": "git 2.45.0"},
            "signing_intent": {"ok": True, "value": "not configured"},
            "signing_key": {
                "ok": False,
                "value": "missing",
                "error": "user.signingkey unset",
            },
            "overall_ok": False,
        }
        output = render(format_git_section(result, SYMBOLS))
        assert output.splitlines() == [
            row("Git binary", "[OK]", "git 2.45.0"),
            row("Signing enabled", "[OK]", "not configured"),
            row("Signing key", "[ERR]", "missing (user.signingkey unset)"),
        ]


def test_fixed_labels_fit_default_width() -> None:
    """Every fixed label fits the default label width at indent 2."""
    too_long = {k: v for k, v in _LABEL_MAP.items() if len(v) > DEFAULT_LABEL_WIDTH}
    assert not too_long, f"labels wider than {DEFAULT_LABEL_WIDTH}: {too_long}"


class TestFileAccessSection:
    """format_file_access_section renders one rules-file row."""

    @staticmethod
    def _result(entry: dict[str, Any]) -> dict[str, Any]:
        return {"rules_file": entry, "overall_ok": entry.get("ok") is True}

    def test_default_label(self) -> None:
        """The default label is .mcp-file-access."""
        result = self._result({"ok": True, "value": "3 rules", "severity": "error"})
        output = render(format_file_access_section(result, SYMBOLS))
        assert output == row(".mcp-file-access", "[OK]", "3 rules")

    def test_custom_label(self) -> None:
        """A caller-supplied label replaces the default."""
        result = self._result({"ok": True, "value": "3 rules", "severity": "error"})
        output = render(format_file_access_section(result, SYMBOLS, label="workspace"))
        assert output == "  workspace              [OK]   3 rules"

    def test_absent(self) -> None:
        """An absent rules file renders [OK]."""
        result = self._result(
            {"ok": True, "value": "absent - gitignore only", "severity": "error"}
        )
        output = render(format_file_access_section(result, SYMBOLS, label="mcp_coder"))
        assert output == "  mcp_coder              [OK]   absent - gitignore only"

    def test_invalid_shows_error(self) -> None:
        """An invalid rules file renders [ERR] with its problems."""
        result = self._result(
            {
                "ok": False,
                "value": "invalid",
                "severity": "error",
                "error": "line 4: bad pattern",
            }
        )
        output = render(format_file_access_section(result, SYMBOLS))
        assert output == "  .mcp-file-access       [ERR]  invalid (line 4: bad pattern)"

    def test_ok_none_renders_warning(self) -> None:
        """ok=None renders [WARN] without the error."""
        result = self._result({"ok": None, "value": "path not found", "error": "x"})
        output = render(format_file_access_section(result, SYMBOLS, label="docs"))
        assert output == "  docs                   [WARN] path not found"

    def test_only_invalid_row_wraps(self) -> None:
        """Only an ok=False row is marked for wrapping."""
        ok_lines = format_file_access_section(
            self._result({"ok": True, "value": "3 rules"}), SYMBOLS
        )
        bad_lines = format_file_access_section(
            self._result({"ok": False, "value": "invalid", "error": "e"}), SYMBOLS
        )
        assert [line.wrap for line in ok_lines if isinstance(line, Row)] == [False]
        assert [line.wrap for line in bad_lines if isinstance(line, Row)] == [True]

    def test_long_problem_wraps_at_80_columns(self) -> None:
        """A long error wraps at 80 columns with continuation at the value column."""
        problems = "; ".join(
            f"line {n}: pattern 'some/long/path/{n}/**' is not valid" for n in range(4)
        )
        result = self._result(
            {"ok": False, "value": "invalid", "severity": "error", "error": problems}
        )
        lines = render(format_file_access_section(result, SYMBOLS)).splitlines()
        assert len(lines) > 1
        assert lines[0].startswith("  .mcp-file-access       [ERR]  invalid (line 0:")
        for line in lines:
            assert len(line) <= 80, line
        for line in lines[1:]:
            assert_value_at_column(line, VALUE_COL)
        assert " ".join(line[VALUE_COL:] for line in lines) == f"invalid ({problems})"
