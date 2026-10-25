"""Tests for the pure porcelain ``-z`` parsers (no git, no repos)."""

from mcp_workspace.git_operations.porcelain_parsers import (
    StatusEntry,
    parse_ls_remote_heads,
    parse_merge_tree_z,
    parse_status_z,
)

TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


class TestParseStatusZ:
    """Tests for parse_status_z."""

    def test_empty_output(self) -> None:
        """Empty output parses to an empty list."""
        assert not parse_status_z(b"")

    def test_modified(self) -> None:
        """A worktree modification keeps X and Y apart."""
        assert parse_status_z(b" M src/a.py\0") == [
            StatusEntry(" ", "M", "src/a.py", None)
        ]

    def test_added(self) -> None:
        """A staged addition."""
        assert parse_status_z(b"A  new.txt\0") == [
            StatusEntry("A", " ", "new.txt", None)
        ]

    def test_deleted(self) -> None:
        """A staged deletion and a worktree deletion."""
        assert parse_status_z(b"D  gone.txt\0 D lost.txt\0") == [
            StatusEntry("D", " ", "gone.txt", None),
            StatusEntry(" ", "D", "lost.txt", None),
        ]

    def test_untracked(self) -> None:
        """An untracked file."""
        assert parse_status_z(b"?? notes.txt\0") == [
            StatusEntry("?", "?", "notes.txt", None)
        ]

    def test_rename_with_orig_path(self) -> None:
        """A rename carries its source path in the following field."""
        output = b"R  new name.txt\0old name.txt\0 M other.txt\0"
        assert parse_status_z(output) == [
            StatusEntry("R", " ", "new name.txt", "old name.txt"),
            StatusEntry(" ", "M", "other.txt", None),
        ]

    def test_non_ascii_path(self) -> None:
        """A non-ASCII path is decoded as UTF-8."""
        name = "üñíçødé_日本.txt"
        output = b"?? " + name.encode("utf-8") + b"\0"
        assert parse_status_z(output) == [StatusEntry("?", "?", name, None)]

    def test_without_trailing_nul(self) -> None:
        """A missing trailing NUL (stripped newline) still parses."""
        assert parse_status_z(b"M  a.txt") == [StatusEntry("M", " ", "a.txt", None)]


class TestParseMergeTreeZ:
    """Tests for parse_merge_tree_z."""

    def test_tree_and_two_paths(self) -> None:
        """The tree oid comes first, then the conflicted paths."""
        output = TREE.encode() + b"\0a.txt\0dir/b.txt\0"
        assert parse_merge_tree_z(output) == (TREE, ["a.txt", "dir/b.txt"])

    def test_non_ascii_path(self) -> None:
        """A non-ASCII path is decoded as UTF-8."""
        output = TREE.encode() + b"\0" + "dätei.txt".encode("utf-8") + b"\0"
        assert parse_merge_tree_z(output) == (TREE, ["dätei.txt"])

    def test_tree_only(self) -> None:
        """A tree without paths parses to an empty path list."""
        assert parse_merge_tree_z(TREE.encode() + b"\0") == (TREE, [])

    def test_empty_output(self) -> None:
        """Empty output has no tree."""
        assert parse_merge_tree_z(b"") == (None, [])


class TestParseLsRemoteHeads:
    """Tests for parse_ls_remote_heads."""

    def test_two_heads(self) -> None:
        """Branch names are returned in output order."""
        output = (
            TREE.encode()
            + b"\trefs/heads/main\n"
            + TREE.encode()
            + b"\trefs/heads/team/feature\n"
        )
        assert parse_ls_remote_heads(output) == ["main", "team/feature"]

    def test_non_ascii_branch(self) -> None:
        """A non-ASCII branch name is decoded as UTF-8."""
        output = TREE.encode() + b"\trefs/heads/" + "zweig-ä".encode("utf-8")
        assert parse_ls_remote_heads(output) == ["zweig-ä"]

    def test_empty_output(self) -> None:
        """Empty output parses to an empty list."""
        assert not parse_ls_remote_heads(b"")
