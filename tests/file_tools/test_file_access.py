"""Tests for effective file access: gitignore default plus .mcp-file-access rules."""

import os
import sys
from pathlib import Path

import pytest

from mcp_workspace.file_tools.access_rules import ACCESS_RULES_FILE, load_access_rules
from mcp_workspace.file_tools.directory_utils import (
    FileAccess,
    _access,
    get_file_access,
    is_path_gitignored,
    require_access,
)

INVALID_REASON = ".mcp-file-access is invalid: line 1: unknown level 'readonly'"


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
        path.write_text("x", encoding="utf-8")
    return root


def _reason(path: str, project_dir: Path) -> str:
    """Return the reason _access gives for a path."""
    return _access(path, project_dir, load_access_rules(project_dir))[1]


class TestDefault:
    """Without matching rules, access follows .gitignore."""

    def test_committed_is_read_write_and_ignored_is_hidden(
        self, tmp_path: Path
    ) -> None:
        project = _project(tmp_path, "*.log\n", "", ("a.txt", "b.log"))

        assert get_file_access("a.txt", project) is FileAccess.READ_WRITE
        assert get_file_access("b.log", project) is FileAccess.HIDDEN
        assert _reason("a.txt", project) == ""

    @pytest.mark.parametrize(
        "path", ["a.txt", "b.log", "secret/key.txt", "new.log", "src/x.py", ".env"]
    )
    def test_no_rules_file_matches_is_path_gitignored(
        self, tmp_path: Path, path: str
    ) -> None:
        project = _project(
            tmp_path,
            "*.log\nsecret/\n.env\n",
            None,
            ("a.txt", "b.log", "secret/key.txt"),
        )

        expected = (
            FileAccess.HIDDEN
            if is_path_gitignored(path, project)
            else FileAccess.READ_WRITE
        )
        assert get_file_access(path, project) is expected

    def test_access_levels_are_ordered(self) -> None:
        assert FileAccess.HIDDEN < FileAccess.READ_ONLY < FileAccess.READ_WRITE


class TestRules:
    """Rules override the gitignore default."""

    def test_read_only_on_committed_and_ignored(self, tmp_path: Path) -> None:
        project = _project(
            tmp_path,
            "uv.lock\n",
            "read-only /pyproject.toml\nread-only /uv.lock\n",
            ("pyproject.toml", "uv.lock"),
        )

        assert get_file_access("pyproject.toml", project) is FileAccess.READ_ONLY
        assert get_file_access("uv.lock", project) is FileAccess.READ_ONLY
        assert _reason("uv.lock", project) == "rule '/uv.lock' in .mcp-file-access"

    def test_read_write_on_ignored(self, tmp_path: Path) -> None:
        project = _project(tmp_path, "*.tmp\n", "read-write /notes.tmp\n")

        assert get_file_access("notes.tmp", project) is FileAccess.READ_WRITE
        assert get_file_access("other.tmp", project) is FileAccess.HIDDEN

    def test_last_match_wins_both_ways(self, tmp_path: Path) -> None:
        project = _project(
            tmp_path,
            "",
            "read-only config/\nread-write config/local.json\n",
            ("config/local.json", "config/base.json"),
        )

        assert get_file_access("config/local.json", project) is FileAccess.READ_WRITE
        assert get_file_access("config/base.json", project) is FileAccess.READ_ONLY

    def test_directory_path_matches_directory_rule(self, tmp_path: Path) -> None:
        project = _project(tmp_path, ".scratch/\n", "read-write /.scratch/\n")
        (project / ".scratch").mkdir()

        assert get_file_access(".scratch", project) is FileAccess.READ_WRITE
        assert get_file_access(".scratch/probe.py", project) is FileAccess.READ_WRITE

    def test_directory_rule_exposes_ignored_file_below(self, tmp_path: Path) -> None:
        project = _project(
            tmp_path, ".env\n", "read-only /config/\n", ("config/.env", ".env")
        )

        assert get_file_access("config/.env", project) is FileAccess.READ_ONLY
        assert get_file_access(".env", project) is FileAccess.HIDDEN

    def test_unanchored_rule_inside_ignored_directory(self, tmp_path: Path) -> None:
        project = _project(
            tmp_path, "logs/\n", "read-only *.log\n", ("logs/a.log", "logs/b.txt")
        )

        assert get_file_access("logs/a.log", project) is FileAccess.READ_ONLY
        assert get_file_access("logs/b.txt", project) is FileAccess.HIDDEN


class TestBuiltIn:
    """Built-in rules that no rules file can override."""

    @pytest.mark.parametrize(
        "rules", [None, "", "read-write /.mcp-file-access\n", "read-write *\n"]
    )
    def test_rules_file_is_read_only(self, tmp_path: Path, rules: str | None) -> None:
        project = _project(tmp_path, "", rules)

        assert get_file_access(ACCESS_RULES_FILE, project) is FileAccess.READ_ONLY
        assert _reason(ACCESS_RULES_FILE, project) == "built-in"

    @pytest.mark.parametrize("path", [".mcp-file-access.", ".mcp-file-access::$DATA"])
    def test_rules_file_spellings_are_read_only(
        self, tmp_path: Path, path: str
    ) -> None:
        project = _project(tmp_path, "", "")

        assert get_file_access(path, project) is FileAccess.READ_ONLY

    def test_rules_file_below_root_is_not_built_in(self, tmp_path: Path) -> None:
        project = _project(tmp_path, "", "")

        assert get_file_access("sub/.mcp-file-access", project) is (
            FileAccess.READ_WRITE
        )

    @pytest.mark.parametrize("path", [".git/config", ".git", "sub/.git/HEAD"])
    def test_git_dir_stays_hidden(self, tmp_path: Path, path: str) -> None:
        project = _project(tmp_path, "", "read-write /.git/\nread-write **/.git/\n")
        (project / ".git").mkdir()

        assert get_file_access(path, project) is FileAccess.HIDDEN


class TestSpellings:
    """Every spelling of a path gets the most restrictive access."""

    @pytest.mark.parametrize("path", [".mcp.json.", ".mcp.json::$DATA"])
    def test_protected_spellings(self, tmp_path: Path, path: str) -> None:
        project = _project(tmp_path, "", "read-only /.mcp.json\n", (".mcp.json",))

        assert get_file_access(path, project) is FileAccess.READ_ONLY

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows name matching")
    def test_case_variant_on_windows(self, tmp_path: Path) -> None:
        project = _project(tmp_path, "", "read-only /.mcp.json\n", (".mcp.json",))

        assert get_file_access(".MCP.json", project) is FileAccess.READ_ONLY

    def test_symlink_to_read_only_file(self, tmp_path: Path) -> None:
        project = _project(tmp_path, "", "read-only /.mcp.json\n", (".mcp.json",))
        try:
            os.symlink(project / ".mcp.json", project / "link.json")
        except OSError as exc:
            pytest.skip(f"symlinks unavailable: {exc}")

        assert get_file_access("link.json", project) is FileAccess.READ_ONLY


class TestInvalidRulesFile:
    """An invalid rules file fails safe."""

    def test_committed_path_is_read_only_with_reason(self, tmp_path: Path) -> None:
        project = _project(tmp_path, "", "readonly /a.txt\n", ("a.txt",))

        assert get_file_access("a.txt", project) is FileAccess.READ_ONLY
        assert _reason("a.txt", project) == INVALID_REASON

    def test_ignored_path_stays_hidden(self, tmp_path: Path) -> None:
        project = _project(
            tmp_path, "*.lock\n", "read-only /uv.lock\nreadonly /x\n", ("uv.lock",)
        )

        assert get_file_access("uv.lock", project) is FileAccess.HIDDEN


class TestRequireAccess:
    """require_access raises the refusal messages."""

    def test_hidden_raises_gitignore_message(self, tmp_path: Path) -> None:
        project = _project(tmp_path, "*.log\n", "", ("b.log",))

        with pytest.raises(ValueError, match="excluded by .gitignore rules"):
            require_access("b.log", project, FileAccess.READ_ONLY)

    def test_read_only_refuses_write(self, tmp_path: Path) -> None:
        project = _project(tmp_path, "", "read-only /.mcp.json\n", (".mcp.json",))

        with pytest.raises(ValueError) as excinfo:
            require_access(".mcp.json", project, FileAccess.READ_WRITE)
        assert str(excinfo.value) == (
            "No write access to '.mcp.json' (rule '/.mcp.json' in .mcp-file-access)"
        )

    def test_read_only_allows_read(self, tmp_path: Path) -> None:
        project = _project(tmp_path, "", "read-only /.mcp.json\n", (".mcp.json",))

        require_access(".mcp.json", project, FileAccess.READ_ONLY)

    def test_read_write_allows_write(self, tmp_path: Path) -> None:
        project = _project(tmp_path, "", "", ("a.txt",))

        require_access("a.txt", project, FileAccess.READ_WRITE)

    def test_absolute_path_inside_project_is_checked(self, tmp_path: Path) -> None:
        project = _project(tmp_path, "", "read-only /.mcp.json\n", (".mcp.json",))

        with pytest.raises(ValueError, match="No write access to '.mcp.json'"):
            require_access(str(project / ".mcp.json"), project, FileAccess.READ_WRITE)

    def test_absolute_path_outside_project_is_left_alone(self, tmp_path: Path) -> None:
        (tmp_path / "p").mkdir()
        project = _project(tmp_path / "p", "*.txt\n")
        outside = tmp_path / "outside.txt"

        require_access(str(outside), project, FileAccess.READ_WRITE)

    def test_invalid_rules_file_refuses_write_with_reason(self, tmp_path: Path) -> None:
        project = _project(tmp_path, "", "readonly /a.txt\n", ("a.txt",))

        with pytest.raises(ValueError) as excinfo:
            require_access("a.txt", project, FileAccess.READ_WRITE)
        assert str(excinfo.value) == f"No write access to 'a.txt' ({INVALID_REASON})"


@pytest.mark.parametrize(
    "module", ["mcp_workspace.file_tools.directory_utils", "mcp_workspace.file_tools"]
)
def test_public_api_importable(module: str) -> None:
    imported = __import__(module, fromlist=["validate_access_rules"])

    assert callable(imported.validate_access_rules)
    assert callable(imported.get_file_access)
    assert imported.FileAccess.READ_ONLY == 1
