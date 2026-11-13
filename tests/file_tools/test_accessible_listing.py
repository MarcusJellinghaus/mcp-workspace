"""Tests for the exposure-aware listing walk and its users."""

import os
from collections.abc import Callable
from pathlib import Path

import pytest

from mcp_workspace.checks.file_sizes import check_file_sizes
from mcp_workspace.file_tools.access_rules import ACCESS_RULES_FILE
from mcp_workspace.file_tools.directory_utils import (
    FileAccess,
    get_file_access,
    list_accessible_files,
    list_files,
)
from mcp_workspace.file_tools.search import search_files
from mcp_workspace.reference_projects import ReferenceProject
from tests.conftest import ToolMap

READ_ONLY_NOTE = "(read-only)"
NOT_COMMITTED_NOTE = "(read-write, not committed)"


def _project(
    root: Path,
    gitignore: str = "",
    rules: str | None = None,
    files: tuple[str, ...] = (),
) -> Path:
    """Build a project with a .gitignore, an optional rules file and files."""
    (root / ".gitignore").write_text(gitignore, encoding="utf-8")
    if rules is not None:
        (root / ACCESS_RULES_FILE).write_text(rules, encoding="utf-8")
    for rel in files:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"MARKER in {rel}\n", encoding="utf-8")
    return root


def _logs_project(root: Path, rules: str) -> Path:
    """Build a project ignoring *.log and logs/, with nested log files."""
    return _project(
        root,
        "*.log\nlogs/\n",
        rules,
        ("plain.txt", "x.log", "logs/a.log", "logs/sub/b.log"),
    )


class TestListAccessibleFiles:
    """The walk lists what gitignore lists, plus the paths rules expose."""

    def test_no_rules_file_matches_list_files(self, tmp_path: Path) -> None:
        project = _project(
            tmp_path,
            "*.log\nsecret/\n.env\n",
            None,
            ("a.txt", "b.log", "secret/key.txt", "src/x.py", ".env"),
        )

        listing = list_accessible_files(".", project)

        assert listing.files == list_files(".", project)
        assert listing.notes == {}
        assert listing.problems == []

    def test_logs_directory_rule(self, tmp_path: Path) -> None:
        project = _logs_project(tmp_path, "read-only /logs/\n")

        listing = list_accessible_files(".", project)

        assert "logs/a.log" in listing.files
        assert "logs/sub/b.log" in listing.files
        assert "x.log" not in listing.files
        assert listing.notes["logs/a.log"] == READ_ONLY_NOTE
        assert listing.notes["logs/sub/b.log"] == READ_ONLY_NOTE
        assert "plain.txt" not in listing.notes

    def test_logs_are_searched(self, tmp_path: Path) -> None:
        project = _logs_project(tmp_path, "read-only /logs/\n")

        result = search_files(project, pattern="MARKER")

        found = {match["file"] for match in result["details"]}
        assert {"logs/a.log", "logs/sub/b.log", "plain.txt"} <= found
        assert "x.log" not in found

    def test_unanchored_rule_does_not_enter_ignored_directory(
        self, tmp_path: Path
    ) -> None:
        project = _logs_project(tmp_path, "read-only *.log\n")

        listing = list_accessible_files(".", project)
        result = search_files(project, pattern="MARKER")

        assert "logs/a.log" not in listing.files
        assert "logs/sub/b.log" not in listing.files
        assert "x.log" in listing.files
        assert listing.notes["x.log"] == READ_ONLY_NOTE
        found = {match["file"] for match in result["details"]}
        assert "logs/a.log" not in found
        assert get_file_access("logs/a.log", project) is FileAccess.READ_ONLY

    def test_anchored_prefix_leads_into_ignored_directory(self, tmp_path: Path) -> None:
        project = _logs_project(tmp_path, "read-only /logs/sub/*.log\n")

        listing = list_accessible_files(".", project)

        assert "logs/sub/b.log" in listing.files
        assert "logs/a.log" not in listing.files

    def test_directory_rule_exposes_other_ignored_files(self, tmp_path: Path) -> None:
        project = _project(
            tmp_path,
            ".scratch/\n__pycache__/\n.env\n",
            "read-write /.scratch/\n",
            (".scratch/probe.py", ".scratch/__pycache__/m.pyc", ".scratch/.env"),
        )

        listing = list_accessible_files(".", project)

        for rel in (".scratch/probe.py", ".scratch/__pycache__/m.pyc", ".scratch/.env"):
            assert rel in listing.files
            assert listing.notes[rel] == NOT_COMMITTED_NOTE

    def test_rules_on_committed_files(self, tmp_path: Path) -> None:
        project = _project(
            tmp_path,
            "",
            "read-only /plain.txt\nread-write /other.txt\n",
            ("plain.txt", "other.txt"),
        )

        listing = list_accessible_files(".", project)

        assert listing.notes["plain.txt"] == READ_ONLY_NOTE
        assert "other.txt" in listing.files
        assert "other.txt" not in listing.notes

    def test_root_rules_file_is_read_only(self, tmp_path: Path) -> None:
        project = _project(tmp_path, "", "read-write /.scratch/\n", ("a.txt",))

        listing = list_accessible_files(".", project)

        assert listing.notes[ACCESS_RULES_FILE] == READ_ONLY_NOTE
        assert "a.txt" not in listing.notes

    def test_ignored_rules_file_without_rule_stays_hidden(self, tmp_path: Path) -> None:
        project = _project(tmp_path, f"{ACCESS_RULES_FILE}\n", "", ("a.txt",))

        listing = list_accessible_files(".", project)

        assert ACCESS_RULES_FILE not in listing.files

    def test_invalid_rules_file(self, tmp_path: Path) -> None:
        project = _logs_project(tmp_path, "readonly /logs/\n")

        listing = list_accessible_files(".", project)

        assert listing.files == list_files(".", project)
        assert "logs/a.log" not in listing.files
        assert listing.notes == {}
        assert listing.problems == ["line 1: unknown level 'readonly'"]

    def test_link_to_hidden_file_in_exposed_directory(self, tmp_path: Path) -> None:
        project = _project(
            tmp_path,
            ".scratch/\n.env\n",
            "read-write /.scratch/\n",
            (".scratch/probe.py", ".env"),
        )
        try:
            os.symlink(project / ".env", project / ".scratch" / "link")
        except OSError as exc:
            pytest.skip(f"symlinks unavailable: {exc}")

        listing = list_accessible_files(".", project)

        assert ".scratch/probe.py" in listing.files
        assert ".scratch/link" not in listing.files

    def test_list_exposed_subdirectory(self, tmp_path: Path) -> None:
        project = _logs_project(tmp_path, "read-only /logs/\n")

        listing = list_accessible_files("logs", project)

        assert listing.files == ["logs/a.log", "logs/sub/b.log"]
        assert listing.notes == {
            "logs/a.log": READ_ONLY_NOTE,
            "logs/sub/b.log": READ_ONLY_NOTE,
        }

    def test_list_directory_reached_by_anchored_prefix(self, tmp_path: Path) -> None:
        project = _logs_project(tmp_path, "read-only /logs/sub/*.log\n")

        assert list_accessible_files("logs", project).files == ["logs/sub/b.log"]

    @pytest.mark.parametrize("directory", ["secret", "secret/sub", "missing_secret"])
    def test_hidden_directory_refused(self, tmp_path: Path, directory: str) -> None:
        project = _project(
            tmp_path,
            "secret/\nmissing_secret\n",
            "read-only /logs/\n",
            ("secret/sub/key.txt",),
        )

        # A missing hidden directory gets the same refusal, not "does not exist"
        with pytest.raises(ValueError, match="excluded by .gitignore"):
            list_accessible_files(directory, project)

    def test_missing_and_file_paths(self, tmp_path: Path) -> None:
        project = _project(tmp_path, "", None, ("a.txt",))

        with pytest.raises(FileNotFoundError):
            list_accessible_files("nope", project)
        with pytest.raises(NotADirectoryError):
            list_accessible_files("a.txt", project)

    def test_file_size_check_excludes_exposed_files(self, tmp_path: Path) -> None:
        project = _logs_project(tmp_path, "read-only /logs/\n")

        result = check_file_sizes(project, max_lines=0, allowlist=set())

        checked = {violation.path for violation in result.violations}
        assert "plain.txt" in checked
        assert "logs/a.log" not in checked


@pytest.fixture
def reference(tmp_path: Path) -> Path:
    """Reference project exposing its ignored logs/ directory read-only."""
    ref = tmp_path / "ref"
    ref.mkdir()
    return _logs_project(ref, "read-only /logs/\n")


@pytest.fixture
def ref_tools(reference: Path, make_tools: Callable[..., ToolMap]) -> ToolMap:
    """Tools whose reference project "ref" is the reference fixture."""
    return make_tools(
        reference_projects={"ref": ReferenceProject(name="ref", path=reference)}
    )


class TestReferenceListing:
    """Reference tools apply the reference project's own rules file."""

    @pytest.mark.asyncio
    async def test_list_reference_directory_includes_exposed(
        self, ref_tools: ToolMap
    ) -> None:
        result = await ref_tools["list_reference_directory"]("ref")

        assert "logs/a.log" in result
        assert "logs/sub/b.log" in result
        assert "x.log" not in result
        assert not any("(read-only)" in entry for entry in result)

    @pytest.mark.asyncio
    async def test_search_reference_files_includes_exposed(
        self, ref_tools: ToolMap
    ) -> None:
        result = await ref_tools["search_reference_files"]("ref", glob="**/*.log")

        assert result["files"] == ["logs/a.log", "logs/sub/b.log"]

    @pytest.mark.asyncio
    async def test_invalid_rules_file_warning(
        self, reference: Path, ref_tools: ToolMap
    ) -> None:
        (reference / ACCESS_RULES_FILE).write_text("readonly /logs/\n", "utf-8")

        result = await ref_tools["list_reference_directory"]("ref")

        assert result[0] == (
            "WARNING: .mcp-file-access is invalid (line 1: unknown level "
            "'readonly') - writes are refused and no gitignored path is exposed."
        )
        assert "logs/a.log" not in result
        assert "plain.txt" in result[1:]
