"""Tests for the GitResult branch create/switch/delete functions."""

from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest
from git import Repo

from mcp_workspace.git_operations.branches import (
    create_and_switch_branch,
    delete_local_branch_force,
    switch_branch,
)


def _upstream(project_dir: Path, name: str) -> str | None:
    """Return the upstream of a local branch as ``origin/<b>``, or None."""
    tracking = Repo(project_dir).branches[name].tracking_branch()
    return tracking.name if tracking is not None else None


def _current(project_dir: Path) -> str:
    """Return the checked-out branch name."""
    return Repo(project_dir).active_branch.name


def _commit_on_new_branch(project_dir: Path, name: str, content: str) -> None:
    """Commit ``README.md`` with ``content`` on a new branch, then return to main."""
    repo = Repo(project_dir)
    repo.git.checkout("-b", name)
    (project_dir / "README.md").write_text(content)
    repo.git.commit("-am", f"change on {name}")
    repo.git.checkout("main")


@pytest.mark.git_integration
class TestCreateAndSwitchBranch:
    """create_and_switch_branch against a real clone."""

    def test_from_head(self, origin_clone: Path) -> None:
        """Without a start ref the branch starts at HEAD and has no upstream."""
        result = create_and_switch_branch(origin_clone, "feature")

        assert result["success"] is True
        assert result["error"] is None
        assert _current(origin_clone) == "feature"
        assert _upstream(origin_clone, "feature") is None

    def test_from_local_ref(self, origin_clone: Path) -> None:
        """A local start ref puts the new branch at that ref's tip."""
        _commit_on_new_branch(origin_clone, "other", "other\n")
        repo = Repo(origin_clone)
        repo.git.checkout("other")
        main_sha = repo.git.rev_parse("refs/heads/main")

        result = create_and_switch_branch(origin_clone, "feature", "refs/heads/main")

        assert result["success"] is True
        assert _current(origin_clone) == "feature"
        assert repo.git.rev_parse("HEAD") == main_sha

    def test_from_remote_ref_no_track(self, origin_clone: Path) -> None:
        """``no_track`` leaves a branch started from origin without upstream."""
        result = create_and_switch_branch(
            origin_clone, "feature", "refs/remotes/origin/main", no_track=True
        )

        assert result["success"] is True
        assert _current(origin_clone) == "feature"
        assert _upstream(origin_clone, "feature") is None

    def test_existing_name(self, origin_clone: Path) -> None:
        """Creating an existing branch fails with git's message."""
        result = create_and_switch_branch(origin_clone, "main")

        assert result["success"] is False
        assert result["error"] is not None
        assert result["returncode"] not in (None, 0)
        assert "already exists" in (result["stderr"] or "")


@pytest.mark.git_integration
class TestSwitchBranch:
    """switch_branch against a real clone."""

    def test_local_branch(self, origin_clone: Path) -> None:
        """An existing local branch is checked out."""
        Repo(origin_clone).git.branch("other")

        result = switch_branch(origin_clone, "other")

        assert result["success"] is True
        assert result["error"] is None
        assert _current(origin_clone) == "other"

    def test_remote_only_branch(self, origin_clone: Path) -> None:
        """A name present only as origin/<name> becomes a tracking branch."""
        repo = Repo(origin_clone)
        repo.git.branch("remote-only")
        repo.git.push("origin", "refs/heads/remote-only:refs/heads/remote-only")
        repo.git.branch("-D", "remote-only")
        repo.git.fetch("origin")

        result = switch_branch(origin_clone, "remote-only")

        assert result["success"] is True
        assert _current(origin_clone) == "remote-only"
        assert _upstream(origin_clone, "remote-only") == "origin/remote-only"

    def test_unknown_branch(self, origin_clone: Path) -> None:
        """An unknown name is an error and creates nothing."""
        result = switch_branch(origin_clone, "no-such-branch")

        assert result["success"] is False
        assert "run git fetch first" in (result["error"] or "")
        assert "no-such-branch" not in [b.name for b in Repo(origin_clone).branches]
        assert _current(origin_clone) == "main"

    def test_blocked_by_dirty_file(self, origin_clone: Path) -> None:
        """A conflicting uncommitted change blocks the switch."""
        _commit_on_new_branch(origin_clone, "other", "other\n")
        (origin_clone / "README.md").write_text("dirty\n")

        result = switch_branch(origin_clone, "other")

        assert result["success"] is False
        assert result["error"] is not None
        assert "overwritten" in (result["stderr"] or "")
        assert _current(origin_clone) == "main"


@pytest.mark.git_integration
class TestDeleteLocalBranchForce:
    """delete_local_branch_force against a real clone."""

    def test_unmerged_branch(self, origin_clone: Path) -> None:
        """An unmerged branch is deleted."""
        _commit_on_new_branch(origin_clone, "other", "other\n")

        result = delete_local_branch_force(origin_clone, "other")

        assert result["success"] is True
        assert "other" not in [b.name for b in Repo(origin_clone).branches]

    def test_current_branch(self, origin_clone: Path) -> None:
        """The checked-out branch cannot be deleted."""
        result = delete_local_branch_force(origin_clone, "main")

        assert result["success"] is False
        assert result["error"] is not None
        assert "main" in [b.name for b in Repo(origin_clone).branches]


@pytest.mark.parametrize(
    "call",
    [
        lambda d: create_and_switch_branch(d, "-x"),
        lambda d: create_and_switch_branch(d, "feature", "--orphan"),
        lambda d: switch_branch(d, "-x"),
        lambda d: delete_local_branch_force(d, "-x"),
    ],
)
def test_option_like_argument(tmp_path: Path, call: Callable[[Path], object]) -> None:
    """An option-like name or start ref is rejected without running git."""
    with patch("mcp_workspace.git_operations.branches.run_git_raw") as run:
        result = call(tmp_path)

    run.assert_not_called()
    assert isinstance(result, dict)
    assert result["success"] is False
    assert result["returncode"] is None
    assert "must not start with '-'" in (result["error"] or "")


def test_non_repository(tmp_path: Path) -> None:
    """A directory that is not a repository is an error result."""
    result = switch_branch(tmp_path, "main")

    assert result["success"] is False
    assert "Not a git repository" in (result["error"] or "")
    assert result["returncode"] is None
