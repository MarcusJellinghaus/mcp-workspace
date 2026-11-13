"""move_file and delete_directory check every file of the tree they touch."""

from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from git import Repo

from mcp_workspace.file_tools.access_rules import ACCESS_RULES_FILE
from mcp_workspace.file_tools.move_operations import _determine_move_method, move_file
from tests.conftest import ToolMap

CONTENT = b"content\n"


def _project(
    root: Path, files: tuple[str, ...], rules: str | None = None, gitignore: str = ""
) -> Path:
    """Build a project holding files, a .gitignore and optionally rules."""
    root.mkdir(parents=True, exist_ok=True)
    (root / ".gitignore").write_text(gitignore, encoding="utf-8")
    for name in files:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(CONTENT)
    if rules is not None:
        (root / ACCESS_RULES_FILE).write_text(rules, encoding="utf-8")
    return root


def _snapshot(directory: Path) -> dict[str, bytes]:
    """Return every file below a directory with its content."""
    return {
        p.relative_to(directory).as_posix(): p.read_bytes()
        for p in directory.rglob("*")
        if p.is_file()
    }


def _touch_tree(tools: ToolMap, tool: str, path: str) -> Any:
    """Delete or move the tree at path."""
    if tool == "delete_directory":
        return tools["delete_directory"](path, recursive=True)
    return tools["move_file"](path, "lib")


def _refused(root: Path, call: Callable[[], Any]) -> str:
    """Run a call that must be refused without changing any file.

    Returns:
        The refusal message.
    """
    before = _snapshot(root)
    with pytest.raises(ValueError) as excinfo:
        call()
    assert _snapshot(root) == before
    return str(excinfo.value)


@pytest.mark.parametrize("tool", ["delete_directory", "move_file"])
def test_tree_with_read_only_file_refused(
    tmp_path: Path, make_tools: Callable[..., ToolMap], tool: str
) -> None:
    root = _project(
        tmp_path / "proj",
        ("pkg/keep.txt", "pkg/other.txt"),
        "read-only /pkg/keep.txt\n",
    )
    tools = make_tools(root)

    message = _refused(root, lambda: _touch_tree(tools, tool, "pkg"))

    assert message == (
        f"No write access to 'pkg/keep.txt' (rule '/pkg/keep.txt' in {ACCESS_RULES_FILE})"
    )


@pytest.mark.parametrize("tool", ["delete_directory", "move_file"])
def test_read_only_file_inside_ignored_subdirectory_refused(
    tmp_path: Path, make_tools: Callable[..., ToolMap], tool: str
) -> None:
    root = _project(
        tmp_path / "proj",
        ("pkg/mod.py", "pkg/__pycache__/x.pyc"),
        "read-only /pkg/__pycache__/x.pyc\n",
        "__pycache__/\n",
    )
    tools = make_tools(root)

    message = _refused(root, lambda: _touch_tree(tools, tool, "pkg"))

    assert message.startswith("No write access to 'pkg/__pycache__/x.pyc'")


def test_move_creating_protected_file_refused(
    tmp_path: Path, make_tools: Callable[..., ToolMap]
) -> None:
    root = _project(
        tmp_path / "proj",
        ("srcdir/config.json", "srcdir/other.txt"),
        "read-only /dst/config.json\n",
    )
    tools = make_tools(root)

    message = _refused(root, lambda: tools["move_file"]("srcdir", "dst"))

    assert message == (
        "No write access to 'dst/config.json' "
        f"(rule '/dst/config.json' in {ACCESS_RULES_FILE})"
    )


class TestHiddenFilesInMovedTree:
    """A move must not make a hidden file accessible (Decision 21)."""

    def test_exposed_by_read_write_rule_refused(
        self, tmp_path: Path, make_tools: Callable[..., ToolMap]
    ) -> None:
        root = _project(
            tmp_path / "proj",
            ("src/app/main.py", "src/app/.env"),
            "read-write /.scratch/\n",
            ".env\n.scratch/\n",
        )
        tools = make_tools(root)

        message = _refused(root, lambda: tools["move_file"]("src/app", ".scratch/app"))

        assert message == (
            "Move refused: 'src/app' contains files hidden by .gitignore rules "
            "that would become accessible at '.scratch/app'"
        )
        assert ".env" not in message

    def test_exposed_by_anchored_gitignore_refused(
        self, tmp_path: Path, make_tools: Callable[..., ToolMap]
    ) -> None:
        root = _project(
            tmp_path / "proj",
            ("src/app/main.py", "src/app/.env"),
            gitignore="/src/app/.env\n",
        )
        tools = make_tools(root)

        message = _refused(root, lambda: tools["move_file"]("src/app", "lib/app"))

        assert message.startswith("Move refused: 'src/app' contains files hidden")
        assert ".env" not in message

    def test_hidden_stays_hidden_allowed(
        self, tmp_path: Path, make_tools: Callable[..., ToolMap]
    ) -> None:
        root = _project(
            tmp_path / "proj",
            ("src/a/mod.py", "src/a/__pycache__/mod.pyc"),
            gitignore="__pycache__/\n",
        )

        assert make_tools(root)["move_file"]("src/a", "src/b") is True

        assert not (root / "src" / "a").exists()
        assert (root / "src" / "b" / "__pycache__" / "mod.pyc").read_bytes() == CONTENT


def test_delete_scratch_with_ignored_files_allowed(
    tmp_path: Path, make_tools: Callable[..., ToolMap]
) -> None:
    root = _project(
        tmp_path / "proj",
        (".scratch/probe.py", ".scratch/run.log", ".scratch/sub/__pycache__/x.pyc"),
        "read-write /.scratch/\n",
        ".scratch/\n*.log\n__pycache__/\n",
    )

    make_tools(root)["delete_directory"](".scratch", recursive=True)

    assert not (root / ".scratch").exists()


def test_determine_move_method_gitignored_destination_is_filesystem(
    tmp_path: Path,
) -> None:
    src = tmp_path / "tracked.txt"
    src.write_bytes(CONTENT)
    with (
        patch("mcp_workspace.git_operations.is_git_repository", return_value=True),
        patch("mcp_workspace.git_operations.is_file_tracked", return_value=True),
    ):
        assert _determine_move_method(src, tmp_path, dest_ignored=False) is True
        assert _determine_move_method(src, tmp_path, dest_ignored=True) is False


@pytest.mark.git_integration
class TestMoveIntoGitignoredDestination:
    """A gitignored destination always gets a plain filesystem move."""

    @staticmethod
    def _repo(root: Path) -> Repo:
        """Commit a .gitignore ignoring .scratch/ and a few tracked files."""
        root.mkdir()
        repo = Repo.init(root)
        _project(
            root, ("a.txt", "b.txt", "pkg/one.txt", "pkg/two.txt"), None, ".scratch/\n"
        )
        repo.index.add([".gitignore", "a.txt", "b.txt", "pkg/one.txt", "pkg/two.txt"])
        repo.index.commit("Initial commit")
        return repo

    def test_tracked_file_and_directory(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        repo = self._repo(root)

        # A normal destination keeps the file tracked
        result = move_file("a.txt", "moved.txt", project_dir=root)
        assert result["method"] == "git"
        assert repo.git.ls_files("moved.txt") == "moved.txt"

        result = move_file("b.txt", ".scratch/b.txt", project_dir=root)
        assert result["method"] == "filesystem"
        assert (root / ".scratch" / "b.txt").read_bytes() == CONTENT
        assert repo.git.ls_files(".scratch/b.txt") == ""

        result = move_file("pkg", ".scratch/pkg", project_dir=root)
        assert result["method"] == "filesystem"
        assert (root / ".scratch" / "pkg" / "one.txt").read_bytes() == CONTENT
        assert repo.git.ls_files(".scratch/pkg") == ""
