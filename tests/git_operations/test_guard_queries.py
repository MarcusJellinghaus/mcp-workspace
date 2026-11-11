"""Tests for the guardrail queries used by the git write tools."""

from collections.abc import Callable
from pathlib import Path

import pytest
from git import GitCommandError, Repo

from mcp_workspace.git_operations.branch_queries import (
    is_ancestor,
    is_valid_branch_name_strict,
    resolve_base_ref,
    resolve_commit,
)
from mcp_workspace.git_operations.rebase import operation_in_progress

from .conftest import FileChanges, commit_files

UNKNOWN_SHA = "0123456789abcdef0123456789abcdef01234567"

ConflictBuilder = Callable[[FileChanges, FileChanges, FileChanges], tuple[Repo, Path]]


def _build_conflict(make_conflict_repo: ConflictBuilder) -> tuple[Repo, Path]:
    """Diverge ``main`` and ``feature`` on the same line of ``f.txt``."""
    return make_conflict_repo(
        {"f.txt": "base\n"}, {"f.txt": "main\n"}, {"f.txt": "feature\n"}
    )


@pytest.mark.git_integration
class TestIsValidBranchNameStrict:
    """is_valid_branch_name_strict against a real repository."""

    @pytest.mark.parametrize("name", ["feature/x", "220-foo"])
    def test_accepts(self, git_repo_with_commit: tuple[Repo, Path], name: str) -> None:
        """Ordinary branch names are valid."""
        _, project_dir = git_repo_with_commit

        assert is_valid_branch_name_strict(project_dir, name) is True

    @pytest.mark.parametrize(
        "name", ["", "HEAD", "-x", "a..b", "x.lock", "a@{b", "a b", "x~1"]
    )
    def test_rejects(self, git_repo_with_commit: tuple[Repo, Path], name: str) -> None:
        """Names git refuses, or that are HEAD or option-like, are invalid."""
        _, project_dir = git_repo_with_commit

        assert is_valid_branch_name_strict(project_dir, name) is False

    def test_rejects_previous_branch_shorthand(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """``@{-1}`` is rejected even when git can expand it."""
        repo, project_dir = git_repo_with_commit
        repo.git.checkout("-b", "other")
        repo.git.checkout("-")

        assert is_valid_branch_name_strict(project_dir, "@{-1}") is False


@pytest.mark.git_integration
class TestResolveBaseRef:
    """resolve_base_ref against a real clone."""

    def test_local_branch(self, origin_clone: Path) -> None:
        """A local branch resolves to refs/heads."""
        assert resolve_base_ref(origin_clone, "main") == "refs/heads/main"

    def test_remote_branch(self, origin_clone: Path) -> None:
        """``origin/<b>`` resolves to refs/remotes."""
        assert resolve_base_ref(origin_clone, "origin/main") == (
            "refs/remotes/origin/main"
        )

    def test_tag_is_not_a_base(self, origin_clone: Path) -> None:
        """A tag never resolves."""
        Repo(origin_clone).git.tag("v1")

        assert resolve_base_ref(origin_clone, "v1") is None

    def test_local_branch_named_like_remote(self, origin_clone: Path) -> None:
        """A local ``origin/x`` does not stand in for a missing remote branch."""
        Repo(origin_clone).git.branch("origin/x")

        assert resolve_base_ref(origin_clone, "origin/x") is None

    def test_unknown(self, origin_clone: Path) -> None:
        """An unknown branch resolves to None."""
        assert resolve_base_ref(origin_clone, "no-such-branch") is None


@pytest.mark.git_integration
class TestResolveCommit:
    """resolve_commit against a real repository."""

    def test_head(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """HEAD resolves to its full SHA."""
        repo, project_dir = git_repo_with_commit

        result = resolve_commit(project_dir, "HEAD")

        assert result == repo.git.rev_parse("HEAD")
        assert result is not None and len(result) == 40

    def test_unknown(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """An unknown ref resolves to None."""
        _, project_dir = git_repo_with_commit

        assert resolve_commit(project_dir, "no-such-ref") is None


@pytest.mark.git_integration
class TestIsAncestor:
    """is_ancestor against a real repository."""

    def test_parent_and_child(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """A parent is an ancestor of its child, not the other way round."""
        repo, project_dir = git_repo_with_commit
        parent = repo.git.rev_parse("HEAD")
        child = commit_files(repo, {"child.txt": "child\n"}, "child")

        assert is_ancestor(project_dir, parent, child) is True
        assert is_ancestor(project_dir, child, parent) is False

    def test_unknown_sha(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """A missing object cannot be decided."""
        _, project_dir = git_repo_with_commit

        assert is_ancestor(project_dir, UNKNOWN_SHA, "HEAD") is None


@pytest.mark.git_integration
class TestOperationInProgress:
    """operation_in_progress against real repositories."""

    def test_clean(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        """A clean repository has no operation in progress."""
        _, project_dir = git_repo_with_commit

        assert operation_in_progress(project_dir) is None

    def test_stopped_rebase(self, make_conflict_repo: ConflictBuilder) -> None:
        """A rebase stopped on a conflict is reported."""
        repo, project_dir = _build_conflict(make_conflict_repo)
        with pytest.raises(GitCommandError):
            repo.git.rebase("main")

        assert operation_in_progress(project_dir) == "rebase"

    def test_stopped_merge(self, make_conflict_repo: ConflictBuilder) -> None:
        """A merge stopped on a conflict is reported."""
        repo, project_dir = _build_conflict(make_conflict_repo)
        with pytest.raises(GitCommandError):
            repo.git.merge("main")

        assert operation_in_progress(project_dir) == "merge"


def test_operation_in_progress_non_repository(tmp_path: Path) -> None:
    """A directory that is not a repository raises ValueError."""
    with pytest.raises(ValueError, match="Not a git repository"):
        operation_in_progress(tmp_path)
