"""Tests for the search_files warning while .mcp-file-access is invalid."""

from pathlib import Path
from typing import Any

import pytest

from mcp_workspace.file_tools.access_rules import (
    ACCESS_RULES_FILE,
    access_rules_warning,
    load_access_rules,
)
from mcp_workspace.file_tools.search import search_files


def _rules_project(root: Path, rules: str | None) -> Path:
    """Build a project with one text file and an optional rules file."""
    (root / ".gitignore").write_text("", encoding="utf-8")
    (root / "a.txt").write_text("MARKER\n", encoding="utf-8")
    if rules is not None:
        (root / ACCESS_RULES_FILE).write_text(rules, encoding="utf-8")
    return root


def _search_in_mode(project: Path, mode: str) -> dict[str, Any]:
    """Run a file-mode or content-mode search over the rules project."""
    if mode == "file":
        return search_files(project, glob="*.txt")
    return search_files(project, pattern="MARKER")


class TestSearchFilesWarning:
    """A "warning" key appears only while .mcp-file-access is invalid."""

    @pytest.mark.parametrize("mode", ["file", "content"])
    def test_invalid_rules_file_adds_warning(self, tmp_path: Path, mode: str) -> None:
        project = _rules_project(tmp_path, "readonly /logs/\n")

        result = _search_in_mode(project, mode)

        expected = access_rules_warning(load_access_rules(project).problems)
        assert expected is not None
        assert result["warning"] == expected

    @pytest.mark.parametrize(
        "rules", ["read-only /logs/\n", None], ids=["valid", "absent"]
    )
    @pytest.mark.parametrize("mode", ["file", "content"])
    def test_valid_or_absent_rules_file_has_no_warning(
        self, tmp_path: Path, rules: str | None, mode: str
    ) -> None:
        project = _rules_project(tmp_path, rules)

        result = _search_in_mode(project, mode)

        assert "warning" not in result
