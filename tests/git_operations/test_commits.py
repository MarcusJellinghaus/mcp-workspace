"""Minimal tests for git commit operations."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from git import Repo
from git.exc import GitCommandError

from mcp_workspace.git_operations.commits import (
    commit_staged_files,
    get_latest_commit_sha,
)
from mcp_workspace.git_operations.workflows import commit_all_changes


@pytest.mark.git_integration
class TestCommitOperations:
    """Minimal tests for commit operations - one test per function."""

    def test_commit_staged_files(self, git_repo: tuple[Repo, Path]) -> None:
        """Test commit_staged_files commits staged changes."""
        repo, project_dir = git_repo

        # Create and stage a file
        test_file = project_dir / "test.py"
        test_file.write_text("# Test file")
        repo.index.add(["test.py"])

        # Commit staged files
        result = commit_staged_files("Add test file", project_dir)

        assert result["success"] is True
        assert result["error"] is None
        assert result["error_category"] is None
        assert len(list(repo.iter_commits())) == 1

    def test_commit_all_changes(self, git_repo: tuple[Repo, Path]) -> None:
        """Test commit_all_changes stages and commits in one operation."""
        repo, project_dir = git_repo

        # Create a file (not staged)
        test_file = project_dir / "test.py"
        test_file.write_text("# Test file")

        # Commit all changes (should stage + commit)
        result = commit_all_changes("Add test file", project_dir)

        assert result["success"] is True
        assert result["error"] is None
        assert len(list(repo.iter_commits())) == 1

    def test_commit_all_changes_no_changes_returns_success(
        self, git_repo: tuple[Repo, Path]
    ) -> None:
        """Test commit_all_changes returns success when no changes to commit."""
        repo, project_dir = git_repo

        # Verify precondition: repo is clean
        assert not repo.is_dirty(untracked_files=True)

        result = commit_all_changes("Test message", project_dir)

        assert result["success"] is True
        assert result["commit_hash"] is None
        assert result["error"] is None

    def test_commit_with_multiline_message(self, git_repo: tuple[Repo, Path]) -> None:
        """Test commit handles multiline commit messages."""
        repo, project_dir = git_repo

        # Create file
        test_file = project_dir / "test.py"
        test_file.write_text("# Test file")

        # Commit with multiline message
        multiline_message = (
            "Add test file\n\nThis is a detailed description\nwith multiple lines"
        )
        result = commit_all_changes(multiline_message, project_dir)

        assert result["success"] is True
        commits = list(repo.iter_commits())
        assert commits[0].message.strip() == multiline_message


@pytest.mark.git_integration
class TestGetLatestCommitSha:
    """Tests for get_latest_commit_sha function."""

    def test_returns_sha_in_git_repo(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """Should return SHA string in a valid git repo."""
        _, project_dir = git_repo_with_commit

        sha = get_latest_commit_sha(project_dir)

        assert sha is not None
        assert len(sha) == 40  # Full SHA length
        assert all(c in "0123456789abcdef" for c in sha)

    def test_returns_none_outside_git_repo(self, tmp_path: Path) -> None:
        """Should return None when not in a git repository."""
        sha = get_latest_commit_sha(tmp_path)

        assert sha is None

    def test_sha_matches_repo_head(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """Should return the same SHA as the repo's HEAD."""
        repo, project_dir = git_repo_with_commit

        sha = get_latest_commit_sha(project_dir)
        expected_sha = repo.head.commit.hexsha

        assert sha == expected_sha


class TestCommitStagedFilesPorcelain:
    """Mock-based tests for porcelain invocation, classification, and validation."""

    def _build_mock_repo(self, hexsha: str = "a" * 40) -> MagicMock:
        """Create a MagicMock repo with sensible defaults for the porcelain path."""
        mock_repo = MagicMock()
        mock_repo.head.commit.hexsha = hexsha
        mock_repo.config_reader.return_value.get_value.return_value = "<unset>"
        return mock_repo

    def test_invokes_porcelain_without_no_gpg_sign(self, tmp_path: Path) -> None:
        """commit_staged_files calls repo.git.commit('-m', message) and not --no-gpg-sign."""
        mock_repo = self._build_mock_repo()
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_repo
        mock_ctx.__exit__.return_value = False

        with patch(
            "mcp_workspace.git_operations.commits.safe_repo_context",
            return_value=mock_ctx,
        ), patch(
            "mcp_workspace.git_operations.commits.is_git_repository",
            return_value=True,
        ), patch(
            "mcp_workspace.git_operations.commits.get_staged_changes",
            return_value=["some_file.py"],
        ):
            result = commit_staged_files("hello", tmp_path)

        assert mock_repo.git.commit.called
        assert mock_repo.git.commit.call_args.args == ("-m", "hello")
        for arg in mock_repo.git.commit.call_args.args:
            assert "--no-gpg-sign" not in str(arg)
        assert result["success"] is True
        assert result["error_category"] is None

    @pytest.mark.parametrize(
        "stderr,expected_category",
        [
            ("gpg: signing failed: secret key not available", "signing_failed"),
            ("pre-commit hook failed", "commit_failed"),
        ],
    )
    def test_classifies_error_category(
        self, tmp_path: Path, stderr: str, expected_category: str
    ) -> None:
        """GitCommandError stderr is classified into signing_failed vs commit_failed."""
        mock_repo = self._build_mock_repo()
        mock_repo.git.commit.side_effect = GitCommandError(
            ["git", "commit", "-m", "x"], 1, stderr=stderr
        )
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_repo
        mock_ctx.__exit__.return_value = False

        with patch(
            "mcp_workspace.git_operations.commits.safe_repo_context",
            return_value=mock_ctx,
        ), patch(
            "mcp_workspace.git_operations.commits.is_git_repository",
            return_value=True,
        ), patch(
            "mcp_workspace.git_operations.commits.get_staged_changes",
            return_value=["some_file.py"],
        ):
            result = commit_staged_files("hello", tmp_path)

        assert result["success"] is False
        assert result["error_category"] == expected_category
        assert result["error"] is not None
        assert stderr in result["error"]

    @pytest.mark.parametrize(
        "case",
        ["empty_message", "whitespace_message", "not_a_repo", "no_staged_files"],
    )
    def test_validation_failures_set_validation_failed(
        self, tmp_path: Path, case: str
    ) -> None:
        """All four pre-git validation paths return error_category='validation_failed'."""
        if case == "empty_message":
            result = commit_staged_files("", tmp_path)
        elif case == "whitespace_message":
            result = commit_staged_files("   \n\t", tmp_path)
        elif case == "not_a_repo":
            # tmp_path is not a git repo
            result = commit_staged_files("valid message", tmp_path)
        elif case == "no_staged_files":
            with patch(
                "mcp_workspace.git_operations.commits.is_git_repository",
                return_value=True,
            ), patch(
                "mcp_workspace.git_operations.commits.get_staged_changes",
                return_value=[],
            ):
                result = commit_staged_files("valid message", tmp_path)
        else:  # pragma: no cover - parametrize guarantees coverage
            raise AssertionError(f"unhandled case: {case}")

        assert result["success"] is False
        assert result["error_category"] == "validation_failed"
