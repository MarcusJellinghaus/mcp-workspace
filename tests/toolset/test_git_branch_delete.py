"""Tests for the git_branch_delete tool."""

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from git import Repo
from github.GithubException import GithubException

from mcp_workspace.toolset import tool_specs

_HELPERS = "mcp_workspace.toolset._git_write_helpers"
_TIP = "0123456789abcdef0123456789abcdef01234567"
_REMOTE = "fedcba9876543210fedcba9876543210fedcba98"
_OK = {"success": True, "error": None, "returncode": 0, "stderr": ""}


def _git_branch_delete(project_dir: Path, name: str) -> str:
    """Call the git_branch_delete tool of a fresh tool set."""
    spec = {s.name: s for s in tool_specs(project_dir)}["git_branch_delete"]
    result: str = asyncio.run(spec.fn(name=name))
    return result


def _remote(sha: str | None, error: str | None = None) -> dict[str, Any]:
    """Build a RemoteHeadResult."""
    return {
        "success": error is None,
        "error": error,
        "returncode": 0 if error is None else 128,
        "stderr": "",
        "sha": sha,
    }


@pytest.fixture
def lib() -> Iterator[dict[str, MagicMock]]:
    """Patch the library functions where the helper module imports them.

    By default the branch ``feature`` exists, is not checked out, and no check
    finds its tip on GitHub.
    """
    manager = MagicMock()
    manager.find_merged_pr_by_head_sha.return_value = None
    defaults: dict[str, Any] = {
        "is_valid_branch_name_strict": True,
        "get_current_branch_name": "main",
        "get_default_branch_name": "main",
        "resolve_commit": _TIP,
        "remote_head_sha": _remote(None),
        "is_ancestor": False,
        "pr_manager": manager,
        "delete_local_branch_force": _OK,
    }
    patchers = {
        name: patch(f"{_HELPERS}.{name}", return_value=value)
        for name, value in defaults.items()
    }
    mocks = {name: p.start() for name, p in patchers.items()}
    yield mocks
    for p in patchers.values():
        p.stop()


def _merged_pr(lib: dict[str, MagicMock]) -> MagicMock:
    """Return the mocked find_merged_pr_by_head_sha."""
    lookup: MagicMock = lib["pr_manager"].return_value.find_merged_pr_by_head_sha
    return lookup


class TestGitBranchDeleteUnit:
    """git_branch_delete guardrails with the library patched."""

    def test_invalid_name(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """A name git rejects is refused before anything else."""
        lib["is_valid_branch_name_strict"].return_value = False

        result = _git_branch_delete(tmp_path, "a..b")

        assert result == "Error: invalid branch name: 'a..b'"
        lib["delete_local_branch_force"].assert_not_called()

    def test_current_branch(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """The checked-out branch is refused."""
        lib["get_current_branch_name"].return_value = "feature"

        result = _git_branch_delete(tmp_path, "feature")

        assert result == "Error: cannot delete the current branch"
        lib["delete_local_branch_force"].assert_not_called()

    def test_default_branch(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """The detected default branch is refused."""
        lib["get_current_branch_name"].return_value = "feature"
        lib["get_default_branch_name"].return_value = "develop"

        result = _git_branch_delete(tmp_path, "develop")

        assert result == "Error: refusing to delete the default branch develop"
        lib["delete_local_branch_force"].assert_not_called()

    @pytest.mark.parametrize("name", ["main", "master"])
    def test_main_and_master_when_default_unknown(
        self, tmp_path: Path, lib: dict[str, MagicMock], name: str
    ) -> None:
        """Without a known default, main and master are both refused."""
        lib["get_current_branch_name"].return_value = "feature"
        lib["get_default_branch_name"].return_value = None

        result = _git_branch_delete(tmp_path, name)

        assert result == f"Error: refusing to delete the default branch {name}"
        lib["delete_local_branch_force"].assert_not_called()

    def test_no_local_branch(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """A name with no local branch is an error."""
        lib["resolve_commit"].return_value = None

        result = _git_branch_delete(tmp_path, "feature")

        assert result == "Error: no local branch feature"
        lib["remote_head_sha"].assert_not_called()

    def test_check_1_passes(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """origin's branch containing the tip suffices; later checks are skipped."""
        lib["remote_head_sha"].return_value = _remote(_REMOTE)
        lib["is_ancestor"].return_value = True

        result = _git_branch_delete(tmp_path, "feature")

        assert result == (
            "Deleted branch feature (tip 0123456 on origin)\n"
            "Verified by: feature on GitHub contains the tip"
        )
        lib["is_ancestor"].assert_called_once_with(tmp_path, _TIP, _REMOTE)
        lib["pr_manager"].assert_not_called()
        lib["delete_local_branch_force"].assert_called_once_with(tmp_path, "feature")

    def test_check_2_passes(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """origin/<default> containing the tip suffices when check 1 fails."""
        lib["remote_head_sha"].return_value = _remote(_REMOTE)
        lib["is_ancestor"].side_effect = lambda _d, _a, d: d.startswith("refs/")

        result = _git_branch_delete(tmp_path, "feature")

        assert result.endswith("Verified by: origin/main contains the tip")
        lib["is_ancestor"].assert_called_with(
            tmp_path, _TIP, "refs/remotes/origin/main"
        )
        lib["pr_manager"].assert_not_called()
        lib["delete_local_branch_force"].assert_called_once()

    def test_check_3_passes(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """A merged PR with the tip as head suffices when checks 1/2 fail."""
        _merged_pr(lib).return_value = 42

        result = _git_branch_delete(tmp_path, "feature")

        assert result.endswith("Verified by: merged PR #42")
        _merged_pr(lib).assert_called_once_with(_TIP)
        lib["delete_local_branch_force"].assert_called_once()

    def test_missing_object_does_not_short_circuit(
        self, tmp_path: Path, lib: dict[str, MagicMock]
    ) -> None:
        """An undecidable check 1 still lets check 3 pass."""
        lib["remote_head_sha"].return_value = _remote(_REMOTE)
        lib["is_ancestor"].side_effect = lambda _d, _a, d: (
            None if d == _REMOTE else False
        )
        _merged_pr(lib).return_value = 7

        result = _git_branch_delete(tmp_path, "feature")

        assert result.endswith("Verified by: merged PR #7")
        lib["delete_local_branch_force"].assert_called_once()

    def test_none_passes_object_missing(
        self, tmp_path: Path, lib: dict[str, MagicMock]
    ) -> None:
        """With a check undecided for a missing object, the user must fetch."""
        lib["remote_head_sha"].return_value = _remote(_REMOTE)
        lib["is_ancestor"].side_effect = lambda _d, _a, d: (
            None if d == _REMOTE else False
        )

        result = _git_branch_delete(tmp_path, "feature")

        assert result.startswith("Error: cannot verify tip 0123456 of feature")
        assert "run git fetch first" in result
        lib["delete_local_branch_force"].assert_not_called()

    def test_none_passes(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """With every check decided negatively, the tip is not on GitHub."""
        result = _git_branch_delete(tmp_path, "feature")

        assert result == (
            "Error: refusing to delete feature: tip 0123456 is not on GitHub"
        )
        lib["delete_local_branch_force"].assert_not_called()

    def test_pr_check_skipped_without_token(
        self, tmp_path: Path, lib: dict[str, MagicMock]
    ) -> None:
        """A failing PR manager skips check 3; checks 1/2 still decide."""
        lib["pr_manager"].side_effect = ValueError("GitHub token not configured")

        refused = _git_branch_delete(tmp_path, "feature")

        assert refused == (
            "Error: refusing to delete feature: tip 0123456 is not on GitHub\n"
            "merged-PR check skipped: GitHub token not configured"
        )

        lib["is_ancestor"].return_value = True
        deleted = _git_branch_delete(tmp_path, "feature")

        assert deleted.endswith("Verified by: origin/main contains the tip")

    def test_pr_lookup_failure_is_not_a_negative_answer(
        self, tmp_path: Path, lib: dict[str, MagicMock]
    ) -> None:
        """A GitHub API error in check 3 is reported as a failed check."""
        _merged_pr(lib).side_effect = GithubException(
            502, {"message": "Bad Gateway"}, None
        )

        result = _git_branch_delete(tmp_path, "feature")

        lines = result.splitlines()
        assert lines[0] == (
            "Error: cannot verify tip 0123456 of feature: the GitHub check "
            "failed; retry later"
        )
        assert lines[1].startswith("merged-PR check failed: 502")
        assert "is not on GitHub" not in result
        lib["delete_local_branch_force"].assert_not_called()

    def test_remote_failure_is_not_a_negative_answer(
        self, tmp_path: Path, lib: dict[str, MagicMock]
    ) -> None:
        """A failed ls-remote in check 1 is reported as a failed check."""
        lib["remote_head_sha"].return_value = _remote(
            None, "git ls-remote failed (exit 128)"
        )

        result = _git_branch_delete(tmp_path, "feature")

        assert result == (
            "Error: cannot verify tip 0123456 of feature: the GitHub check "
            "failed; retry later\n"
            "GitHub branch check failed: git ls-remote failed (exit 128)"
        )
        lib["is_ancestor"].assert_called_once_with(
            tmp_path, _TIP, "refs/remotes/origin/main"
        )
        lib["delete_local_branch_force"].assert_not_called()

    def test_remote_branch_without_tip(
        self, tmp_path: Path, lib: dict[str, MagicMock]
    ) -> None:
        """A successful ls-remote whose branch lacks the tip is a negative answer."""
        lib["remote_head_sha"].return_value = _remote(_REMOTE)

        result = _git_branch_delete(tmp_path, "feature")

        assert result == (
            "Error: refusing to delete feature: tip 0123456 is not on GitHub"
        )
        lib["delete_local_branch_force"].assert_not_called()

    def test_delete_failure(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """A failed git branch -D reports the reason and git's stderr."""
        lib["is_ancestor"].return_value = True
        lib["delete_local_branch_force"].return_value = {
            "success": False,
            "error": "git branch -D failed (exit 1)",
            "returncode": 1,
            "stderr": "error: branch not found\n",
        }

        result = _git_branch_delete(tmp_path, "feature")

        assert result == (
            "Error: git branch -D failed (exit 1)\nerror: branch not found"
        )


def _commit(project_dir: Path, filename: str) -> str:
    """Commit one new file and return the commit SHA."""
    repo = Repo(project_dir)
    (project_dir / filename).write_text(f"{filename}\n")
    repo.index.add([filename])
    return repo.index.commit(f"Add {filename}").hexsha


def _branches(project_dir: Path) -> list[str]:
    """Return the local branch names."""
    return [b.name for b in Repo(project_dir).branches]


def _feature_branch(project_dir: Path, push: bool) -> str:
    """Create ``feature`` with one own commit, optionally push it, back on main."""
    repo = Repo(project_dir)
    repo.git.checkout("-b", "feature")
    tip = _commit(project_dir, "feature.txt")
    if push:
        repo.git.push("origin", "feature")
    repo.git.checkout("main")
    return tip


@pytest.mark.git_integration
class TestGitBranchDeleteIntegration:
    """git_branch_delete against a real clone, with the PR lookup patched."""

    @pytest.fixture(autouse=True)
    def merged_pr(self) -> Iterator[MagicMock]:
        """Patch the merged-PR lookup to find nothing."""
        with patch(f"{_HELPERS}.pr_manager") as manager:
            lookup: MagicMock = manager.return_value.find_merged_pr_by_head_sha
            lookup.return_value = None
            yield lookup

    def test_squash_merged_branch(
        self, origin_clone: Path, merged_pr: MagicMock
    ) -> None:
        """A squash-merged, remote-deleted branch needs the merged-PR check."""
        tip = _feature_branch(origin_clone, push=True)
        repo = Repo(origin_clone)
        repo.git.merge("--squash", "feature")
        repo.index.commit("Squash feature")
        repo.git.push("origin", "main")
        repo.git.push("origin", "--delete", "feature")

        refused = _git_branch_delete(origin_clone, "feature")

        assert refused == (
            f"Error: refusing to delete feature: tip {tip[:7]} is not on GitHub"
        )
        assert "feature" in _branches(origin_clone)

        merged_pr.return_value = 7
        deleted = _git_branch_delete(origin_clone, "feature")

        assert deleted == (
            f"Deleted branch feature (tip {tip[:7]} on origin)\n"
            "Verified by: merged PR #7"
        )
        merged_pr.assert_called_with(tip)
        assert "feature" not in _branches(origin_clone)

    def test_fast_forward_merged_branch(self, origin_clone: Path) -> None:
        """A fast-forward-merged, remote-deleted branch passes via origin/main."""
        tip = _feature_branch(origin_clone, push=True)
        repo = Repo(origin_clone)
        repo.git.merge("--ff-only", "feature")
        repo.git.push("origin", "main")
        repo.git.push("origin", "--delete", "feature")

        result = _git_branch_delete(origin_clone, "feature")

        assert result == (
            f"Deleted branch feature (tip {tip[:7]} on origin)\n"
            "Verified by: origin/main contains the tip"
        )
        assert "feature" not in _branches(origin_clone)

    def test_unpushed_branch(self, origin_clone: Path) -> None:
        """A branch never pushed is refused and kept."""
        tip = _feature_branch(origin_clone, push=False)

        result = _git_branch_delete(origin_clone, "feature")

        assert result == (
            f"Error: refusing to delete feature: tip {tip[:7]} is not on GitHub"
        )
        assert "feature" in _branches(origin_clone)

    def test_pushed_branch_keeps_remote(self, origin_clone: Path) -> None:
        """A pushed branch is deleted locally only."""
        tip = _feature_branch(origin_clone, push=True)

        result = _git_branch_delete(origin_clone, "feature")

        assert result == (
            f"Deleted branch feature (tip {tip[:7]} on origin)\n"
            "Verified by: feature on GitHub contains the tip"
        )
        assert "feature" not in _branches(origin_clone)
        remote = str(Repo(origin_clone).git.ls_remote("--heads", "origin", "feature"))
        assert remote.startswith(tip)

    def test_current_branch(self, origin_clone: Path) -> None:
        """The checked-out branch is refused."""
        result = _git_branch_delete(origin_clone, "main")

        assert result == "Error: cannot delete the current branch"
        assert "main" in _branches(origin_clone)
