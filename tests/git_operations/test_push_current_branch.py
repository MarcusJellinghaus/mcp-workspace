"""Tests for push_current_branch."""

from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from git import Repo

from mcp_workspace.git_operations._subprocess_git import GitOutput
from mcp_workspace.git_operations.core import GitResult
from mcp_workspace.git_operations.remotes import push_current_branch

from .conftest import commit_files

MODULE = "mcp_workspace.git_operations.remotes"


def _output(success: bool = True, stderr: str | None = "pushed\n") -> GitOutput:
    """Build a run_git_timed result."""
    return GitOutput(
        success=success,
        error=None if success else "git push failed (exit 1)",
        returncode=0 if success else 1,
        stderr=stderr,
        stdout="ignored\n",
    )


def _push_patched(
    project_dir: Path,
    run_mock: MagicMock,
    force: bool = False,
    branch: str | None = "b",
    version: tuple[int, int] = (2, 43),
    reflog: bool = True,
) -> GitResult:
    """Call push_current_branch with its collaborators patched."""
    with (
        patch(f"{MODULE}.get_current_branch_name", return_value=branch),
        patch(f"{MODULE}.git_version", return_value=version),
        patch(f"{MODULE}._remote_tracking_reflog_exists", return_value=reflog),
        patch(f"{MODULE}.run_git_timed", run_mock),
    ):
        return push_current_branch(project_dir, force=force)


class TestPushCurrentBranchUnit:
    """push_current_branch with git calls mocked."""

    def test_plain_push_argv(self, git_repo: tuple[Repo, Path]) -> None:
        """A plain push is exactly ``push -u origin <full refspec>``."""
        _, project_dir = git_repo
        run_mock = MagicMock(return_value=_output())

        result = _push_patched(project_dir, run_mock)

        run_mock.assert_called_once_with(
            project_dir, "push", "-u", "origin", "refs/heads/b:refs/heads/b"
        )
        assert result == {
            "success": True,
            "error": None,
            "returncode": 0,
            "stderr": "pushed\n",
        }

    def test_force_push_argv(self, git_repo: tuple[Repo, Path]) -> None:
        """A force push uses lease and includes-check, never plain --force."""
        _, project_dir = git_repo
        run_mock = MagicMock(return_value=_output())

        _push_patched(project_dir, run_mock, force=True)

        argv = run_mock.call_args.args[1:]
        assert argv == (
            "push",
            "-u",
            "--force-with-lease",
            "--force-if-includes",
            "origin",
            "refs/heads/b:refs/heads/b",
        )
        assert "--force" not in argv
        assert "-f" not in argv

    def test_detached_head(self, git_repo: tuple[Repo, Path]) -> None:
        """Detached HEAD is refused before any push runs."""
        _, project_dir = git_repo
        run_mock = MagicMock()

        result = _push_patched(project_dir, run_mock, branch=None)

        assert result == {
            "success": False,
            "error": "HEAD is detached; check out a branch first",
            "returncode": None,
            "stderr": None,
        }
        run_mock.assert_not_called()

    def test_force_needs_git_2_30(self, git_repo: tuple[Repo, Path]) -> None:
        """Git older than 2.30 refuses a force push."""
        _, project_dir = git_repo
        run_mock = MagicMock()

        result = _push_patched(project_dir, run_mock, force=True, version=(2, 29))

        assert result == {
            "success": False,
            "error": "git_push_force needs git 2.30+ (--force-if-includes)",
            "returncode": None,
            "stderr": None,
        }
        run_mock.assert_not_called()

    def test_force_needs_reflog(self, git_repo: tuple[Repo, Path]) -> None:
        """A missing remote-tracking reflog refuses a force push."""
        _, project_dir = git_repo
        run_mock = MagicMock()

        result = _push_patched(project_dir, run_mock, force=True, reflog=False)

        assert result["success"] is False
        assert result["error"] == (
            "refs/remotes/origin/b has no reflog (fresh clone?); "
            "--force-if-includes would refuse falsely. "
            "Force-push via Bash after checking the remote branch"
        )
        assert result["returncode"] is None
        run_mock.assert_not_called()

    def test_plain_push_skips_force_checks(self, git_repo: tuple[Repo, Path]) -> None:
        """Old git and no reflog do not block a plain push."""
        _, project_dir = git_repo
        run_mock = MagicMock(return_value=_output())

        result = _push_patched(project_dir, run_mock, version=(2, 20), reflog=False)

        assert result["success"] is True
        run_mock.assert_called_once()

    def test_timeout_passed_through(self, git_repo: tuple[Repo, Path]) -> None:
        """A timed-out push is reported as run_git_timed returned it."""
        _, project_dir = git_repo
        run_mock = MagicMock(
            return_value=GitOutput(
                success=False,
                error="git push timed out after 120 s",
                returncode=None,
                stderr=None,
                stdout="",
            )
        )

        result = _push_patched(project_dir, run_mock)

        assert result == {
            "success": False,
            "error": "git push timed out after 120 s",
            "returncode": None,
            "stderr": None,
        }

    def test_failure_keeps_stderr(self, git_repo: tuple[Repo, Path]) -> None:
        """A rejected push keeps error and stderr, drops stdout."""
        _, project_dir = git_repo
        run_mock = MagicMock(return_value=_output(False, "rejected\n"))

        result = _push_patched(project_dir, run_mock)

        assert result == {
            "success": False,
            "error": "git push failed (exit 1)",
            "returncode": 1,
            "stderr": "rejected\n",
        }

    def test_not_a_repository(self, tmp_path: Path) -> None:
        """A non-repository is an error without running git."""
        with patch(f"{MODULE}.run_git_timed") as run_mock:
            result = push_current_branch(tmp_path)

        assert result == {
            "success": False,
            "error": f"Not a git repository: {tmp_path}",
            "returncode": None,
            "stderr": None,
        }
        run_mock.assert_not_called()


def _new_branch(clone_dir: Path, name: str = "feature") -> Repo:
    """Check out a new branch in ``clone_dir`` with one commit on it."""
    repo = Repo(clone_dir)
    repo.git.checkout("-b", name)
    commit_files(repo, {"feature.txt": "one\n"}, "feature work")
    return repo


@pytest.mark.git_integration
class TestPushCurrentBranchIntegration:
    """push_current_branch against a real bare origin."""

    def test_new_branch_sets_upstream(self, origin_clone: Path) -> None:
        """A new branch is pushed and tracks origin/<branch>."""
        repo = _new_branch(origin_clone)

        result = push_current_branch(origin_clone)

        assert result["success"] is True, result
        assert result["returncode"] == 0
        assert repo.git.rev_parse("--abbrev-ref", "@{u}") == "origin/feature"
        assert repo.git.ls_remote("--heads", "origin", "refs/heads/feature")

    def test_tag_with_branch_name(self, origin_clone: Path) -> None:
        """A tag named like the branch does not make the push ambiguous."""
        repo = _new_branch(origin_clone)
        repo.git.tag("feature")

        result = push_current_branch(origin_clone)

        assert result["success"] is True, result
        head = repo.git.rev_parse("HEAD")
        remote = repo.git.ls_remote("origin", "refs/heads/feature").split()[0]
        assert remote == head

    def test_force_after_amend(self, origin_clone: Path) -> None:
        """An amended, already pushed branch can be force-pushed."""
        repo = _new_branch(origin_clone)
        assert push_current_branch(origin_clone)["success"] is True
        (origin_clone / "feature.txt").write_text("two\n")
        repo.git.add("-A")
        repo.git.commit("--amend", "--no-edit")

        assert push_current_branch(origin_clone)["success"] is False
        result = push_current_branch(origin_clone, force=True)

        assert result["success"] is True, result
        remote = repo.git.ls_remote("origin", "refs/heads/feature").split()[0]
        assert remote == repo.git.rev_parse("HEAD")

    @pytest.mark.parametrize("name", ["work", "second"])
    def test_force_refused_in_fresh_clone(
        self, make_clone: Callable[[str], Path], name: str
    ) -> None:
        """A fresh clone has no remote-tracking reflog, so force is refused."""
        clone_dir = make_clone(name)

        result = push_current_branch(clone_dir, force=True)

        assert result["success"] is False
        assert result["error"] is not None
        assert result["error"].startswith(
            "refs/remotes/origin/main has no reflog (fresh clone?)"
        )
        assert result["returncode"] is None
