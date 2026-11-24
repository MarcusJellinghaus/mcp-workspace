"""Tests for execute_verify: section output and exit code."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any, NamedTuple
from unittest.mock import MagicMock, patch

import pytest

from mcp_workspace.cli.verify import execute_verify
from mcp_workspace.file_tools.access_rules import ACCESS_RULES_FILE
from mcp_workspace.github_operations.security_rows import github_security_rows
from mcp_workspace.reference_projects import ReferenceProject

from .verify_test_helpers import VALUE_COL, assert_section_aligned, row

_VERIFY = "mcp_workspace.cli.verify"
_SECURITY_PROBE = "mcp_workspace.github_operations.security_rows.verify_github_security"

_SECURITY_API_KEYS = (
    "dependabot_alerts",
    "dependabot_security_updates",
    "secret_scanning",
    "secret_scanning_push_protection",
    "code_scanning_alerts",
)
_SECURITY_API_LABELS = (
    "Dependabot alerts",
    "Dependabot security",
    "Secret scanning",
    "Secret push protection",
    "Code scanning alerts",
)


class Mocks(NamedTuple):
    """Patched collaborators of execute_verify."""

    verify_git: MagicMock
    verify_github: MagicMock
    security_rows: MagicMock
    ensure_truststore: MagicMock
    set_traffic_log_context: MagicMock


@pytest.fixture(name="mocks", autouse=True)
def fixture_mocks() -> Iterator[Mocks]:
    """Patch git, GitHub and security checks to ok, and the startup hooks."""
    with (
        patch(f"{_VERIFY}.verify_git", return_value={"overall_ok": True}) as git,
        patch(f"{_VERIFY}.verify_github", return_value={"overall_ok": True}) as gh,
        patch(f"{_VERIFY}.github_security_rows", return_value={}) as security,
        patch(f"{_VERIFY}.ensure_truststore") as truststore,
        patch(f"{_VERIFY}.set_traffic_log_context") as context,
    ):
        yield Mocks(git, gh, security, truststore, context)


@pytest.fixture(name="workspace")
def fixture_workspace(tmp_path: Path) -> Path:
    """An empty workspace directory (no rules file)."""
    path = tmp_path / "ws"
    path.mkdir()
    return path


def _make_dir(tmp_path: Path, name: str, rules: str | None = None) -> Path:
    """Create ``tmp_path/name``, with a rules file when ``rules`` is given."""
    path = tmp_path / name
    path.mkdir()
    if rules is not None:
        (path / ACCESS_RULES_FILE).write_text(rules, encoding="utf-8")
    return path


def _section(output: str, title: str) -> list[str]:
    """Return the lines of section ``title``, up to the next blank line."""
    lines = output.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"=== {title} "))
    body: list[str] = []
    for line in lines[start + 1 :]:
        if not line:
            break
        body.append(line)
    return body


def _security_api(**row: Any) -> dict[str, Any]:
    """Five API-backed security rows, each a copy of ``row``."""
    return {key: dict(row) for key in _SECURITY_API_KEYS}


class TestSetup:
    """Startup hooks, check arguments and section order."""

    def test_sections_in_order(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """FILE ACCESS, GIT, GITHUB, GITHUB SECURITY headers in that order."""
        execute_verify(workspace, {}, [])
        lines = capsys.readouterr().out.splitlines()
        positions = [
            next(i for i, line in enumerate(lines) if line.startswith(f"=== {t} "))
            for t in ("FILE ACCESS", "GIT", "GITHUB", "GITHUB SECURITY")
        ]
        assert positions == sorted(positions)

    def test_startup_hooks_and_check_arguments(
        self, mocks: Mocks, workspace: Path
    ) -> None:
        """Truststore once, traffic-log command name, signing probe enabled."""
        execute_verify(workspace, {}, [])
        mocks.ensure_truststore.assert_called_once_with()
        mocks.set_traffic_log_context.assert_called_once_with(
            command="mcp-workspace verify"
        )
        mocks.verify_git.assert_called_once_with(workspace, actually_sign=True)
        mocks.verify_github.assert_called_once_with(workspace)
        mocks.security_rows.assert_called_once_with(workspace)


class TestFileAccessSection:
    """Rows of the FILE ACCESS section and their exit-code effect."""

    def test_all_ok(
        self,
        workspace: Path,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Workspace first, then references in dict order; exit 0."""
        (workspace / ACCESS_RULES_FILE).write_text(
            "read-only /a\nread-write /b\nread-only /c\n", encoding="utf-8"
        )
        refs = {
            "zeta": ReferenceProject("zeta", _make_dir(tmp_path, "zeta")),
            "alpha": ReferenceProject(
                "alpha", _make_dir(tmp_path, "alpha", "read-only /x\n")
            ),
        }

        assert execute_verify(workspace, refs, []) == 0
        assert _section(capsys.readouterr().out, "FILE ACCESS") == [
            row("workspace", "[OK]", "3 rules"),
            row("zeta", "[OK]", "absent - gitignore only"),
            row("alpha", "[OK]", "1 rules"),
        ]

    def test_invalid_workspace_rules_exit_1(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """An invalid workspace rules file renders [ERR] and fails the run."""
        (workspace / ACCESS_RULES_FILE).write_text("readonly /a\n", encoding="utf-8")

        assert execute_verify(workspace, {}, []) == 1
        assert _section(capsys.readouterr().out, "FILE ACCESS") == [
            row("workspace", "[ERR]", "invalid (line 1: unknown level 'readonly')"),
        ]

    def test_invalid_reference_rules_exit_1(
        self,
        workspace: Path,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """An invalid reference rules file renders [ERR] and fails the run."""
        ref = _make_dir(tmp_path, "ref", "readonly /a\n")

        assert execute_verify(workspace, {"ref": ReferenceProject("ref", ref)}, []) == 1
        assert _section(capsys.readouterr().out, "FILE ACCESS") == [
            row("workspace", "[OK]", "absent - gitignore only"),
            row("ref", "[ERR]", "invalid (line 1: unknown level 'readonly')"),
        ]

    def test_missing_reference_path_warns_exit_0(
        self,
        workspace: Path,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A reference whose path is gone renders [WARN] and keeps exit 0."""
        refs = {"gone": ReferenceProject("gone", tmp_path / "missing")}

        assert execute_verify(workspace, refs, []) == 0
        assert _section(capsys.readouterr().out, "FILE ACCESS") == [
            row("workspace", "[OK]", "absent - gitignore only"),
            row("gone", "[WARN]", "path not found"),
        ]

    def test_rejected_rows_last_exit_1(
        self,
        workspace: Path,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Rejected entries follow accepted references and fail the run."""
        refs = {"ok": ReferenceProject("ok", _make_dir(tmp_path, "ok"))}
        rejected = [("bad", "inside workspace"), ("old", "old format")]

        assert execute_verify(workspace, refs, rejected) == 1
        assert _section(capsys.readouterr().out, "FILE ACCESS") == [
            row("workspace", "[OK]", "absent - gitignore only"),
            row("ok", "[OK]", "absent - gitignore only"),
            row("bad", "[ERR]", "rejected: inside workspace"),
            row("old", "[ERR]", "rejected: old format"),
        ]

    def test_long_rejected_label_widens_section(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A long rejected label widens every FILE ACCESS row to one value column."""
        label = "name=a-very-long-reference-name,path=/somewhere"

        execute_verify(workspace, {}, [(label, "missing path")])
        section = _section(capsys.readouterr().out, "FILE ACCESS")

        width = len(label)
        assert section == [
            row("workspace", "[OK]", "absent - gitignore only", label_width=width),
            row(label, "[ERR]", "rejected: missing path", label_width=width),
        ]
        assert assert_section_aligned("\n".join(section)) == 2


class TestExitCode:
    """GIT and GITHUB overall_ok drive the exit code."""

    @pytest.mark.parametrize(
        ("git_ok", "github_ok", "expected"),
        [
            pytest.param(True, True, 0, id="both-ok"),
            pytest.param(False, True, 1, id="git-fails"),
            pytest.param(True, False, 1, id="github-fails"),
        ],
    )
    def test_overall_ok(
        self,
        mocks: Mocks,
        workspace: Path,
        git_ok: bool,
        github_ok: bool,
        expected: int,
    ) -> None:
        """Exit 1 when either GIT or GITHUB reports overall_ok False."""
        mocks.verify_git.return_value = {"overall_ok": git_ok}
        mocks.verify_github.return_value = {"overall_ok": github_ok}
        assert execute_verify(workspace, {}, []) == expected


class TestGithubSecuritySection:
    """GITHUB SECURITY section rendering; never affects the exit code."""

    @pytest.fixture(autouse=True)
    def fixture_real_security_rows(self, mocks: Mocks) -> None:
        """Run the real row assembly; tests patch only the API probe."""
        mocks.security_rows.side_effect = github_security_rows

    def test_section_renders_all_rows(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """All seven rows render with their labels."""
        with patch(_SECURITY_PROBE, return_value=_security_api(ok=True, value="on")):
            execute_verify(workspace, {}, [])
        section = _section(capsys.readouterr().out, "GITHUB SECURITY")

        assert [line[2:24].rstrip() for line in section] == [
            "Dependabot config",
            "Dependabot alerts",
            "Dependabot security",
            "Secret scanning",
            "Secret push protection",
            "CodeQL workflow",
            "Code scanning alerts",
        ]

    def test_exit_neutral_when_all_rows_fail(self, workspace: Path) -> None:
        """Exit 0 even when every security row fails."""
        api = _security_api(ok=False, value="disabled", severity="warning")
        with patch(_SECURITY_PROBE, return_value=api):
            assert execute_verify(workspace, {}, []) == 0

    def test_api_rows_pass_through_unmodified(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A 403-style ok=None row renders as [WARN] with its value unchanged."""
        api = _security_api(ok=True, value="enabled", severity="warning")
        api["secret_scanning"] = {
            "ok": None,
            "value": "not accessible (403)",
            "severity": "warning",
        }
        with patch(_SECURITY_PROBE, return_value=api):
            execute_verify(workspace, {}, [])
        section = _section(capsys.readouterr().out, "GITHUB SECURITY")

        assert row("Secret scanning", "[WARN]", "not accessible (403)") in section

    def test_no_token_rows_render_as_warn(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Unresolvable repository → each API row reads not accessible, exit 0."""
        api = _security_api(
            ok=None,
            value="not checked",
            severity="warning",
            error="repository not accessible",
        )
        with patch(_SECURITY_PROBE, return_value=api):
            result = execute_verify(workspace, {}, [])
        section = _section(capsys.readouterr().out, "GITHUB SECURITY")

        for label in _SECURITY_API_LABELS:
            expected = row(
                label, "[WARN]", "not accessible (repository not accessible)"
            )
            assert expected in section
        assert result == 0


class TestGithubTokenSource:
    """The token_source hint line under Token configured in GITHUB."""

    @pytest.mark.parametrize(
        ("token_source", "hint"),
        [
            pytest.param("env", "from GITHUB_TOKEN env var", id="env"),
            pytest.param("config", "from ~/.mcp_coder/config.toml", id="config"),
        ],
    )
    def test_hint_line_at_value_column(
        self,
        mocks: Mocks,
        workspace: Path,
        token_source: str,
        hint: str,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The hint renders on its own line starting at the value column."""
        mocks.verify_github.return_value = {
            "token_configured": {
                "ok": True,
                "value": "configured (scopes: repo, workflow)",
                "token_source": token_source,
            },
            "overall_ok": True,
        }

        execute_verify(workspace, {}, [])

        assert _section(capsys.readouterr().out, "GITHUB") == [
            row("Token configured", "[OK]", "configured (scopes: repo, workflow)"),
            f"{' ' * VALUE_COL}{hint}",
        ]
