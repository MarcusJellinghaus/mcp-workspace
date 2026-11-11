"""Tests for ``body_file`` on github_issue_view and its write helpers."""

import sys
from pathlib import Path

import pytest

from mcp_workspace.toolset._context import WorkspaceContext
from mcp_workspace.toolset._github_write_helpers import check_body_target, save_body


@pytest.fixture
def ctx(project_dir: Path) -> WorkspaceContext:
    """Context rooted at the isolated project directory."""
    return WorkspaceContext(project_dir, {}, None, None, False, True)


def _files(project_dir: Path) -> set[Path]:
    """Return every path below the project directory."""
    return set(project_dir.rglob("*"))


class TestCheckBodyTarget:
    """Test the check_body_target helper."""

    def test_new_nested_path_accepted(
        self, ctx: WorkspaceContext, project_dir: Path
    ) -> None:
        """A path that doesn't exist yet returns its forward-slash relative path."""
        before = _files(project_dir)

        abs_path, display = check_body_target(ctx, ".scratch/new/issue.md")

        assert abs_path == project_dir / ".scratch" / "new" / "issue.md"
        assert display == ".scratch/new/issue.md"
        assert _files(project_dir) == before

    @pytest.mark.parametrize(
        "body_file",
        [
            "../outside.md",
            pytest.param(
                "..\\x.md",
                marks=pytest.mark.skipif(
                    sys.platform != "win32", reason="backslash is a separator"
                ),
            ),
        ],
    )
    def test_outside_rejected(
        self, ctx: WorkspaceContext, project_dir: Path, body_file: str
    ) -> None:
        """A path leaving the project is rejected without writing."""
        before = _files(project_dir)

        with pytest.raises(ValueError):
            check_body_target(ctx, body_file)

        assert _files(project_dir) == before
        assert not (project_dir.parent / "outside.md").exists()
        assert not (project_dir.parent / "x.md").exists()

    def test_gitignored_rejected(
        self, ctx: WorkspaceContext, project_dir: Path
    ) -> None:
        """A gitignored path is rejected without writing."""
        (project_dir / ".gitignore").write_bytes(b"*.log\n")
        before = _files(project_dir)

        with pytest.raises(ValueError):
            check_body_target(ctx, "issue.log")

        assert _files(project_dir) == before

    def test_directory_rejected(self, ctx: WorkspaceContext, project_dir: Path) -> None:
        """An existing directory is rejected without writing."""
        (project_dir / "subdir").mkdir()
        before = _files(project_dir)

        with pytest.raises(ValueError, match="is a directory"):
            check_body_target(ctx, "subdir")

        assert _files(project_dir) == before


class TestSaveBody:
    """Test the save_body helper."""

    def test_crlf_non_ascii_verbatim(self, project_dir: Path) -> None:
        """A CRLF non-ASCII body is written as UTF-8 without BOM, CRLF kept."""
        body = "äöü → ✓\r\nzweite Zeile\r\n"
        target = project_dir / "issue.md"

        save_body(target, "issue.md", body)

        assert target.read_bytes() == body.encode("utf-8")

    @pytest.mark.parametrize(
        "body", ["a\r\nb\nc\rd\r\n", "a\rb\rc\r"], ids=["mixed", "cr"]
    )
    def test_mixed_and_cr_verbatim(self, project_dir: Path, body: str) -> None:
        """Mixed and CR bodies are kept byte for byte."""
        target = project_dir / "issue.md"

        save_body(target, "issue.md", body)

        assert target.read_bytes() == body.encode("utf-8")

    def test_creates_missing_parents(self, project_dir: Path) -> None:
        """Missing parent directories are created."""
        target = project_dir / ".scratch" / "new" / "issue.md"

        save_body(target, ".scratch/new/issue.md", "x\n")

        assert target.read_bytes() == b"x\n"

    def test_overwrites_existing(self, project_dir: Path) -> None:
        """An existing file is overwritten."""
        target = project_dir / "issue.md"
        target.write_bytes(b"old content that is longer\r\n")

        save_body(target, "issue.md", "new\n")

        assert target.read_bytes() == b"new\n"

    def test_empty_body(self, project_dir: Path) -> None:
        """An empty body gives a 0-byte file and the empty pointer."""
        target = project_dir / "issue.md"

        result = save_body(target, "issue.md", "")

        assert target.read_bytes() == b""
        assert result == "(body saved to issue.md: empty)"

    @pytest.mark.parametrize(
        ("body", "expected"),
        [
            ("a\r\nb\r\n", "(body saved to x.md, 2 lines, CRLF)"),
            ("a\nb\nc", "(body saved to x.md, 3 lines, LF)"),
            ("a\r\nb\n", "(body saved to x.md, 2 lines, mixed)"),
            ("just one line", "(body saved to x.md, 1 line)"),
        ],
        ids=["crlf", "lf", "mixed", "no_break"],
    )
    def test_pointer_text(self, project_dir: Path, body: str, expected: str) -> None:
        """The pointer line names the path, line count and style."""
        assert save_body(project_dir / "x.md", "x.md", body) == expected
