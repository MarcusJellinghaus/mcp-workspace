"""Unit tests for IssueManager core CRUD operations with mocked dependencies."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import git
import pytest
from github.GithubException import GithubException

from mcp_workspace.github_operations.issues import IssueManager


@pytest.mark.git_integration
class TestIssueManagerCore:
    """Unit tests for IssueManager core CRUD operations with mocked dependencies."""

    def test_initialization_requires_project_dir(self) -> None:
        """Test that None project_dir raises ValueError."""
        with pytest.raises(
            ValueError, match="Exactly one of project_dir or repo_url must be provided"
        ):
            IssueManager(None)

    def test_initialization_requires_git_repository(self, tmp_path: Path) -> None:
        """Test that non-git directory raises ValueError."""
        regular_dir = tmp_path / "regular_dir"
        regular_dir.mkdir()

        with pytest.raises(ValueError, match="Directory is not a git repository"):
            IssueManager(regular_dir)

    def test_initialization_requires_github_token(self, tmp_path: Path) -> None:
        """Test that missing GitHub token raises ValueError."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value=None,
        ):
            with pytest.raises(ValueError, match="GitHub token not found"):
                IssueManager(git_dir)

    def test_get_issue_success(self, mock_issue_manager: IssueManager) -> None:
        """Test successful issue retrieval."""
        issue_number = 1
        mock_issue = MagicMock()
        mock_issue.number = issue_number
        mock_issue.title = "Test Issue"
        mock_issue.body = "Test body"
        mock_issue.state = "open"
        mock_issue.labels = []
        mock_issue.created_at = datetime(2023, 1, 1)
        mock_issue.updated_at = datetime(2023, 1, 2)

        mock_issue_manager._repository.get_issue.return_value = mock_issue

        result = mock_issue_manager.get_issue(issue_number)

        assert result is not None
        assert result["number"] == issue_number
        mock_issue_manager._repository.get_issue.assert_called_once_with(issue_number)

    def test_create_issue_success(self, mock_issue_manager: IssueManager) -> None:
        """Test successful issue creation."""
        title = "Test Issue"
        body = "Test body"
        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.title = title
        mock_issue.body = body

        mock_issue_manager._repository.create_issue.return_value = mock_issue

        result = mock_issue_manager.create_issue(title, body)

        assert result["number"] == 1
        assert result["title"] == title
        mock_issue_manager._repository.create_issue.assert_called_once_with(
            title=title, body=body
        )

    def test_create_issue_with_labels(self, mock_issue_manager: IssueManager) -> None:
        """Test issue creation with labels."""
        title = "Test Issue"
        body = "Test body"
        labels = ["bug", "enhancement"]
        mock_issue = MagicMock()
        mock_issue.number = 1

        mock_issue_manager._repository.create_issue.return_value = mock_issue

        result = mock_issue_manager.create_issue(title, body, labels=labels)

        assert result["number"] == 1
        mock_issue_manager._repository.create_issue.assert_called_once_with(
            title=title, body=body, labels=labels
        )

    def test_create_issue_empty_title(self, mock_issue_manager: IssueManager) -> None:
        """Test that empty title raises ValueError."""
        with pytest.raises(ValueError, match="Issue title cannot be empty"):
            mock_issue_manager.create_issue("", "body")

    def test_close_issue_success(self, mock_issue_manager: IssueManager) -> None:
        """Test successful issue closing."""
        issue_number = 1
        mock_issue = MagicMock()
        mock_issue.number = issue_number

        mock_issue_manager._repository.get_issue.return_value = mock_issue

        mock_issue_manager.close_issue(issue_number)

        mock_issue.edit.assert_called_once_with(state="closed")

    def test_close_issue_invalid_number(self, mock_issue_manager: IssueManager) -> None:
        """Test closing issue with invalid number."""
        with pytest.raises(ValueError, match="Issue number must be a positive integer"):
            mock_issue_manager.close_issue(0)

    def test_reopen_issue_success(self, mock_issue_manager: IssueManager) -> None:
        """Test successful issue reopening."""
        issue_number = 1
        mock_issue = MagicMock()
        mock_issue.number = issue_number

        mock_issue_manager._repository.get_issue.return_value = mock_issue

        mock_issue_manager.reopen_issue(issue_number)

        mock_issue.edit.assert_called_once_with(state="open")

    def test_reopen_issue_invalid_number(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test reopening issue with invalid number."""
        with pytest.raises(ValueError, match="Issue number must be a positive integer"):
            mock_issue_manager.reopen_issue(0)

    def test_create_issue_auth_error_raises(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test that authentication errors are raised."""
        mock_issue_manager._repository.create_issue.side_effect = GithubException(
            401, {"message": "Bad credentials"}, None
        )

        with pytest.raises(GithubException):
            mock_issue_manager.create_issue("Title", "Body")

    def test_close_issue_auth_error_raises(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test that authentication errors are raised when closing."""
        mock_issue_manager._repository.get_issue.side_effect = GithubException(
            401, {"message": "Bad credentials"}, None
        )

        with pytest.raises(GithubException):
            mock_issue_manager.close_issue(1)

    def test_reopen_issue_auth_error_raises(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test that authentication errors are raised when reopening."""
        mock_issue_manager._repository.get_issue.side_effect = GithubException(
            401, {"message": "Bad credentials"}, None
        )

        with pytest.raises(GithubException):
            mock_issue_manager.reopen_issue(1)

    def test_get_available_labels_success(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test successful label retrieval."""
        mock_label1 = MagicMock()
        mock_label1.name = "bug"
        mock_label2 = MagicMock()
        mock_label2.name = "enhancement"

        mock_issue_manager._repository.get_labels.return_value = [
            mock_label1,
            mock_label2,
        ]

        result = mock_issue_manager.get_available_labels()

        assert len(result) == 2
        assert result[0]["name"] == "bug"
        assert result[1]["name"] == "enhancement"

    def test_get_available_labels_auth_error_raises(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test that authentication errors are raised when getting labels."""
        mock_issue_manager._repository.get_labels.side_effect = GithubException(
            401, {"message": "Bad credentials"}, None
        )

        with pytest.raises(GithubException):
            mock_issue_manager.get_available_labels()

    def test_list_issues_default_parameters(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test listing issues with default parameters."""
        mock_issue1 = MagicMock()
        mock_issue1.number = 1
        mock_issue1.pull_request = None
        mock_issue1.body = ""
        mock_issue2 = MagicMock()
        mock_issue2.number = 2
        mock_issue2.pull_request = None
        mock_issue2.body = ""

        mock_issue_manager._repository.get_issues.return_value = [
            mock_issue1,
            mock_issue2,
        ]

        result = mock_issue_manager.list_issues()

        assert len(result) == 2
        mock_issue_manager._repository.get_issues.assert_called_once_with(state="open")

    def test_list_issues_open_only(self, mock_issue_manager: IssueManager) -> None:
        """Test listing only open issues."""
        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.pull_request = None
        mock_issue.body = ""

        mock_issue_manager._repository.get_issues.return_value = [mock_issue]

        result = mock_issue_manager.list_issues(state="open")

        assert len(result) == 1
        mock_issue_manager._repository.get_issues.assert_called_once_with(state="open")

    def test_list_issues_include_pull_requests(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test that pull requests are filtered out by default."""
        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.pull_request = None
        mock_issue.body = ""
        mock_pr = MagicMock()
        mock_pr.number = 2
        mock_pr.pull_request = MagicMock()  # Has pull_request attribute
        mock_pr.body = ""

        mock_issue_manager._repository.get_issues.return_value = [mock_issue, mock_pr]

        result = mock_issue_manager.list_issues()

        assert len(result) == 1
        assert result[0]["number"] == 1

    def test_list_issues_pagination_handled(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test that pagination is properly handled."""
        # Create mock issues
        mock_issues = [MagicMock() for _ in range(50)]
        for i, issue in enumerate(mock_issues):
            issue.number = i + 1
            issue.pull_request = None
            issue.body = ""

        mock_issue_manager._repository.get_issues.return_value = mock_issues

        result = mock_issue_manager.list_issues()

        assert len(result) == 50

    def test_list_issues_empty_repository(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test listing issues from empty repository."""
        mock_issue_manager._repository.get_issues.return_value = []

        result = mock_issue_manager.list_issues()

        assert len(result) == 0

    def test_list_issues_github_error_handling(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test that GitHub errors are properly raised."""
        mock_issue_manager._repository.get_issues.side_effect = GithubException(
            403, {"message": "API rate limit exceeded"}, None
        )

        with pytest.raises(GithubException):
            mock_issue_manager.list_issues()

    def test_list_issues_with_since_parameter(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test listing issues with since parameter."""
        since_date = datetime(2023, 1, 1)
        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.pull_request = None
        mock_issue.body = ""

        mock_issue_manager._repository.get_issues.return_value = [mock_issue]

        result = mock_issue_manager.list_issues(since=since_date)

        assert len(result) == 1
        mock_issue_manager._repository.get_issues.assert_called_once_with(
            state="open", since=since_date
        )

    def test_list_issues_since_filters_pull_requests(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test that PRs are filtered when using since parameter."""
        since_date = datetime(2023, 1, 1)
        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.pull_request = None
        mock_issue.body = ""
        mock_pr = MagicMock()
        mock_pr.number = 2
        mock_pr.pull_request = MagicMock()
        mock_pr.body = ""

        mock_issue_manager._repository.get_issues.return_value = [mock_issue, mock_pr]

        result = mock_issue_manager.list_issues(since=since_date)

        assert len(result) == 1
        assert result[0]["number"] == 1

    def test_list_issues_without_since_unchanged(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test that behavior without since parameter is unchanged."""
        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.pull_request = None
        mock_issue.body = ""

        mock_issue_manager._repository.get_issues.return_value = [mock_issue]

        result = mock_issue_manager.list_issues()

        assert len(result) == 1
        mock_issue_manager._repository.get_issues.assert_called_once_with(state="open")

    def test_list_issues_since_pagination(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test pagination works with since parameter."""
        since_date = datetime(2023, 1, 1)
        mock_issues = [MagicMock() for _ in range(50)]
        for i, issue in enumerate(mock_issues):
            issue.number = i + 1
            issue.pull_request = None
            issue.body = ""

        mock_issue_manager._repository.get_issues.return_value = mock_issues

        result = mock_issue_manager.list_issues(since=since_date)

        assert len(result) == 50

    def test_get_issue_with_base_branch(self, mock_issue_manager: IssueManager) -> None:
        """Test getting issue with base_branch in body."""
        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.title = "Test"
        mock_issue.body = "Some text\n**Base Branch:** `main`\nMore text"

        mock_issue_manager._repository.get_issue.return_value = mock_issue

        result = mock_issue_manager.get_issue(1)

        assert result["number"] == 1

    def test_get_issue_without_base_branch(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test getting issue without base_branch in body."""
        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.title = "Test"
        mock_issue.body = "Some text without base branch"

        mock_issue_manager._repository.get_issue.return_value = mock_issue

        result = mock_issue_manager.get_issue(1)

        assert result["number"] == 1

    def test_get_issue_with_malformed_base_branch_logs_warning(
        self, mock_issue_manager: IssueManager, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that malformed base branch logs warning."""
        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.title = "Test"
        mock_issue.body = "**Base Branch:** malformed\nMore text"

        mock_issue_manager._repository.get_issue.return_value = mock_issue

        result = mock_issue_manager.get_issue(1)

        assert result["number"] == 1

    def test_list_issues_includes_base_branch(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test that listed issues include base_branch data."""
        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.body = "**Base Branch:** `main`"
        mock_issue.pull_request = None

        mock_issue_manager._repository.get_issues.return_value = [mock_issue]

        result = mock_issue_manager.list_issues()

        assert len(result) == 1

    def test_list_issues_with_malformed_base_branch_logs_warning(
        self, mock_issue_manager: IssueManager, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that malformed base branch in list logs warning."""
        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.body = "**Base Branch:** malformed"
        mock_issue.pull_request = None

        mock_issue_manager._repository.get_issues.return_value = [mock_issue]

        result = mock_issue_manager.list_issues()

        assert len(result) == 1

    def test_list_issues_no_error_handling_server_error_raises(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test that _list_issues_no_error_handling raises on server errors."""
        mock_issue_manager._repository.get_issues.side_effect = GithubException(
            500, {"message": "Internal Server Error"}, None
        )

        with pytest.raises(GithubException):
            mock_issue_manager._list_issues_no_error_handling()

    def test_list_issues_no_error_handling_network_error_raises(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test that _list_issues_no_error_handling raises on network errors."""
        mock_issue_manager._repository.get_issues.side_effect = ConnectionError(
            "Connection refused"
        )

        with pytest.raises(ConnectionError):
            mock_issue_manager._list_issues_no_error_handling()

    def test_list_issues_still_returns_empty_on_error(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Test that list_issues() returns [] on server error (existing behavior)."""
        mock_issue_manager._repository.get_issues.side_effect = GithubException(
            500, {"message": "Internal Server Error"}, None
        )

        result = mock_issue_manager.list_issues()

        assert result == []

    def test_list_issues_no_error_handling_raises_when_repo_is_none(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """_list_issues_no_error_handling() must raise (not return []) when
        the repository cannot be resolved, so the cache snapshot/restore path
        sees the failure instead of treating it as an empty repo."""
        with patch.object(mock_issue_manager, "_get_repository", return_value=None):
            with pytest.raises(RuntimeError, match="Failed to get repository"):
                mock_issue_manager._list_issues_no_error_handling()


@pytest.mark.git_integration
class TestListIssuesExtendedParams:
    """Tests for labels, assignee, and max_results parameters."""

    def test_list_issues_with_labels(self, mock_issue_manager: IssueManager) -> None:
        """Verify labels param is forwarded to repo.get_issues()."""
        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.pull_request = None
        mock_issue.body = ""

        mock_issue_manager._repository.get_issues.return_value = [mock_issue]

        result = mock_issue_manager.list_issues(labels=["bug", "enhancement"])

        assert len(result) == 1
        mock_issue_manager._repository.get_issues.assert_called_once_with(
            state="open", labels=["bug", "enhancement"]
        )

    def test_list_issues_with_assignee(self, mock_issue_manager: IssueManager) -> None:
        """Verify assignee param is forwarded to repo.get_issues()."""
        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.pull_request = None
        mock_issue.body = ""

        mock_issue_manager._repository.get_issues.return_value = [mock_issue]

        result = mock_issue_manager.list_issues(assignee="octocat")

        assert len(result) == 1
        mock_issue_manager._repository.get_issues.assert_called_once_with(
            state="open", assignee="octocat"
        )

    def test_list_issues_with_max_results(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Verify iteration stops at max_results limit."""
        mock_issues = []
        for i in range(10):
            issue = MagicMock()
            issue.number = i + 1
            issue.pull_request = None
            issue.body = ""
            mock_issues.append(issue)

        mock_issue_manager._repository.get_issues.return_value = mock_issues

        result = mock_issue_manager.list_issues(max_results=3)

        assert len(result) == 3
        assert [r["number"] for r in result] == [1, 2, 3]

    def test_list_issues_max_results_with_pr_filtering(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Verify max_results counts only non-PR issues when include_pull_requests=False."""
        items = []
        for i in range(6):
            item = MagicMock()
            item.number = i + 1
            item.body = ""
            # Alternate: issue, PR, issue, PR, issue, PR
            item.pull_request = MagicMock() if i % 2 == 1 else None
            items.append(item)

        mock_issue_manager._repository.get_issues.return_value = items

        result = mock_issue_manager.list_issues(
            include_pull_requests=False, max_results=2
        )

        assert len(result) == 2
        # Should get issues #1 and #3 (skipping PRs #2 and #4)
        assert [r["number"] for r in result] == [1, 3]

    def test_list_issues_combined_params(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Verify all new params work together."""
        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.pull_request = None
        mock_issue.body = ""

        mock_issue_manager._repository.get_issues.return_value = [mock_issue]

        result = mock_issue_manager.list_issues(
            state="closed",
            labels=["bug"],
            assignee="octocat",
            max_results=10,
        )

        assert len(result) == 1
        mock_issue_manager._repository.get_issues.assert_called_once_with(
            state="closed", labels=["bug"], assignee="octocat"
        )

    def test_list_issues_max_results_none_returns_all(
        self, mock_issue_manager: IssueManager
    ) -> None:
        """Verify that max_results=None returns all issues (default behavior)."""
        mock_issues = []
        for i in range(5):
            issue = MagicMock()
            issue.number = i + 1
            issue.pull_request = None
            issue.body = ""
            mock_issues.append(issue)

        mock_issue_manager._repository.get_issues.return_value = mock_issues

        result = mock_issue_manager.list_issues(max_results=None)

        assert len(result) == 5
