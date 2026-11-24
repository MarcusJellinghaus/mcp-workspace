"""Shared helpers for the reference-tool tests at origin/<default>."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import git

from mcp_workspace.reference_projects import ReferenceProject
from tests.conftest import ToolMap

MakeClone = Callable[[str], Path]
MakeTools = Callable[..., ToolMap]

FALLBACK_NOTE = (
    "[reference ref: no usable origin default branch — read the local folder]"
)


def git_cmd(path: Path, *args: str) -> str:
    """Run a git command in ``path`` and return its stdout."""
    return str(git.Git(path).execute(["git", *args]))


def commit_files(clone: Path, files: dict[str, bytes], message: str = "change") -> str:
    """Write ``files`` byte-exact, commit them (ignored ones too), return HEAD."""
    for rel, data in files.items():
        target = clone / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    git_cmd(clone, "config", "core.autocrlf", "false")
    git_cmd(clone, "add", "-f", "--", *files)
    git_cmd(clone, "commit", "-q", "-m", message)
    return git_cmd(clone, "rev-parse", "HEAD")


def push_main(clone: Path) -> None:
    """Push the clone's HEAD to ``main`` on origin."""
    git_cmd(clone, "push", "-q", "origin", "HEAD:refs/heads/main")


def short_main(path: Path) -> str:
    """Return ``origin/main @ <short sha>`` for ``path``."""
    return f"origin/main @ {git_cmd(path, 'rev-parse', 'refs/remotes/origin/main')[:7]}"


def init_repo(path: Path) -> Path:
    """Create a repository with one commit (``local.txt``) and no remotes."""
    path.mkdir(parents=True)
    git.Git(path).init()
    git_cmd(path, "config", "user.name", "Test User")
    git_cmd(path, "config", "user.email", "test@example.com")
    git_cmd(path, "config", "commit.gpgsign", "false")
    commit_files(path, {"local.txt": b"local\n"})
    return path


def push_upstream(make_clone: MakeClone, files: dict[str, bytes]) -> Path:
    """Push ``files`` to origin's main from a helper clone ``up``."""
    up = make_clone("up")
    commit_files(up, files)
    push_main(up)
    return up


def ref_tools(
    make_tools: MakeTools, path: Path, interval: int = 0, **settings: object
) -> ToolMap:
    """Tools with one reference project ``ref`` at ``path``."""
    return make_tools(
        reference_projects={"ref": ReferenceProject(name="ref", path=path)},
        reference_fetch_interval_minutes=interval,
        **settings,
    )


async def read_ref(tools: ToolMap, path: str, **kwargs: object) -> str:
    """Call ``read_reference_file`` on ``ref``."""
    result: str = await tools["read_reference_file"]("ref", path, **kwargs)
    return result


async def list_ref(tools: ToolMap) -> list[str]:
    """Call ``list_reference_directory`` on ``ref``."""
    result: list[str] = await tools["list_reference_directory"]("ref")
    return result


async def search_ref(tools: ToolMap, **kwargs: object) -> dict[str, Any]:
    """Call ``search_reference_files`` on ``ref``."""
    result: dict[str, Any] = await tools["search_reference_files"]("ref", **kwargs)
    return result


def hit_files(result: dict[str, Any]) -> list[str]:
    """Files of a content search's matches, in result order, without repeats."""
    return list(dict.fromkeys(match["file"] for match in result["details"]))


def ls_tree(path: Path) -> list[str]:
    """Paths at origin/main of ``path`` in ``git ls-tree -r`` order."""
    return git_cmd(
        path, "ls-tree", "-r", "--name-only", "refs/remotes/origin/main"
    ).splitlines()


def make_ref_work(make_clone: MakeClone) -> Path:
    """Work clone whose origin/main holds a known tree, a symlink and a gitlink."""
    up = make_clone("up")
    commit_files(
        up,
        {
            ".gitignore": b"secret.txt\n",
            "CLAUDE.md": b"# Claude\n",
            "secret.txt": b"tracked but ignored\n",
            "src/a.py": b"print('a')\n",
            "z.txt": b"z\n",
        },
    )
    blob = git_cmd(up, "hash-object", "-w", "--", "z.txt")
    head = git_cmd(up, "rev-parse", "HEAD")
    git_cmd(up, "update-index", "--add", "--cacheinfo", f"120000,{blob},link")
    git_cmd(up, "update-index", "--add", "--cacheinfo", f"160000,{head},sub")
    git_cmd(up, "commit", "-q", "-m", "link and gitlink")
    push_main(up)
    return make_clone("work")


# Local folders that are not read at a ref -----------------------------------


def plain_folder(tmp_path: Path) -> Path:
    """A folder that is not a git repository, holding ``file.txt``."""
    path = tmp_path / "plain"
    path.mkdir()
    (path / "file.txt").write_text("x\n", encoding="utf-8")
    return path


def broken_git(tmp_path: Path) -> Path:
    """A plain folder with an empty ``.git`` directory."""
    path = plain_folder(tmp_path)
    (path / ".git").mkdir()
    return path


def nested_in_checkout(tmp_path: Path) -> Path:
    """A folder inside a checkout that has an origin remote."""
    outer = init_repo(tmp_path / "outer")
    git_cmd(outer, "remote", "add", "origin", "https://example.invalid/x.git")
    path = outer / "nested"
    path.mkdir()
    (path / "file.txt").write_text("x\n", encoding="utf-8")
    return path


def repo_without_origin(tmp_path: Path) -> Path:
    """A repository with no remotes and an untracked ``file.txt``."""
    path = init_repo(tmp_path / "repo")
    (path / "file.txt").write_text("x\n", encoding="utf-8")
    return path
