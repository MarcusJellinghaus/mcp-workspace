"""The file tools refuse the git directory and gitignored paths however spelled."""

import asyncio
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from mcp_workspace import server
from mcp_workspace.file_tools import read_file as read_file_util
from mcp_workspace.file_tools.directory_utils import is_path_gitignored, list_files
from mcp_workspace.file_tools.path_utils import normalize_path
from mcp_workspace.utils.git_paths import canonical_spelling, is_path_in_git_dir
from tests.conftest import ToolMap

CONFIG_TEXT = "[core]\n\trepositoryformatversion = 0\n"
SECRET_TEXT = "SECRET=1\n"

GIT_DIR_SPELLINGS = [
    ".git/config",
    ".GIT/config",
    ".Git/config",
    ".git./config",
    ".git../config",
    ".git /config",
    ".GiT. /config",
    ".git::$INDEX_ALLOCATION/config",
    ".git:stream/config",
    "sub/.GIT/config",
]

# Each entry calls one workspace file tool with a path it must refuse.
FILE_TOOLS: dict[str, Callable[[ToolMap, str], Any]] = {
    "read_file": lambda t, p: t["read_file"](p),
    "save_file": lambda t, p: t["save_file"](p, "changed"),
    "append_file": lambda t, p: t["append_file"](p, "changed"),
    "edit_file": lambda t, p: asyncio.run(t["edit_file"](p, "core", "changed")),
    "delete_this_file": lambda _t, p: server.delete_this_file(p),
    "delete_directory": lambda _t, p: server.delete_directory(
        str(Path(p).parent), recursive=True
    ),
    "move_file_source": lambda _t, p: server.move_file(p, "moved.txt"),
    "move_file_destination": lambda _t, p: server.move_file("plain.txt", p + ".new"),
    "list_directory": lambda t, p: t["list_directory"](str(Path(p).parent)),
}


def _snapshot(directory: Path) -> dict[str, bytes]:
    """Return every file below a directory with its content."""
    return {
        p.relative_to(directory).as_posix(): p.read_bytes()
        for p in directory.rglob("*")
        if p.is_file()
    }


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Project with a git directory, a gitignored secret, and a plain file."""
    root = tmp_path / "project"
    (root / ".git" / "hooks").mkdir(parents=True)
    (root / ".git" / "config").write_text(CONFIG_TEXT, encoding="utf-8")
    (root / "secret").mkdir()
    (root / "secret" / "key.txt").write_text(SECRET_TEXT, encoding="utf-8")
    (root / ".gitignore").write_text(".env\nsecret/\n*.log\n", encoding="utf-8")
    (root / ".env").write_text(SECRET_TEXT, encoding="utf-8")
    (root / "plain.txt").write_text("plain\n", encoding="utf-8")
    monkeypatch.setattr(server, "_project_dir", root)
    return root


@pytest.fixture
def tools(project: Path, make_tools: Callable[..., ToolMap]) -> ToolMap:
    """Tools bound to the project fixture."""
    return make_tools(project)


def _make_file_link(link: Path, target: Path) -> None:
    """Create a file symlink, or skip when this machine does not allow it."""
    try:
        os.symlink(target, link)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")


def _make_dir_link(link: Path, target: Path) -> None:
    """Create a directory link: a junction on Windows, a symlink elsewhere."""
    if sys.platform == "win32":
        import _winapi  # pylint: disable=import-outside-toplevel,import-error

        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


class TestGitDirSpelling:
    """The name rule is pure string logic and holds on every OS."""

    @pytest.mark.parametrize("path", GIT_DIR_SPELLINGS + [".git", ".git\\config"])
    def test_git_dir_spellings_are_detected(self, path: str) -> None:
        assert is_path_in_git_dir(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            ".github/workflows/ci.yml",
            ".gitignore",
            ".gitattributes",
            ".gitmodules",
            "git/config",
            "project.git/config",
            ".git_old/config",
            "src/.gitkeep",
            "docs/.git-notes.md",
        ],
    )
    def test_similar_names_are_not_detected(self, path: str) -> None:
        assert is_path_in_git_dir(path) is False

    @pytest.mark.parametrize(
        "spelled, canonical",
        [
            (".env", ".env"),
            (".env.", ".env"),
            (".env ", ".env"),
            (".env::$DATA", ".env"),
            ("a.b/c.d", "a.b/c.d"),
            ("logs./x.log::$DATA", "logs/x.log"),
            ("a\\b.log.", "a/b.log"),
        ],
    )
    def test_canonical_spelling(self, spelled: str, canonical: str) -> None:
        assert canonical_spelling(spelled) == canonical


class TestNormalizePathRefusesGitDir:
    """normalize_path is the layer every file tool shares."""

    @pytest.mark.parametrize("path", GIT_DIR_SPELLINGS)
    def test_relative_spellings(self, project: Path, path: str) -> None:
        with pytest.raises(ValueError, match="git directory"):
            normalize_path(path, project)

    def test_absolute_path(self, project: Path) -> None:
        with pytest.raises(ValueError, match="git directory"):
            normalize_path(str(project / ".git" / "config"), project)

    def test_nonexistent_path(self, project: Path) -> None:
        with pytest.raises(ValueError, match="git directory"):
            normalize_path(".GIT/hooks/new-file", project)

    def test_ordinary_paths_still_normalize(self, project: Path) -> None:
        assert normalize_path(".github/x.yml", project)[1] == ".github/x.yml"
        assert normalize_path(".gitignore", project)[1] == ".gitignore"
        assert normalize_path("plain.txt", project)[1] == "plain.txt"

    def test_reference_read_layer_refuses_git_dir(self, project: Path) -> None:
        with pytest.raises(ValueError, match="git directory"):
            read_file_util(".git/config", project_dir=project)


class TestFileToolsRefuseGitDir:
    """Every workspace file tool refuses the git directory and changes nothing."""

    @pytest.mark.parametrize("tool", sorted(FILE_TOOLS))
    @pytest.mark.parametrize("path", GIT_DIR_SPELLINGS)
    def test_refused_without_side_effect(
        self, project: Path, tools: ToolMap, tool: str, path: str
    ) -> None:
        if tool in ("delete_directory", "list_directory") and "/" not in path:
            pytest.skip("directory tools take the parent")
        before = _snapshot(project)
        with pytest.raises(ValueError):
            FILE_TOOLS[tool](tools, path)
        assert _snapshot(project) == before

    def test_read_returns_no_content(self, tools: ToolMap) -> None:
        with pytest.raises(ValueError) as excinfo:
            tools["read_file"](".GIT/config")
        assert "repositoryformatversion" not in str(excinfo.value)

    def test_search_does_not_reach_git_dir(self, tools: ToolMap) -> None:
        result = tools["search_files"](pattern="repositoryformatversion")
        assert result["details"] == []

    def test_listing_omits_git_dir(self, tools: ToolMap) -> None:
        listed = tools["list_directory"](".")
        assert not any(is_path_in_git_dir(entry) for entry in listed)

    @pytest.mark.parametrize("spelling", [".git", ".GIT", ".git."])
    def test_listing_refuses_git_dir_itself(
        self, tools: ToolMap, spelling: str
    ) -> None:
        with pytest.raises(ValueError):
            tools["list_directory"](spelling)


class TestGitFileAndNestedRepos:
    """A `.git` file and repositories below the project get the same rule."""

    def test_git_file_refused(self, project: Path, tools: ToolMap) -> None:
        worktree = project / "wt"
        worktree.mkdir()
        (worktree / ".git").write_text("gitdir: ../elsewhere\n", encoding="utf-8")
        with pytest.raises(ValueError):
            tools["read_file"]("wt/.git")

    def test_git_file_not_listed(self, project: Path) -> None:
        worktree = project / "wt"
        worktree.mkdir()
        (worktree / ".git").write_text("gitdir: ../elsewhere\n", encoding="utf-8")
        (worktree / "file.txt").write_text("x", encoding="utf-8")
        assert list_files("wt", project) == ["wt/file.txt"]

    def test_nested_repo_refused(self, project: Path, tools: ToolMap) -> None:
        nested = project / "vendor" / "lib" / ".git"
        nested.mkdir(parents=True)
        (nested / "config").write_text(CONFIG_TEXT, encoding="utf-8")
        with pytest.raises(ValueError):
            tools["read_file"]("vendor/lib/.git/config")

    def test_recursive_delete_keeps_nested_repo(self, project: Path) -> None:
        nested = project / "vendor" / "lib" / ".git"
        nested.mkdir(parents=True)
        (nested / "config").write_text(CONFIG_TEXT, encoding="utf-8")
        with pytest.raises(ValueError, match="git directory"):
            server.delete_directory("vendor", recursive=True)
        assert (nested / "config").is_file()

    def test_move_keeps_nested_repo(self, project: Path) -> None:
        nested = project / "vendor" / "lib" / ".git"
        nested.mkdir(parents=True)
        with pytest.raises(ValueError):
            server.move_file("vendor", "elsewhere")
        assert nested.is_dir()

    def test_directory_without_repo_still_deletes_and_moves(
        self, project: Path
    ) -> None:
        (project / "old").mkdir()
        (project / "old" / "x.txt").write_text("x", encoding="utf-8")
        assert server.move_file("old", "new") is True
        server.delete_directory("new", recursive=True)
        assert not (project / "new").exists()


class TestFilesystemAliases:
    """These need a filesystem that resolves the alias; skipped elsewhere."""

    @pytest.mark.parametrize("alias", [".GIT", ".git.", "GIT~1"])
    def test_alias_of_git_dir_is_refused(
        self, project: Path, tools: ToolMap, alias: str
    ) -> None:
        if not (project / alias / "config").is_file():
            pytest.skip(f"{alias} is not an alias of .git on this filesystem")
        before = _snapshot(project)
        with pytest.raises(ValueError):
            tools["read_file"](f"{alias}/config")
        with pytest.raises(ValueError):
            tools["append_file"](f"{alias}/config", "changed")
        assert _snapshot(project) == before

    def test_short_name_below_git_dir_for_new_file(
        self, project: Path, tools: ToolMap
    ) -> None:
        if not (project / "GIT~1").is_dir():
            pytest.skip("no short name for .git on this filesystem")
        with pytest.raises(ValueError):
            tools["save_file"]("GIT~1/hooks/new-file", "changed")
        assert not (project / ".git" / "hooks" / "new-file").exists()


class TestLinksIntoProtectedPaths:
    """A link inside the project gets the rule of the location it points to."""

    def test_directory_link_to_git_dir(self, project: Path, tools: ToolMap) -> None:
        _make_dir_link(project / "gitlink", project / ".git")
        before = _snapshot(project / ".git")
        with pytest.raises(ValueError):
            tools["read_file"]("gitlink/config")
        with pytest.raises(ValueError):
            tools["save_file"]("gitlink/hooks/new-file", "changed")
        assert _snapshot(project / ".git") == before

    def test_directory_link_to_gitignored_dir(
        self, project: Path, tools: ToolMap
    ) -> None:
        _make_dir_link(project / "seclink", project / "secret")
        with pytest.raises(ValueError, match="excluded by .gitignore"):
            tools["read_file"]("seclink/key.txt")

    def test_file_link_to_gitignored_file(self, project: Path, tools: ToolMap) -> None:
        _make_file_link(project / "envlink", project / ".env")
        with pytest.raises(ValueError, match="excluded by .gitignore"):
            tools["read_file"]("envlink")

    def test_file_link_to_git_config(self, project: Path, tools: ToolMap) -> None:
        _make_file_link(project / "cfglink", project / ".git" / "config")
        with pytest.raises(ValueError):
            tools["read_file"]("cfglink")

    def test_search_skips_file_link_to_gitignored_file(
        self, project: Path, tools: ToolMap
    ) -> None:
        _make_file_link(project / "envlink", project / ".env")
        result = tools["search_files"](pattern="SECRET")
        assert result["details"] == []

    def test_listing_omits_file_link_to_gitignored_file(
        self, project: Path, tools: ToolMap
    ) -> None:
        _make_file_link(project / "envlink", project / ".env")
        assert "envlink" not in tools["list_directory"](".")

    def test_link_to_tracked_file_still_works(
        self, project: Path, tools: ToolMap
    ) -> None:
        _make_file_link(project / "plainlink", project / "plain.txt")
        assert tools["read_file"]("plainlink") == "plain\n"
        assert "plainlink" in tools["list_directory"](".")


class TestGitignoreSpelling:
    """Gitignored paths stay refused under other spellings of the same name."""

    @pytest.mark.parametrize(
        "path",
        [
            ".env",
            ".env.",
            ".env ",
            ".env::$DATA",
            ".env:stream",
            "secret/key.txt",
            "secret./key.txt",
            "debug.log",
            "debug.log::$DATA",
            "sub\\debug.log",
        ],
    )
    def test_spellings_are_ignored(self, project: Path, path: str) -> None:
        assert is_path_gitignored(path, project) is True

    @pytest.mark.parametrize("path", ["plain.txt", "docs/env.md", "log.txt", "a:b.txt"])
    def test_other_names_are_not_ignored(self, project: Path, path: str) -> None:
        assert is_path_gitignored(path, project) is False

    @pytest.mark.parametrize("path", [".env::$DATA", ".env:stream"])
    def test_read_and_write_refused(
        self, project: Path, tools: ToolMap, path: str
    ) -> None:
        before = _snapshot(project)
        with pytest.raises(ValueError, match="excluded by .gitignore"):
            tools["read_file"](path)
        with pytest.raises(ValueError, match="excluded by .gitignore"):
            tools["save_file"](path, "changed")
        assert _snapshot(project) == before

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows name matching")
    @pytest.mark.parametrize("path", [".ENV", "SECRET/key.txt", "DEBUG.LOG"])
    def test_case_variants_refused_on_windows(self, tools: ToolMap, path: str) -> None:
        with pytest.raises(ValueError, match="excluded by .gitignore"):
            tools["read_file"](path)
