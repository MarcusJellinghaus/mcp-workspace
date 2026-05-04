"""Integration tests for read-only git operations."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from git import Repo
from git.exc import GitCommandError

from mcp_workspace.git_operations.read_operations import (
    _run_simple_command,
    git,
    git_branch,
    git_diff,
    git_log,
    git_merge_base,
    git_show,
    git_status,
)


@pytest.mark.git_integration
class TestGitLog:
    """Tests for git_log()."""

    def test_basic_log_returns_commits(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        _, project_dir = git_repo_with_commit
        result = git_log(project_dir)
        assert "Initial commit" in result

    def test_log_with_oneline(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        _, project_dir = git_repo_with_commit
        result = git_log(project_dir, args=["--oneline"])
        # Oneline format: short hash + message on one line
        lines = result.strip().splitlines()
        assert len(lines) >= 1
        assert "Initial commit" in lines[0]

    def test_log_with_pathspec(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        repo, project_dir = git_repo_with_commit
        # Create a second file with its own commit
        (project_dir / "other.txt").write_text("other")
        repo.index.add(["other.txt"])
        repo.index.commit("Add other file")

        result = git_log(project_dir, pathspec=["README.md"])
        assert "Initial commit" in result
        assert "Add other file" not in result

    def test_log_search_filters_output(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        repo, project_dir = git_repo_with_commit
        (project_dir / "marker.txt").write_text("UNIQUE_MARKER")
        repo.index.add(["marker.txt"])
        repo.index.commit("Second commit with UNIQUE_MARKER")

        result = git_log(project_dir, search="UNIQUE_MARKER")
        assert "UNIQUE_MARKER" in result
        assert "Initial commit" not in result

    def test_log_max_lines_truncates(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        repo, project_dir = git_repo_with_commit
        # Create several commits to generate multi-line output
        for i in range(10):
            (project_dir / f"file_{i}.txt").write_text(f"content {i}")
            repo.index.add([f"file_{i}.txt"])
            repo.index.commit(f"Commit number {i}")

        result = git_log(project_dir, max_lines=3)
        assert "[truncated" in result

    def test_log_empty_repo_message(self, git_repo: tuple[Repo, Path]) -> None:
        _, project_dir = git_repo
        result = git_log(project_dir)
        assert result == "No commits found."

    def test_log_rejected_flag_raises(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        _, project_dir = git_repo_with_commit
        with pytest.raises(ValueError, match="not in the security allowlist"):
            git_log(project_dir, args=["--exec=evil"])

    def test_log_hardcodes_safety_flags(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        _, project_dir = git_repo_with_commit
        with patch(
            "mcp_workspace.git_operations.read_operations.safe_repo_context"
        ) as mock_ctx:
            mock_repo = MagicMock()
            mock_repo.git.log.return_value = "mocked"
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_repo)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            git_log(project_dir, args=["--oneline"])

            call_args = mock_repo.git.log.call_args[0]
            assert "--no-ext-diff" in call_args
            assert "--no-textconv" in call_args

    def test_log_reraises_non_empty_repo_git_error(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        _, project_dir = git_repo_with_commit
        with patch(
            "mcp_workspace.git_operations.read_operations.safe_repo_context"
        ) as mock_ctx:
            mock_repo = MagicMock()
            mock_repo.git.log.side_effect = GitCommandError(
                "git log", 128, stderr="fatal: bad revision 'nonexistent'"
            )
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_repo)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(GitCommandError):
                git_log(project_dir)


@pytest.mark.git_integration
class TestGitDiff:
    """Tests for git_diff()."""

    def test_basic_diff_returns_changes(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        _, project_dir = git_repo_with_commit
        (project_dir / "README.md").write_text("# Changed")
        result = git_diff(project_dir, compact=False)
        assert "Changed" in result

    def test_diff_staged(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        repo, project_dir = git_repo_with_commit
        (project_dir / "README.md").write_text("# Staged change")
        repo.index.add(["README.md"])
        result = git_diff(project_dir, args=["--staged"], compact=False)
        assert "Staged change" in result

    def test_diff_between_refs(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        repo, project_dir = git_repo_with_commit
        first_sha = repo.head.commit.hexsha
        (project_dir / "README.md").write_text("# Updated")
        repo.index.add(["README.md"])
        repo.index.commit("Update readme")

        result = git_diff(project_dir, args=[first_sha, "HEAD"], compact=False)
        assert "Updated" in result

    def test_diff_with_pathspec(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        _, project_dir = git_repo_with_commit
        (project_dir / "README.md").write_text("# Changed readme")
        (project_dir / "other.txt").write_text("other change")
        result = git_diff(project_dir, pathspec=["README.md"], compact=False)
        assert "Changed readme" in result
        assert "other change" not in result

    def test_diff_compact_default(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        _, project_dir = git_repo_with_commit
        (project_dir / "README.md").write_text("# Changed for compact")
        # compact=True is default
        result = git_diff(project_dir)
        assert "Changed for compact" in result

    def test_diff_compact_false_raw(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        _, project_dir = git_repo_with_commit
        (project_dir / "README.md").write_text("# Raw diff")
        result = git_diff(project_dir, compact=False)
        # Raw diff should contain standard diff markers
        assert "diff --git" in result

    def test_diff_search_filters(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        _, project_dir = git_repo_with_commit
        (project_dir / "README.md").write_text("# SEARCHABLE_TOKEN here")
        result = git_diff(project_dir, search="SEARCHABLE_TOKEN", compact=False)
        assert "SEARCHABLE_TOKEN" in result

    def test_diff_max_lines_truncates(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        _, project_dir = git_repo_with_commit
        # Create a large tracked change
        content = "\n".join(f"line {i}" for i in range(200))
        (project_dir / "README.md").write_text(content)
        result = git_diff(project_dir, max_lines=5, compact=False)
        assert "[truncated" in result

    def test_diff_no_changes_message(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        _, project_dir = git_repo_with_commit
        result = git_diff(project_dir)
        assert result == "No changes found"

    def test_diff_rejected_flag_raises(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        _, project_dir = git_repo_with_commit
        with pytest.raises(ValueError, match="not in the security allowlist"):
            git_diff(project_dir, args=["--output=evil"])

    def test_diff_hardcodes_safety_flags(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        _, project_dir = git_repo_with_commit
        with patch(
            "mcp_workspace.git_operations.read_operations.safe_repo_context"
        ) as mock_ctx:
            mock_repo = MagicMock()
            mock_repo.git.diff.return_value = ""
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_repo)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            git_diff(project_dir, compact=False)

            call_args = mock_repo.git.diff.call_args[0]
            assert "--no-ext-diff" in call_args
            assert "--no-textconv" in call_args


@pytest.mark.git_integration
class TestGitStatus:
    """Tests for git_status()."""

    def test_status_clean_repo(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        _, project_dir = git_repo_with_commit
        result = git_status(project_dir)
        # A clean repo should mention "nothing to commit" or similar
        assert "nothing to commit" in result or "clean" in result.lower()

    def test_status_with_changes(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        _, project_dir = git_repo_with_commit
        (project_dir / "new_file.txt").write_text("new content")
        result = git_status(project_dir)
        assert "new_file.txt" in result

    def test_status_short_flag(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        _, project_dir = git_repo_with_commit
        (project_dir / "new_file.txt").write_text("content")
        result = git_status(project_dir, args=["--short"])
        assert "new_file.txt" in result
        # Short format uses ?? for untracked
        assert "??" in result

    def test_status_max_lines_truncates(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        _, project_dir = git_repo_with_commit
        # Create many untracked files
        for i in range(50):
            (project_dir / f"file_{i}.txt").write_text(f"content {i}")
        result = git_status(project_dir, max_lines=3)
        assert "[truncated" in result

    def test_status_with_pathspec(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        _, project_dir = git_repo_with_commit
        with patch(
            "mcp_workspace.git_operations.read_operations.safe_repo_context"
        ) as mock_ctx:
            mock_repo = MagicMock()
            mock_repo.git.status.return_value = "mocked status"
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_repo)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            result = git_status(project_dir, pathspec=["src/"])

            call_args = mock_repo.git.status.call_args[0]
            assert "--" in call_args
            assert "src/" in call_args
            assert result == "mocked status"

    def test_status_rejected_flag_raises(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        _, project_dir = git_repo_with_commit
        with pytest.raises(ValueError, match="not in the security allowlist"):
            git_status(project_dir, args=["--exec=evil"])


@pytest.mark.git_integration
class TestGitMergeBase:
    """Tests for git_merge_base()."""

    def test_merge_base_two_branches(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        repo, project_dir = git_repo_with_commit
        # Rename to main for consistency
        repo.git.branch("-M", "main")
        # Create a feature branch with a new commit
        repo.git.checkout("-b", "feature")
        (project_dir / "feature.txt").write_text("feature")
        repo.index.add(["feature.txt"])
        repo.index.commit("Feature commit")
        repo.git.checkout("main")

        result = git_merge_base(project_dir, args=["main", "feature"])
        # Should return the initial commit SHA
        assert len(result.strip()) >= 7

    def test_merge_base_is_ancestor(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        repo, project_dir = git_repo_with_commit
        repo.git.branch("-M", "main")
        initial_sha = repo.head.commit.hexsha
        (project_dir / "second.txt").write_text("second")
        repo.index.add(["second.txt"])
        repo.index.commit("Second commit")

        result = git_merge_base(
            project_dir, args=["--is-ancestor", initial_sha, "HEAD"]
        )
        assert result == "true"

    def test_merge_base_not_ancestor(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        repo, project_dir = git_repo_with_commit
        repo.git.branch("-M", "main")
        (project_dir / "second.txt").write_text("second")
        repo.index.add(["second.txt"])
        repo.index.commit("Second commit")
        head_sha = repo.head.commit.hexsha

        # HEAD is not an ancestor of the initial commit
        initial_sha = repo.head.commit.parents[0].hexsha
        result = git_merge_base(
            project_dir, args=["--is-ancestor", head_sha, initial_sha]
        )
        assert result == "false"

    def test_merge_base_rejected_flag_raises(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        _, project_dir = git_repo_with_commit
        with pytest.raises(ValueError, match="not in the security allowlist"):
            git_merge_base(project_dir, args=["--exec=evil"])


class TestRunSimpleCommand:
    """Unit tests for _run_simple_command() with mocked repo."""

    def _make_mock_context(self) -> tuple[MagicMock, MagicMock]:
        mock_repo = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_repo)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
        return mock_ctx, mock_repo

    @patch("mcp_workspace.git_operations.read_operations.validate_args")
    @patch("mcp_workspace.git_operations.read_operations.safe_repo_context")
    def test_validates_args(
        self, mock_ctx: MagicMock, mock_validate: MagicMock, tmp_path: Path
    ) -> None:
        mock_ctx_obj, mock_repo = self._make_mock_context()
        mock_ctx.side_effect = mock_ctx_obj.side_effect
        mock_ctx.return_value = mock_ctx_obj.return_value
        mock_repo.git.fetch.return_value = "ok"

        _run_simple_command(
            git_method="fetch",
            project_dir=tmp_path,
            command="fetch",
            args=["--all"],
            pathspec=None,
            max_lines=100,
        )
        mock_validate.assert_called_once_with("fetch", ["--all"])

    @patch("mcp_workspace.git_operations.read_operations.safe_repo_context")
    def test_appends_pathspec(self, mock_ctx: MagicMock, tmp_path: Path) -> None:
        mock_ctx_obj, mock_repo = self._make_mock_context()
        mock_ctx.return_value = mock_ctx_obj.return_value
        mock_repo.git.ls_files.return_value = "file.txt"

        _run_simple_command(
            git_method="ls_files",
            project_dir=tmp_path,
            command="ls_files",
            args=["--cached"],
            pathspec=["src/"],
            max_lines=100,
        )
        call_args = mock_repo.git.ls_files.call_args[0]
        assert "--" in call_args
        assert "src/" in call_args

    @patch("mcp_workspace.git_operations.read_operations.safe_repo_context")
    def test_truncates_output(self, mock_ctx: MagicMock, tmp_path: Path) -> None:
        mock_ctx_obj, mock_repo = self._make_mock_context()
        mock_ctx.return_value = mock_ctx_obj.return_value
        mock_repo.git.ls_files.return_value = "\n".join(f"file_{i}" for i in range(200))

        result = _run_simple_command(
            git_method="ls_files",
            project_dir=tmp_path,
            command="ls_files",
            args=["--cached"],
            pathspec=None,
            max_lines=5,
        )
        assert "[truncated" in result

    @patch("mcp_workspace.git_operations.read_operations.safe_repo_context")
    def test_no_output_message(self, mock_ctx: MagicMock, tmp_path: Path) -> None:
        mock_ctx_obj, mock_repo = self._make_mock_context()
        mock_ctx.return_value = mock_ctx_obj.return_value
        mock_repo.git.fetch.return_value = ""

        result = _run_simple_command(
            git_method="fetch",
            project_dir=tmp_path,
            command="fetch",
            args=["--all"],
            pathspec=None,
            max_lines=100,
            no_output_message="Nothing fetched.",
        )
        assert result == "Nothing fetched."

    @patch("mcp_workspace.git_operations.read_operations.safe_repo_context")
    def test_includes_safety_flags(self, mock_ctx: MagicMock, tmp_path: Path) -> None:
        mock_ctx_obj, mock_repo = self._make_mock_context()
        mock_ctx.return_value = mock_ctx_obj.return_value
        mock_repo.git.ls_tree.return_value = "blob"

        _run_simple_command(
            git_method="ls_tree",
            project_dir=tmp_path,
            command="ls_tree",
            args=["HEAD"],
            pathspec=None,
            max_lines=100,
            use_safety_flags=True,
        )
        call_args = mock_repo.git.ls_tree.call_args[0]
        assert "--no-ext-diff" in call_args
        assert "--no-textconv" in call_args

    @patch("mcp_workspace.git_operations.read_operations.safe_repo_context")
    def test_no_safety_flags(self, mock_ctx: MagicMock, tmp_path: Path) -> None:
        mock_ctx_obj, mock_repo = self._make_mock_context()
        mock_ctx.return_value = mock_ctx_obj.return_value
        mock_repo.git.rev_parse.return_value = "abc123"

        _run_simple_command(
            git_method="rev_parse",
            project_dir=tmp_path,
            command="rev_parse",
            args=["HEAD"],
            pathspec=None,
            max_lines=100,
            use_safety_flags=False,
        )
        call_args = mock_repo.git.rev_parse.call_args[0]
        assert "--no-ext-diff" not in call_args
        assert "--no-textconv" not in call_args


@pytest.mark.git_integration
class TestGitShow:
    """Tests for git_show()."""

    def test_show_head_commit(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        _, project_dir = git_repo_with_commit
        result = git_show(project_dir, args=["HEAD"])
        # Compact rendering may strip commit message; check for diff content
        assert "README.md" in result

    def test_show_compact_default(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        _, project_dir = git_repo_with_commit
        # compact=True is default — should apply compact rendering
        result = git_show(project_dir, args=["HEAD"])
        assert "diff --git" in result

    def test_show_colon_skips_compact(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        _, project_dir = git_repo_with_commit
        result = git_show(project_dir, args=["HEAD:README.md"])
        # Should return file content directly, not compact diff
        assert "# Test Project" in result

    def test_show_search_filters(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        repo, project_dir = git_repo_with_commit
        (project_dir / "marker.txt").write_text("SHOW_MARKER_TOKEN")
        repo.index.add(["marker.txt"])
        repo.index.commit("Commit with SHOW_MARKER_TOKEN")

        result = git_show(project_dir, args=["HEAD"], search="SHOW_MARKER_TOKEN")
        assert "SHOW_MARKER_TOKEN" in result

    def test_show_rejected_flag_raises(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        _, project_dir = git_repo_with_commit
        with pytest.raises(ValueError, match="not in the security allowlist"):
            git_show(project_dir, args=["--exec=evil"])


@pytest.mark.git_integration
class TestGitBranch:
    """Tests for git_branch()."""

    def test_branch_list(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        _, project_dir = git_repo_with_commit
        result = git_branch(project_dir, args=["--list"])
        assert "master" in result or "main" in result or result.strip()

    def test_branch_all(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        _, project_dir = git_repo_with_commit
        result = git_branch(project_dir, args=["-a"])
        assert result.strip()

    def test_branch_show_current(self, git_repo_with_commit: tuple[Repo, Path]) -> None:
        _, project_dir = git_repo_with_commit
        result = git_branch(project_dir, args=["--show-current"])
        assert result.strip()

    def test_branch_bare_rejected(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        _, project_dir = git_repo_with_commit
        with pytest.raises(ValueError, match="requires a read-only flag"):
            git_branch(project_dir, args=[])

    def test_branch_no_read_flag_rejected(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        _, project_dir = git_repo_with_commit
        with pytest.raises(ValueError, match="requires a read-only flag"):
            git_branch(project_dir, args=["new-branch-name"])

    def test_branch_rejected_flag_raises(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        _, project_dir = git_repo_with_commit
        with pytest.raises(ValueError, match="not in the security allowlist"):
            git_branch(project_dir, args=["--delete", "some-branch"])


class TestGitDispatcher:
    """Unit tests for the unified git() dispatcher (mocked implementations)."""

    @patch("mcp_workspace.git_operations.read_operations.git_log")
    def test_routes_to_log(self, mock_log: MagicMock, tmp_path: Path) -> None:
        mock_log.return_value = "log output"
        result = git(
            command="log",
            project_dir=tmp_path,
            args=["--oneline"],
            pathspec=["src/"],
            search="fix",
            max_lines=25,
        )
        mock_log.assert_called_once_with(tmp_path, ["--oneline"], ["src/"], "fix", 25)
        assert result == "log output"

    @patch("mcp_workspace.git_operations.read_operations.git_diff")
    def test_routes_to_diff(self, mock_diff: MagicMock, tmp_path: Path) -> None:
        mock_diff.return_value = "diff output"
        result = git(
            command="diff",
            project_dir=tmp_path,
            args=["--staged"],
            pathspec=["file.py"],
            search="pattern",
            context=5,
            max_lines=50,
            compact=False,
        )
        mock_diff.assert_called_once_with(
            tmp_path, ["--staged"], ["file.py"], "pattern", 5, 50, False
        )
        assert result == "diff output"

    @patch("mcp_workspace.git_operations.read_operations.git_status")
    def test_routes_to_status(self, mock_status: MagicMock, tmp_path: Path) -> None:
        mock_status.return_value = "status output"
        result = git(
            command="status",
            project_dir=tmp_path,
            args=["--short"],
            pathspec=["src/"],
        )
        mock_status.assert_called_once_with(tmp_path, ["--short"], 200, ["src/"])
        assert result == "status output"

    @patch("mcp_workspace.git_operations.read_operations.git_merge_base")
    def test_routes_to_merge_base(self, mock_mb: MagicMock, tmp_path: Path) -> None:
        mock_mb.return_value = "abc123"
        result = git(
            command="merge_base", project_dir=tmp_path, args=["main", "feature"]
        )
        mock_mb.assert_called_once_with(tmp_path, ["main", "feature"])
        assert result == "abc123"

    @patch("mcp_workspace.git_operations.read_operations.git_show")
    def test_routes_to_show(self, mock_show: MagicMock, tmp_path: Path) -> None:
        mock_show.return_value = "show output"
        result = git(
            command="show",
            project_dir=tmp_path,
            args=["HEAD"],
            pathspec=["file.py"],
            search="token",
            context=2,
            max_lines=80,
            compact=False,
        )
        mock_show.assert_called_once_with(
            tmp_path, ["HEAD"], ["file.py"], "token", 2, 80, False
        )
        assert result == "show output"

    @patch("mcp_workspace.git_operations.read_operations.git_branch")
    def test_routes_to_branch(self, mock_branch: MagicMock, tmp_path: Path) -> None:
        mock_branch.return_value = "branch output"
        result = git(command="branch", project_dir=tmp_path, args=["--list"])
        mock_branch.assert_called_once_with(tmp_path, ["--list"], 100)
        assert result == "branch output"

    @patch("mcp_workspace.git_operations.read_operations._run_simple_command")
    def test_routes_to_fetch(self, mock_simple: MagicMock, tmp_path: Path) -> None:
        mock_simple.return_value = "fetch done"
        result = git(command="fetch", project_dir=tmp_path, args=["--all"])
        mock_simple.assert_called_once_with(
            "fetch",
            tmp_path,
            "fetch",
            ["--all"],
            None,
            100,
            "Fetch complete (no output).",
            use_safety_flags=False,
        )
        assert result == "fetch done"

    def test_unknown_command_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Unknown git command: 'push'"):
            git(command="push", project_dir=tmp_path)

    @patch("mcp_workspace.git_operations.read_operations.git_log")
    def test_default_max_lines_log(self, mock_log: MagicMock, tmp_path: Path) -> None:
        mock_log.return_value = ""
        git(command="log", project_dir=tmp_path)
        assert mock_log.call_args[0][4] == 50  # max_lines positional arg

    @patch("mcp_workspace.git_operations.read_operations.git_diff")
    def test_default_max_lines_diff(self, mock_diff: MagicMock, tmp_path: Path) -> None:
        mock_diff.return_value = ""
        git(command="diff", project_dir=tmp_path)
        assert mock_diff.call_args[0][5] == 100  # max_lines positional arg

    @patch("mcp_workspace.git_operations.read_operations.git_status")
    def test_default_max_lines_status(
        self, mock_status: MagicMock, tmp_path: Path
    ) -> None:
        mock_status.return_value = ""
        git(command="status", project_dir=tmp_path)
        assert mock_status.call_args[0][2] == 200  # max_lines positional arg

    @patch("mcp_workspace.git_operations.read_operations._run_simple_command")
    def test_default_max_lines_other(
        self, mock_simple: MagicMock, tmp_path: Path
    ) -> None:
        mock_simple.return_value = ""
        git(command="fetch", project_dir=tmp_path)
        # max_lines should be 100 (default for commands not in _DEFAULT_MAX_LINES)
        assert mock_simple.call_args[0][5] == 100

    @patch("mcp_workspace.git_operations.read_operations.git_log")
    def test_explicit_max_lines_overrides(
        self, mock_log: MagicMock, tmp_path: Path
    ) -> None:
        mock_log.return_value = ""
        git(command="log", project_dir=tmp_path, max_lines=25)
        assert mock_log.call_args[0][4] == 25

    @patch("mcp_workspace.git_operations.read_operations.git_status")
    def test_soft_warning_search_on_status(
        self, mock_status: MagicMock, tmp_path: Path
    ) -> None:
        mock_status.return_value = "status output"
        result = git(command="status", project_dir=tmp_path, search="pattern")
        assert "⚠" in result
        assert "'search'" in result
        assert "status output" in result

    @patch("mcp_workspace.git_operations.read_operations.git_log")
    def test_soft_warning_compact_on_log(
        self, mock_log: MagicMock, tmp_path: Path
    ) -> None:
        mock_log.return_value = "log output"
        result = git(command="log", project_dir=tmp_path, compact=False)
        assert "⚠" in result
        assert "'compact'" in result
        assert "log output" in result

    @patch("mcp_workspace.git_operations.read_operations._run_simple_command")
    def test_soft_warning_pathspec_on_fetch(
        self, mock_simple: MagicMock, tmp_path: Path
    ) -> None:
        mock_simple.return_value = "fetch output"
        result = git(command="fetch", project_dir=tmp_path, pathspec=["src/"])
        assert "⚠" in result
        assert "'pathspec'" in result
        assert "fetch output" in result

    @patch("mcp_workspace.git_operations.read_operations.git_log")
    def test_no_warning_for_defaults(self, mock_log: MagicMock, tmp_path: Path) -> None:
        mock_log.return_value = "log output"
        # compact=True is the default, should NOT warn even though log doesn't support compact
        result = git(command="log", project_dir=tmp_path, compact=True)
        assert "⚠" not in result

    @patch("mcp_workspace.git_operations.read_operations.git_status")
    def test_no_warning_context_default_on_status(
        self, mock_status: MagicMock, tmp_path: Path
    ) -> None:
        mock_status.return_value = "status output"
        # context=3 is the default, should NOT warn
        result = git(command="status", project_dir=tmp_path, context=3)
        assert "⚠" not in result

    @patch("mcp_workspace.git_operations.read_operations.git_diff")
    def test_no_warning_for_supported_params(
        self, mock_diff: MagicMock, tmp_path: Path
    ) -> None:
        mock_diff.return_value = "diff output"
        # search is supported for diff, should NOT warn
        result = git(command="diff", project_dir=tmp_path, search="pattern")
        assert "⚠" not in result
