"""Tests for the git_push_force tool."""

import asyncio
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from git import GitCommandError, Repo

from mcp_workspace.toolset import tool_specs

_HELPERS = "mcp_workspace.toolset._git_write_helpers"
_PUSH_OUTPUT = (
    "To origin.git\n + 1111111...2222222 feature -> feature (forced update)\n"
)
_REFLOG_ERROR = (
    "refs/remotes/origin/feature has no reflog (fresh clone?); "
    "--force-if-includes would refuse falsely. "
    "Force-push via Bash after checking the remote branch"
)


def _git_push_force(project_dir: Path) -> str:
    """Call the git_push_force tool of a fresh tool set."""
    spec = {s.name: s for s in tool_specs(project_dir)}["git_push_force"]
    result: str = asyncio.run(spec.fn())
    return result


def _push_result(
    error: str | None = None, stderr: str | None = _PUSH_OUTPUT
) -> dict[str, Any]:
    """Build the GitResult of push_current_branch."""
    return {
        "success": error is None,
        "error": error,
        "returncode": 0 if error is None else 1,
        "stderr": stderr,
    }


@pytest.fixture
def lib() -> Iterator[dict[str, MagicMock]]:
    """Patch the library functions where the helper module imports them.

    By default ``feature`` is checked out, the default branch is ``main`` and
    the push succeeds.
    """
    defaults: dict[str, Any] = {
        "get_current_branch_name": "feature",
        "get_default_branch_name": "main",
        "push_current_branch": _push_result(),
    }
    patchers = {
        name: patch(f"{_HELPERS}.{name}", return_value=value)
        for name, value in defaults.items()
    }
    mocks = {name: p.start() for name, p in patchers.items()}
    yield mocks
    for p in patchers.values():
        p.stop()


class TestGitPushForceUnit:
    """git_push_force guardrails with the library patched."""

    def test_detached_head(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """A detached HEAD is refused."""
        lib["get_current_branch_name"].return_value = None

        result = _git_push_force(tmp_path)

        assert result == "Error: HEAD is detached; check out a branch first"
        lib["push_current_branch"].assert_not_called()

    def test_default_branch(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """The default branch is refused."""
        lib["get_current_branch_name"].return_value = "main"

        result = _git_push_force(tmp_path)

        assert result == "Error: refusing to push the default branch main"
        lib["push_current_branch"].assert_not_called()

    def test_old_git(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """The library's git version error is passed through."""
        lib["push_current_branch"].return_value = _push_result(
            "git_push_force needs git 2.30+ (--force-if-includes)", None
        )

        result = _git_push_force(tmp_path)

        assert result == "Error: git_push_force needs git 2.30+ (--force-if-includes)"

    def test_no_reflog(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """The library's missing-reflog error is passed through."""
        lib["push_current_branch"].return_value = _push_result(_REFLOG_ERROR, None)

        result = _git_push_force(tmp_path)

        assert result == f"Error: {_REFLOG_ERROR}"

    def test_success(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """A force push uses force=True and reports the lease."""
        result = _git_push_force(tmp_path)

        assert result == (
            "Force-pushed feature to origin (lease ok)\n" + _PUSH_OUTPUT.strip()
        )
        lib["push_current_branch"].assert_called_once_with(tmp_path, True)


def _commit(repo: Repo, filename: str) -> None:
    """Commit one new file in ``repo``."""
    Path(repo.working_dir, filename).write_text(f"{filename}\n", encoding="utf-8")
    repo.index.add([filename])
    repo.index.commit(f"Add {filename}")


def _pushed_feature_branch(project_dir: Path) -> Repo:
    """Check out ``feature`` with one own commit and push it with upstream."""
    repo = Repo(project_dir)
    repo.git.checkout("-b", "feature")
    _commit(repo, "feature.txt")
    repo.git.push("-u", "origin", "feature")
    return repo


def _origin_feature(project_dir: Path) -> str:
    """Return the SHA of origin's ``feature`` branch."""
    heads = Repo(project_dir).git.ls_remote("origin", "refs/heads/feature")
    return str(heads).split()[0]


def _amend(repo: Repo) -> None:
    """Rewrite the current branch's tip."""
    repo.git.commit("--amend", "-m", "Rewritten")


@pytest.mark.git_integration
class TestGitPushForceIntegration:
    """git_push_force against real clones of a bare origin."""

    def test_rebase_after_push(
        self, origin_clone: Path, make_clone: Callable[[str], Path]
    ) -> None:
        """A branch rebased onto an advanced main is force-pushed."""
        repo = _pushed_feature_branch(origin_clone)
        other = Repo(make_clone("other"))
        _commit(other, "main.txt")
        other.git.push("origin", "main")
        repo.git.fetch("origin")
        repo.git.rebase("origin/main")

        result = _git_push_force(origin_clone)

        assert result.splitlines()[0] == "Force-pushed feature to origin (lease ok)"
        assert _origin_feature(origin_clone) == repo.head.commit.hexsha

    def test_remote_advanced_then_fetched(
        self, origin_clone: Path, make_clone: Callable[[str], Path]
    ) -> None:
        """Another clone's fetched-but-unintegrated commit is not overwritten."""
        repo = _pushed_feature_branch(origin_clone)
        other = Repo(make_clone("other"))
        other.git.checkout("feature")
        _commit(other, "other.txt")
        other.git.push("origin", "feature")
        repo.git.fetch("origin")
        _amend(repo)

        result = _git_push_force(origin_clone)

        assert result.startswith("Error:")
        assert _origin_feature(origin_clone) == other.head.commit.hexsha

    def test_fresh_clone(
        self, origin_clone: Path, make_clone: Callable[[str], Path]
    ) -> None:
        """A fresh clone without a remote-tracking reflog is refused."""
        _pushed_feature_branch(origin_clone)
        fresh = Repo(make_clone("fresh"))
        with pytest.raises(GitCommandError):
            fresh.git.reflog("exists", "refs/remotes/origin/feature")
        fresh.git.checkout("feature")
        _amend(fresh)

        result = _git_push_force(Path(fresh.working_dir))

        assert result == f"Error: {_REFLOG_ERROR}"
        assert _origin_feature(origin_clone) != fresh.head.commit.hexsha

    def test_default_branch(self, origin_clone: Path) -> None:
        """Force-pushing main is refused."""
        result = _git_push_force(origin_clone)

        assert result == "Error: refusing to push the default branch main"
