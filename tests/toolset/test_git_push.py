"""Tests for the git_push tool."""

import asyncio
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from git import Repo

from mcp_workspace.toolset import tool_specs

_HELPERS = "mcp_workspace.toolset._git_write_helpers"
_PUSH_OUTPUT = (
    "To origin.git\n * [new branch]      feature -> feature\n"
    "branch 'feature' set up to track 'origin/feature'.\n"
)


def _git_push(project_dir: Path) -> str:
    """Call the git_push tool of a fresh tool set."""
    spec = {s.name: s for s in tool_specs(project_dir)}["git_push"]
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


class TestGitPushUnit:
    """git_push guardrails with the library patched."""

    def test_detached_head(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """A detached HEAD is refused."""
        lib["get_current_branch_name"].return_value = None

        result = _git_push(tmp_path)

        assert result == "Error: HEAD is detached; check out a branch first"
        lib["push_current_branch"].assert_not_called()

    def test_default_branch(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """The default branch is refused."""
        lib["get_current_branch_name"].return_value = "main"

        result = _git_push(tmp_path)

        assert result == "Error: refusing to push the default branch main"
        lib["push_current_branch"].assert_not_called()

    def test_default_unknown(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """An unknown default branch is refused with a hint."""
        lib["get_default_branch_name"].return_value = None

        result = _git_push(tmp_path)

        assert result.startswith("Error: cannot determine the default branch")
        assert "git remote set-head origin -a" in result
        lib["push_current_branch"].assert_not_called()

    def test_rejected(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """A rejected push reports the reason and git's stderr."""
        lib["push_current_branch"].return_value = _push_result(
            "git push failed (exit 1)",
            " ! [rejected]        feature -> feature (fetch first)\n",
        )

        result = _git_push(tmp_path)

        assert result == (
            "Error: git push failed (exit 1)\n"
            "! [rejected]        feature -> feature (fetch first)"
        )

    def test_timeout(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """A timed-out push is an error."""
        lib["push_current_branch"].return_value = _push_result(
            "git push timed out after 120 s", None
        )

        result = _git_push(tmp_path)

        assert result == "Error: git push timed out after 120 s"

    def test_success(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """A successful push names the branch, then git's output."""
        result = _git_push(tmp_path)

        assert result == "Pushed feature to origin\n" + _PUSH_OUTPUT.strip()
        lib["push_current_branch"].assert_called_once_with(tmp_path, False)

    def test_success_without_output(
        self, tmp_path: Path, lib: dict[str, MagicMock]
    ) -> None:
        """Without git output the result is the first line only."""
        lib["push_current_branch"].return_value = _push_result(stderr="")

        result = _git_push(tmp_path)

        assert result == "Pushed feature to origin"


def _feature_branch(project_dir: Path, filename: str = "feature.txt") -> Repo:
    """Check out a new ``feature`` branch with one own commit."""
    repo = Repo(project_dir)
    repo.git.checkout("-b", "feature")
    (project_dir / filename).write_text(f"{filename}\n")
    repo.index.add([filename])
    repo.index.commit(f"Add {filename}")
    return repo


def _origin_heads(project_dir: Path) -> str:
    """Return origin's ``feature`` head as listed by ls-remote."""
    return str(Repo(project_dir).git.ls_remote("--heads", "origin", "feature"))


@pytest.mark.git_integration
class TestGitPushIntegration:
    """git_push against a real clone of a bare origin."""

    def test_new_branch(self, origin_clone: Path) -> None:
        """A new branch is pushed with upstream tracking."""
        repo = _feature_branch(origin_clone)

        result = _git_push(origin_clone)

        assert result.splitlines()[0] == "Pushed feature to origin"
        assert _origin_heads(origin_clone).startswith(repo.head.commit.hexsha)
        upstream = repo.git.rev_parse("--abbrev-ref", "feature@{upstream}")
        assert upstream == "origin/feature"

    def test_tag_with_branch_name(self, origin_clone: Path) -> None:
        """A tag named like the branch does not make the push ambiguous."""
        repo = _feature_branch(origin_clone)
        repo.create_tag("feature", ref="main")

        result = _git_push(origin_clone)

        assert result.splitlines()[0] == "Pushed feature to origin"
        assert _origin_heads(origin_clone).startswith(repo.head.commit.hexsha)

    def test_default_branch(self, origin_clone: Path) -> None:
        """Pushing main is refused."""
        result = _git_push(origin_clone)

        assert result == "Error: refusing to push the default branch main"

    def test_remote_advanced(
        self, origin_clone: Path, make_clone: Callable[[str], Path]
    ) -> None:
        """A push that is not a fast-forward is rejected."""
        other = make_clone("other")
        _feature_branch(other, "other.txt").git.push("origin", "feature")
        repo = _feature_branch(origin_clone)

        result = _git_push(origin_clone)

        assert result.startswith("Error: git push failed")
        assert "rejected" in result
        assert not _origin_heads(origin_clone).startswith(repo.head.commit.hexsha)
