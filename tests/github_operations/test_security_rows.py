"""Tests for ``github_security_rows`` and its local-file checks and row mapping.

The probe tests call the real ``verify_github_security`` with only
``BaseGitHubManager`` patched, so they pin the probe's value strings and the
no-token outcome that ``_map_security_row`` relies on. No live calls.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp_coder_utils.verify_render import STATUS_SYMBOLS, render_rows

from mcp_workspace.cli.verify_formatting import format_github_security_section
from mcp_workspace.github_operations import GithubException
from mcp_workspace.github_operations._types import CheckResult
from mcp_workspace.github_operations.security_rows import (
    _check_codeql_workflow,
    _check_dependabot_config,
    _map_security_row,
    github_security_rows,
)

_SECURITY_ROWS = "mcp_workspace.github_operations.security_rows"
_PROBES = "mcp_workspace.github_operations._security_probes"


def _write_dependabot(project_dir: Path, content: str) -> None:
    github_dir = project_dir / ".github"
    github_dir.mkdir(parents=True, exist_ok=True)
    (github_dir / "dependabot.yml").write_text(content, encoding="utf-8")


class TestCheckDependabotConfig:
    """``_check_dependabot_config`` reads ``.github/dependabot.yml``."""

    def test_missing_file_returns_false(self, tmp_path: Path) -> None:
        result = _check_dependabot_config(tmp_path)

        assert result["ok"] is False
        assert result["value"] == "not present"
        assert result["severity"] == "warning"

    def test_invalid_yaml_returns_false(self, tmp_path: Path) -> None:
        _write_dependabot(tmp_path, "updates: [unterminated")

        result = _check_dependabot_config(tmp_path)

        assert result["ok"] is False
        assert "invalid YAML" in result["value"]

    def test_no_updates_key_returns_false(self, tmp_path: Path) -> None:
        _write_dependabot(tmp_path, "version: 2\n")

        result = _check_dependabot_config(tmp_path)

        assert result["ok"] is False
        assert result["value"] == "no ecosystems configured"

    def test_empty_updates_list_returns_false(self, tmp_path: Path) -> None:
        _write_dependabot(tmp_path, "version: 2\nupdates: []\n")

        result = _check_dependabot_config(tmp_path)

        assert result["ok"] is False
        assert result["value"] == "no ecosystems configured"

    def test_single_ecosystem(self, tmp_path: Path) -> None:
        _write_dependabot(
            tmp_path,
            "version: 2\n"
            "updates:\n"
            '  - package-ecosystem: "pip"\n'
            '    directory: "/"\n'
            "    schedule:\n"
            '      interval: "weekly"\n',
        )

        result = _check_dependabot_config(tmp_path)

        assert result["ok"] is True
        assert "pip: weekly" in result["value"]

    def test_multi_ecosystem_uniform_schedule(self, tmp_path: Path) -> None:
        _write_dependabot(
            tmp_path,
            "version: 2\n"
            "updates:\n"
            '  - package-ecosystem: "pip"\n'
            '    directory: "/"\n'
            "    schedule:\n"
            '      interval: "weekly"\n'
            '  - package-ecosystem: "npm"\n'
            '    directory: "/"\n'
            "    schedule:\n"
            '      interval: "weekly"\n',
        )

        result = _check_dependabot_config(tmp_path)

        assert result["ok"] is True
        assert "pip, npm: weekly" in result["value"]

    def test_multi_ecosystem_mixed_schedule(self, tmp_path: Path) -> None:
        _write_dependabot(
            tmp_path,
            "version: 2\n"
            "updates:\n"
            '  - package-ecosystem: "pip"\n'
            '    directory: "/"\n'
            "    schedule:\n"
            '      interval: "weekly"\n'
            '  - package-ecosystem: "npm"\n'
            '    directory: "/"\n'
            "    schedule:\n"
            '      interval: "daily"\n',
        )

        result = _check_dependabot_config(tmp_path)

        assert result["ok"] is True
        assert "pip: weekly, npm: daily" in result["value"]

    def test_unreadable_file_returns_false(self, tmp_path: Path) -> None:
        github_dir = tmp_path / ".github"
        github_dir.mkdir()
        (github_dir / "dependabot.yml").write_bytes(b"\xff\xfe\x00bad\x80")

        result = _check_dependabot_config(tmp_path)

        assert result["ok"] is False
        assert result["value"] == "unreadable"

    def test_yaml_extension_accepted(self, tmp_path: Path) -> None:
        github_dir = tmp_path / ".github"
        github_dir.mkdir()
        (github_dir / "dependabot.yaml").write_text(
            "version: 2\nupdates:\n"
            '  - package-ecosystem: "pip"\n'
            "    schedule:\n"
            '      interval: "weekly"\n',
            encoding="utf-8",
        )

        result = _check_dependabot_config(tmp_path)

        assert result["ok"] is True
        assert ".github/dependabot.yaml (pip: weekly)" in result["value"]

    def test_yml_preferred_over_yaml(self, tmp_path: Path) -> None:
        _write_dependabot(
            tmp_path,
            "version: 2\nupdates:\n"
            '  - package-ecosystem: "pip"\n'
            "    schedule:\n"
            '      interval: "weekly"\n',
        )
        (tmp_path / ".github" / "dependabot.yaml").write_text(
            "version: 2\n", encoding="utf-8"
        )

        result = _check_dependabot_config(tmp_path)

        assert result["ok"] is True
        assert "dependabot.yml (pip" in result["value"]

    def test_updates_without_valid_entries_returns_false(self, tmp_path: Path) -> None:
        _write_dependabot(tmp_path, "version: 2\nupdates:\n  - foo\n  - 42\n")

        result = _check_dependabot_config(tmp_path)

        assert result["ok"] is False
        assert result["value"] == "no ecosystems configured"

    def test_null_schedule_does_not_crash(self, tmp_path: Path) -> None:
        _write_dependabot(
            tmp_path,
            "version: 2\n"
            "updates:\n"
            '  - package-ecosystem: "pip"\n'
            '    directory: "/"\n'
            "    schedule:\n",
        )

        result = _check_dependabot_config(tmp_path)

        assert result["ok"] is True
        assert "pip: ?" in result["value"]


def _write_workflow(project_dir: Path, filename: str, content: str) -> None:
    workflows_dir = project_dir / ".github" / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)
    (workflows_dir / filename).write_text(content, encoding="utf-8")


class TestCheckCodeqlWorkflow:
    """``_check_codeql_workflow`` scans workflow files for a CodeQL step."""

    def test_no_workflows_dir_returns_false(self, tmp_path: Path) -> None:
        result = _check_codeql_workflow(tmp_path)

        assert result["ok"] is False
        assert result["value"] == "no workflow step uses github/codeql-action"
        assert result["severity"] == "warning"

    def test_workflow_with_unrelated_content_returns_false(
        self, tmp_path: Path
    ) -> None:
        _write_workflow(
            tmp_path,
            "ci.yml",
            "name: CI\non: push\njobs:\n  build:\n    steps:\n      - uses: actions/checkout@v4\n",
        )

        result = _check_codeql_workflow(tmp_path)

        assert result["ok"] is False
        assert result["value"] == "no workflow step uses github/codeql-action"

    def test_codeql_step_in_non_obvious_filename(self, tmp_path: Path) -> None:
        _write_workflow(
            tmp_path,
            "build.yml",
            "name: Build\non: push\njobs:\n  build:\n    steps:\n      - uses: github/codeql-action/analyze@v3\n",
        )

        result = _check_codeql_workflow(tmp_path)

        assert result["ok"] is True
        assert result["value"] == "found in build.yml"

    def test_quoted_uses_value(self, tmp_path: Path) -> None:
        _write_workflow(
            tmp_path,
            "build.yml",
            'name: Build\non: push\njobs:\n  build:\n    steps:\n      - uses: "github/codeql-action/analyze@v3"\n',
        )

        result = _check_codeql_workflow(tmp_path)

        assert result["ok"] is True
        assert result["value"] == "found in build.yml"

    def test_commented_out_uses_not_detected(self, tmp_path: Path) -> None:
        _write_workflow(
            tmp_path,
            "build.yml",
            "name: Build\non: push\njobs:\n  build:\n    steps:\n"
            "      # - uses: github/codeql-action/analyze@v3\n"
            "      - uses: actions/checkout@v4\n",
        )

        result = _check_codeql_workflow(tmp_path)

        assert result["ok"] is False

    def test_uses_text_inside_run_not_detected(self, tmp_path: Path) -> None:
        _write_workflow(
            tmp_path,
            "build.yml",
            "name: Build\non: push\njobs:\n  build:\n    steps:\n"
            "      - run: |\n"
            "          echo uses: github/codeql-action/analyze@v3\n",
        )

        result = _check_codeql_workflow(tmp_path)

        assert result["ok"] is False

    def test_invalid_yaml_workflow_skipped(self, tmp_path: Path) -> None:
        _write_workflow(tmp_path, "a.yml", "jobs: [unterminated")
        _write_workflow(tmp_path, "b.yml", "- just\n- a list\n")
        _write_workflow(tmp_path, "c.yml", "jobs:\n  x: null\n  y:\n    steps: 3\n")

        result = _check_codeql_workflow(tmp_path)

        assert result["ok"] is False

    def test_non_utf8_file_skipped_and_others_scanned(self, tmp_path: Path) -> None:
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)
        (workflows_dir / "a.yml").write_bytes(b"\xff\xfe\x00bad\x80")
        _write_workflow(
            tmp_path,
            "b.yml",
            "jobs:\n  build:\n    steps:\n      - uses: github/codeql-action/analyze@v3\n",
        )

        result = _check_codeql_workflow(tmp_path)

        assert result["ok"] is True
        assert result["value"] == "found in b.yml"


def _check(ok: bool | None, value: str, error: str | None = None) -> CheckResult:
    result = CheckResult(ok=ok, value=value, severity="warning")
    if error is not None:
        result["error"] = error
    return result


class TestMapSecurityRow:
    """``_map_security_row`` passes probe rows through, applying three rules."""

    @pytest.mark.parametrize(
        ("key", "row", "expected_ok", "expected_value"),
        [
            pytest.param(
                "code_scanning_alerts",
                _check(True, "scope present"),
                True,
                "scope present",
                id="code-scanning-200",
            ),
            pytest.param(
                "code_scanning_alerts",
                _check(False, "scope missing or Advanced Security not enabled"),
                False,
                "scope missing or Advanced Security not enabled",
                id="code-scanning-403",
            ),
            pytest.param(
                "code_scanning_alerts",
                _check(False, "scope missing or not configured"),
                None,
                "scope missing or not configured",
                id="code-scanning-404",
            ),
            pytest.param(
                "secret_scanning",
                _check(False, "scope missing or not configured"),
                False,
                "scope missing or not configured",
                id="404-demotion-is-code-scanning-only",
            ),
            pytest.param(
                "code_scanning_alerts",
                _check(None, "not accessible", error="network error: boom"),
                None,
                "not accessible (network error: boom)",
                id="code-scanning-error",
            ),
            pytest.param(
                "dependabot_alerts",
                _check(None, "not checked", error="repository not accessible"),
                None,
                "not accessible (repository not accessible)",
                id="repo-unresolvable",
            ),
            pytest.param(
                "code_scanning_alerts",
                _check(False, "something reworded"),
                False,
                "something reworded",
                id="code-scanning-unrecognised",
            ),
        ],
    )
    def test_mapping(
        self,
        key: str,
        row: CheckResult,
        expected_ok: bool | None,
        expected_value: str,
    ) -> None:
        result = _map_security_row(key, row)

        assert result["ok"] is expected_ok
        assert result["value"] == expected_value
        assert result["severity"] == "warning"

    def test_input_row_not_mutated(self) -> None:
        row = _check(None, "not checked", error="repository not accessible")

        _map_security_row("dependabot_alerts", row)

        assert row["value"] == "not checked"


class TestGithubSecurityRows:
    """``github_security_rows`` assembles local and API rows in display order."""

    def test_key_order(self, tmp_path: Path) -> None:
        api = {
            key: _check(True, "enabled")
            for key in (
                "dependabot_alerts",
                "dependabot_security_updates",
                "secret_scanning",
                "secret_scanning_push_protection",
                "code_scanning_alerts",
            )
        }
        with patch(f"{_SECURITY_ROWS}.verify_github_security", return_value=api):
            result = github_security_rows(tmp_path)

        assert list(result) == [
            "dependabot_config",
            "dependabot_alerts",
            "dependabot_security_updates",
            "secret_scanning",
            "secret_scanning_push_protection",
            "codeql_workflow",
            "code_scanning_alerts",
        ]
        assert all(row["severity"] == "warning" for row in result.values())


def _render(project_dir: Path, repo: MagicMock | None) -> str:
    """Render GITHUB SECURITY through the real probe; return the text."""
    with patch(f"{_PROBES}.BaseGitHubManager") as mock_cls:
        if repo is None:
            mock_cls.side_effect = ValueError("no token")
        else:
            mock_cls.return_value._get_repository.return_value = repo
        rows = github_security_rows(project_dir)
    return "\n".join(render_rows(format_github_security_section(rows, STATUS_SYMBOLS)))


def _line(output: str, label: str) -> str:
    """Return the single output line whose label column is ``label``."""
    rows = [
        line for line in output.splitlines() if line.lstrip().startswith(f"{label} ")
    ]
    assert len(rows) == 1, f"expected one {label!r} row, got {rows}"
    return rows[0]


def _make_repo(code_scanning_effect: BaseException | None) -> MagicMock:
    repo = MagicMock()
    repo.url = "https://api.github.com/repos/o/r"
    repo.requester.requestJson.return_value = (204, {}, None)
    repo.security_and_analysis = None
    repo.requester.requestJsonAndCheck.side_effect = code_scanning_effect
    return repo


class TestRealProbeCodeScanning:
    """The code-scanning row for each probe outcome."""

    @pytest.mark.parametrize(
        ("side_effect", "marker", "value"),
        [
            pytest.param(None, "[OK]", "scope present", id="200"),
            pytest.param(
                GithubException(403, {"message": "x"}, None),
                "[ERR]",
                "scope missing or Advanced Security not enabled",
                id="403",
            ),
            pytest.param(
                GithubException(404, {"message": "x"}, None),
                "[WARN]",
                "scope missing or not configured",
                id="404",
            ),
            pytest.param(
                ConnectionError("boom"),
                "[WARN]",
                "not accessible (network error: boom)",
                id="error",
            ),
        ],
    )
    def test_code_scanning_row(
        self,
        side_effect: BaseException | None,
        marker: str,
        value: str,
        tmp_path: Path,
    ) -> None:
        """The probe's result maps to the expected marker and value."""
        output = _render(tmp_path, _make_repo(side_effect))

        line = _line(output, "Code scanning alerts")
        assert marker in line
        assert value in line


class TestRealProbeRepoUnresolvable:
    """All API-backed rows when the repository cannot be resolved."""

    def test_all_api_rows_not_accessible(self, tmp_path: Path) -> None:
        """Each of the five API-backed rows renders as not accessible."""
        output = _render(tmp_path, None)

        for label in (
            "Dependabot alerts",
            "Dependabot security",
            "Secret scanning",
            "Secret push protection",
            "Code scanning alerts",
        ):
            line = _line(output, label)
            assert "[WARN]" in line
            assert "not accessible (repository not accessible)" in line
