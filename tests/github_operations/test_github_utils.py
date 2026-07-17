"""Tests for GitHub operations module.

Integration tests require GitHub configuration:

Environment Variables (recommended):
    GITHUB_TOKEN: GitHub Personal Access Token with repo scope
    GITHUB_TEST_REPO_URL: URL of test repository (e.g., https://github.com/user/test-repo)

Config File Alternative (~/.mcp_coder/config.toml):
    [github]
    token = "ghp_your_token_here"
    test_repo_url = "https://github.com/user/test-repo"

Note: Tests will be skipped if configuration is missing.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Generator, List
from unittest.mock import MagicMock, Mock, patch

import git
import pytest

from mcp_workspace.github_operations import LabelsManager, PullRequestManager
from mcp_workspace.github_operations.labels_manager import LabelData
from mcp_workspace.github_operations.pr_manager import PullRequestData

if TYPE_CHECKING:
    from tests.conftest import GitHubTestSetup


@pytest.fixture
def labels_manager(
    github_test_setup: "GitHubTestSetup",
) -> Generator[LabelsManager, None, None]:
    """Create LabelsManager instance for testing.

    Uses shared github_test_setup fixture for configuration and repository setup.

    Args:
        github_test_setup: Shared GitHub test configuration fixture

    Returns:
        LabelsManager: Configured instance for testing

    Raises:
        pytest.skip: When GitHub token or test repository not configured
    """
    from tests.conftest import create_github_manager

    try:
        manager = create_github_manager(LabelsManager, github_test_setup)
        yield manager
    except Exception as e:  # pylint: disable=broad-exception-caught
        pytest.skip(f"Failed to create LabelsManager: {e}")


@pytest.fixture
def pr_manager(
    github_test_setup: "GitHubTestSetup",
) -> Generator[PullRequestManager, None, None]:
    """Create PullRequestManager instance for testing.

    Uses shared github_test_setup fixture for configuration and repository setup.

    Args:
        github_test_setup: Shared GitHub test configuration fixture

    Returns:
        PullRequestManager: Configured instance for testing

    Raises:
        pytest.skip: When GitHub token or test repository not configured
    """
    from tests.conftest import create_github_manager

    try:
        manager = create_github_manager(PullRequestManager, github_test_setup)
        yield manager
    except Exception as e:  # pylint: disable=broad-exception-caught
        pytest.skip(f"Failed to create PullRequestManager: {e}")


@pytest.mark.git_integration
class TestPullRequestManagerUnit:
    """Unit tests for PullRequestManager with mocked dependencies."""

    def test_title_validation_empty_string(self, tmp_path: Path) -> None:
        """Test that empty title returns empty dict."""
        # Setup git repo with mocked config
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)

            # Test empty title
            result = manager.create_pull_request("", "feature-branch", "main")
            assert not result  # Should return empty dict

            # Test whitespace-only title
            result = manager.create_pull_request("   ", "feature-branch", "main")
            assert not result  # Should return empty dict

    def test_branch_validation(self, tmp_path: Path) -> None:
        """Test branch name validation."""
        # Setup git repo with mocked config
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)

            # Test invalid head branch
            result = manager.create_pull_request(
                "Valid Title", "invalid~branch", "main"
            )
            assert not result  # Should return empty dict

            # Test invalid base branch
            result = manager.create_pull_request(
                "Valid Title", "feature", "invalid^branch"
            )
            assert not result  # Should return empty dict

    @patch("mcp_workspace.github_operations._client.Github")
    def test_create_pull_request_success(
        self, mock_github: Mock, tmp_path: Path
    ) -> None:
        """Test successful pull request creation with mocked GitHub API."""
        # Setup git repo
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        # Mock GitHub API responses
        mock_pr = MagicMock()
        mock_pr.number = 123
        mock_pr.title = "Test PR"
        mock_pr.body = "Test description"
        mock_pr.state = "open"
        mock_pr.head.ref = "feature-branch"
        mock_pr.base.ref = "main"
        mock_pr.html_url = "https://github.com/test/repo/pull/123"
        mock_pr.created_at.isoformat.return_value = "2023-01-01T00:00:00Z"
        mock_pr.updated_at.isoformat.return_value = "2023-01-01T00:00:00Z"
        mock_pr.user.login = "testuser"
        mock_pr.mergeable = True
        mock_pr.merged = False
        mock_pr.draft = False

        mock_repo = MagicMock()
        mock_repo.create_pull.return_value = mock_pr

        mock_github_client = MagicMock()
        mock_github_client.get_repo.return_value = mock_repo
        mock_github.return_value = mock_github_client

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)

            result = manager.create_pull_request(
                "Test PR", "feature-branch", "main", "Test description"
            )

            # Verify the result
            assert result["number"] == 123
            assert result["title"] == "Test PR"
            assert result["body"] == "Test description"
            assert result["state"] == "open"
            assert result["head_branch"] == "feature-branch"
            assert result["base_branch"] == "main"
            assert result["url"] == "https://github.com/test/repo/pull/123"

            # Verify GitHub API was called correctly
            mock_repo.create_pull.assert_called_once_with(
                title="Test PR",
                body="Test description",
                head="feature-branch",
                base="main",
            )

    def test_repository_name_property(self, tmp_path: Path) -> None:
        """Test repository_name property."""
        # Setup git repo with mocked config
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/testuser/testrepo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)

            assert manager.repository_name == "testuser/testrepo"


@pytest.mark.github_integration
class TestPullRequestManagerIntegration:
    """Integration tests for PullRequestManager with GitHub API."""

    def test_pr_manager_lifecycle(  # pylint: disable=too-many-statements
        self, pr_manager: PullRequestManager
    ) -> None:
        """Test complete PR lifecycle: create, get, list, close.

        This test creates a test branch, creates a PR, retrieves it, lists PRs, and closes it.
        """
        print("\n=== TEST FUNCTION START ===")
        print(f"PR Manager received: {type(pr_manager)}")
        print(f"Project dir: {pr_manager.project_dir}")

        from mcp_workspace.git_operations import create_branch, push_branch

        test_branch = "test-branch-lifecycle"

        # Create unique PR title with timestamp and current branch name
        import datetime

        from mcp_workspace.git_operations import get_current_branch_name

        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
        current_branch = get_current_branch_name(Path.cwd()) or "unknown"
        pr_title = f"Test PR for Lifecycle - {timestamp} - {current_branch}"
        pr_body = f"This is a test PR for the complete lifecycle test.\n\nGenerated at: {datetime.datetime.now().isoformat()}\nFrom branch: {current_branch}"

        print(f"Starting lifecycle test with branch: {test_branch}")

        # Enable debug logging to see GitHub API errors
        import logging
        import sys

        # Set up basic logging to console
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(name)s - %(levelname)s - %(message)s",
            stream=sys.stdout,
            force=True,
        )

        logging.getLogger("mcp_workspace.github_operations.pr_manager").setLevel(
            logging.DEBUG
        )
        logging.getLogger("github").setLevel(logging.DEBUG)
        print("[DEBUG] Logging configured")

        created_pr = None
        try:
            # Check if test branch exists remotely first
            from mcp_workspace.git_operations import (
                branch_exists,
                checkout_branch,
                fetch_remote,
            )

            # Fetch latest to see all remote branches
            print("Fetching latest from remote...")
            assert pr_manager.project_dir is not None, "project_dir should not be None"
            fetch_result = fetch_remote(pr_manager.project_dir)
            print(f"Fetch result: {fetch_result}")

            # Check if the test branch exists remotely by checking git ls-remote
            # git already imported at module level
            repo = git.Repo(pr_manager.project_dir)
            try:
                # List all remote branches
                remote_branches = str(repo.git.ls_remote("--heads", "origin")).split(
                    "\n"
                )
                remote_branch_names = [
                    line.split("/")[-1] for line in remote_branches if line.strip()
                ]
                branch_exists_remotely = test_branch in remote_branch_names
                print(f"Remote branches: {remote_branch_names}")
                print(f"Branch {test_branch} exists remotely: {branch_exists_remotely}")
            except Exception as e:  # pylint: disable=broad-exception-caught
                print(f"Failed to check remote branches: {e}")
                branch_exists_remotely = False

            # Check if the test branch already exists locally
            assert pr_manager.project_dir is not None, "project_dir should not be None"
            branch_exists_locally = branch_exists(pr_manager.project_dir, test_branch)
            print(f"Branch {test_branch} exists locally: {branch_exists_locally}")

            if branch_exists_remotely:
                # Branch exists remotely - checkout or create tracking branch
                if branch_exists_locally:
                    print(f"Checking out existing local branch: {test_branch}")
                    assert (
                        pr_manager.project_dir is not None
                    ), "project_dir should not be None"
                    checkout_result = checkout_branch(
                        test_branch, pr_manager.project_dir
                    )
                    print(f"Checkout result: {checkout_result}")

                    # Pull latest changes from remote
                    try:
                        repo.git.pull("origin", test_branch)
                        print(f"[OK] Pulled latest changes for {test_branch}")
                    except Exception as e:  # pylint: disable=broad-exception-caught
                        print(f"[WARN] Pull failed: {e}")
                else:
                    print(f"Creating local tracking branch for remote {test_branch}")
                    try:
                        repo.git.checkout("-b", test_branch, f"origin/{test_branch}")
                        print(f"[OK] Created local tracking branch for {test_branch}")
                    except Exception as e:  # pylint: disable=broad-exception-caught
                        print(f"[ERROR] Failed to create tracking branch: {e}")
                        pytest.skip(
                            f"Failed to create tracking branch for {test_branch}"
                        )
            elif branch_exists_locally:
                # Branch exists locally but not remotely - just checkout
                print(f"Checking out existing local branch: {test_branch}")
                assert (
                    pr_manager.project_dir is not None
                ), "project_dir should not be None"
                checkout_result = checkout_branch(test_branch, pr_manager.project_dir)
                print(f"Checkout result: {checkout_result}")
                if not checkout_result:
                    pytest.skip(f"Failed to checkout existing branch: {test_branch}")
            else:
                # Branch doesn't exist - create new branch and push it
                print(f"Creating new branch: {test_branch}")
                assert (
                    pr_manager.project_dir is not None
                ), "project_dir should not be None"
                create_result = create_branch(
                    test_branch, pr_manager.project_dir, from_branch="main"
                )
                print(f"Create branch result: {create_result}")
                if not create_result:
                    print(f"[ERROR] Branch creation failed for: {test_branch}")
                    pytest.skip(f"Failed to create test branch: {test_branch}")

                print(f"Pushing new branch: {test_branch}")

                # Try manual push to see detailed error
                try:
                    push_info = repo.git.push("--set-upstream", "origin", test_branch)
                    print(f"Manual push info: {push_info}")
                    push_result = True
                except (
                    Exception
                ) as push_error:  # pylint: disable=broad-exception-caught
                    print(f"Manual push failed with: {push_error}")
                    assert (
                        pr_manager.project_dir is not None
                    ), "project_dir should not be None"
                    push_result = push_branch(test_branch, pr_manager.project_dir)
                    print(f"Push branch result: {push_result}")

                if not push_result:
                    print(f"[ERROR] Branch push failed for: {test_branch}")
                    pytest.skip(f"Failed to push test branch: {test_branch}")

            # Check current branch before creating PR
            current_branch = repo.active_branch.name
            print(f"Current active branch: {current_branch}")

            # Verify we're on the test branch
            if current_branch != test_branch:
                print(f"[WARN] Not on test branch {test_branch}, switching...")
                repo.git.checkout(test_branch)
                print(f"Switched to branch: {repo.active_branch.name}")

            # Test GitHub API access first
            print("[DEBUG] Testing GitHub API access...")
            try:
                existing_prs_before = pr_manager.list_pull_requests(state="open")
                print(
                    f"[DEBUG] Successfully listed {len(existing_prs_before)} existing PRs"
                )
                print(f"[DEBUG] Repository name: {pr_manager.repository_name}")
                print(
                    f"[DEBUG] Repository URL: {pr_manager._repo_identifier.https_url}"
                )
            except Exception as e:  # pylint: disable=broad-exception-caught
                print(f"[ERROR] GitHub API access failed: {e}")
                pytest.skip(f"GitHub API access failed: {e}")

            # Verify branch has commits (optional verification)
            print(f"Current active branch: {repo.active_branch.name}")

            # Create a unique commit on the test branch to avoid GitHub's 100 PR limit per SHA
            print(
                "[DEBUG] Creating unique commit on test branch to avoid SHA collision..."
            )
            assert pr_manager.project_dir is not None, "project_dir should not be None"
            test_file_path = pr_manager.project_dir / "test_commit_marker.txt"
            unique_timestamp = datetime.datetime.now().isoformat()
            test_file_path.write_text(f"Test commit at {unique_timestamp}\n")
            repo.index.add([str(test_file_path)])
            commit_msg = f"Test commit for PR lifecycle test at {unique_timestamp}"
            repo.index.commit(commit_msg)
            print(f"[DEBUG] Created commit: {commit_msg}")

            # Push the new commit to remote
            try:
                repo.git.push("origin", test_branch)
                print(f"[DEBUG] Pushed unique commit to remote {test_branch}")
            except Exception as push_error:  # pylint: disable=broad-exception-caught
                print(f"[WARN] Failed to push commit: {push_error}")
                # Continue anyway - PR creation might still work with local commit

            # Create pull request with debug logging
            print(f"Creating PR: {pr_title} from {test_branch} to main")
            try:
                created_pr = pr_manager.create_pull_request(
                    title=pr_title,
                    head_branch=test_branch,
                    base_branch="main",
                    body=pr_body,
                )
                print(f"PR creation result: {created_pr}")
                print(f"PR creation successful: {bool(created_pr)}")
                if created_pr:
                    print(f"PR #{created_pr['number']}: {created_pr['title']}")
                    print(f"PR URL: {created_pr['url']}")
            except Exception as e:  # pylint: disable=broad-exception-caught
                print(f"[ERROR] Exception during PR creation: {e}")
                import traceback

                print(f"[ERROR] Traceback: {traceback.format_exc()}")
                from typing import cast

                created_pr = cast(PullRequestData, {})

            # If PR creation failed, let's see if there are existing PRs for this branch
            if not created_pr:
                print("[DEBUG] PR creation failed, checking existing PRs...")
                existing_prs = pr_manager.list_pull_requests(state="open")
                print(f"Existing open PRs: {len(existing_prs)}")
                for pr in existing_prs:
                    if pr.get("head_branch") == test_branch:
                        print(
                            f"Found existing PR for branch {test_branch}: #{pr['number']} - {pr['title']}"
                        )
                        created_pr = pr
                        break

            # Verify PR was created or found
            assert created_pr, f"Expected PR creation to return data. Got: {created_pr}"
            assert "number" in created_pr, "Expected PR number in response"
            assert "title" in created_pr, "Expected PR title in response"
            assert created_pr["title"] == pr_title, f"Expected title '{pr_title}'"

            pr_number = created_pr["number"]

            # Get specific pull request
            retrieved_pr = pr_manager.get_pull_request(pr_number)
            assert retrieved_pr, "Expected to retrieve PR data"
            assert retrieved_pr["number"] == pr_number, "Expected same PR number"
            assert retrieved_pr["title"] == pr_title, "Expected same PR title"

            # List pull requests
            pr_list = pr_manager.list_pull_requests(state="open")
            assert isinstance(pr_list, list), "Expected list of PRs"
            assert len(pr_list) > 0, "Expected at least one open PR"

            # Verify our PR is in the list
            our_pr = next((pr for pr in pr_list if pr["number"] == pr_number), None)
            assert our_pr is not None, "Expected our PR to be in the list"

            # Close pull request
            closed_pr = pr_manager.close_pull_request(pr_number)
            assert closed_pr, "Expected close operation to return data"
            assert closed_pr["number"] == pr_number, "Expected same PR number"
            assert closed_pr["state"] == "closed", "Expected PR to be closed"

        finally:
            # Cleanup: ensure PR is closed even if test fails
            if created_pr and "number" in created_pr:
                try:
                    pr_manager.close_pull_request(created_pr["number"])
                except Exception:  # pylint: disable=broad-exception-caught
                    pass  # Ignore cleanup failures

    def test_direct_instantiation(self, tmp_path: Path) -> None:
        """Test direct PullRequestManager instantiation."""
        # Setup git repo
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        # Test that direct instantiation creates instance
        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="test-token",
        ):
            direct_manager = PullRequestManager(git_dir)
            assert isinstance(direct_manager, PullRequestManager)
            assert direct_manager._repo_identifier.full_name == "test/repo"
            assert direct_manager._repo_identifier.hostname == "github.com"
            assert direct_manager.github_token == "test-token"

    def test_manager_properties(self, pr_manager: PullRequestManager) -> None:
        """Test PullRequestManager properties."""
        # Test repository_name property
        repo_name = pr_manager.repository_name
        assert repo_name, "Expected repository name to be returned"
        assert "/" in repo_name, "Expected repository name in 'owner/repo' format"

        # Test default_branch property
        # Note: In test environments without proper remote setup, this may return empty string
        default_branch = pr_manager.default_branch
        assert isinstance(default_branch, str), "Expected default branch to be string"
        # Default branch may be empty in test environment, but should at least be a string

    def test_list_pull_requests_with_filters(
        self, pr_manager: PullRequestManager
    ) -> None:
        """Test listing pull requests with different filters.

        This test verifies basic listing functionality with pagination limits
        to avoid performance issues as the repository accumulates PRs.
        """
        # Test listing open PRs (no limit needed - usually small)
        open_prs = pr_manager.list_pull_requests(state="open")
        assert isinstance(open_prs, list), "Expected list for open PRs"

        # Test listing closed PRs (limit to 5 most recent to avoid slowdown)
        closed_prs = pr_manager.list_pull_requests(state="closed", max_results=5)
        assert isinstance(closed_prs, list), "Expected list for closed PRs"
        assert len(closed_prs) <= 5, "Expected at most 5 closed PRs"

        # Test listing all PRs (limit to 10 most recent to avoid slowdown)
        all_prs = pr_manager.list_pull_requests(state="all", max_results=10)
        assert isinstance(all_prs, list), "Expected list for all PRs"
        assert len(all_prs) <= 10, "Expected at most 10 PRs total"

        # Verify returned data structure is valid
        if len(all_prs) > 0:
            pr = all_prs[0]
            assert "number" in pr, "Expected PR to have number field"
            assert "state" in pr, "Expected PR to have state field"
            assert "title" in pr, "Expected PR to have title field"

    def test_validation_failures(self, tmp_path: Path) -> None:
        """Test validation failures for invalid inputs."""
        # Test with None project_dir
        with pytest.raises(
            ValueError, match="Exactly one of project_dir or repo_url must be provided"
        ):
            PullRequestManager(None)

        # Test with non-existent directory
        nonexistent = tmp_path / "does_not_exist"
        with pytest.raises(ValueError, match="Directory does not exist"):
            PullRequestManager(nonexistent)

        # Test with file instead of directory
        file_path = tmp_path / "test_file.txt"
        file_path.write_text("test")
        with pytest.raises(ValueError, match="Path is not a directory"):
            PullRequestManager(file_path)

        # Test with non-git directory
        regular_dir = tmp_path / "regular_dir"
        regular_dir.mkdir()
        with pytest.raises(ValueError, match="Directory is not a git repository"):
            PullRequestManager(regular_dir)

        # Setup git repo for remaining tests
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        # Create manager with mocked token for validation tests
        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)

        # Test invalid PR numbers
        assert manager._validate_pr_number(0) == False
        assert manager._validate_pr_number(-1) == False
        assert manager._validate_pr_number(1) == True
        # Note: Testing with wrong types (like strings) is skipped as it's a type error

        # Test invalid branch names
        assert manager._validate_branch_name("") == False
        assert manager._validate_branch_name("   ") == False
        assert manager._validate_branch_name("branch~name") == False
        assert manager._validate_branch_name("branch^name") == False
        assert manager._validate_branch_name("branch:name") == False
        assert manager._validate_branch_name(".branch") == False
        assert manager._validate_branch_name("branch.") == False
        assert manager._validate_branch_name("branch.lock") == False
        assert manager._validate_branch_name("valid-branch") == True
        assert manager._validate_branch_name("feature/new-feature") == True

        # Test methods with invalid inputs return empty dict/list
        # Note: These return cast TypedDict instances, so we check for empty/falsy values
        invalid_pr_result = manager.get_pull_request(-1)
        assert not invalid_pr_result

        invalid_close_result = manager.close_pull_request(0)
        assert not invalid_close_result

        invalid_create_result = manager.create_pull_request(
            "title", "invalid~branch", "main"
        )
        assert not invalid_create_result

        invalid_list_result = manager.list_pull_requests(base_branch="invalid~branch")
        expected_empty_list: List[Dict[str, Any]] = []
        assert invalid_list_result == expected_empty_list


@pytest.mark.git_integration
class TestLabelsManagerUnit:
    """Unit tests for LabelsManager with mocked dependencies."""

    def test_initialization_requires_project_dir(self) -> None:
        """Test that None project_dir raises ValueError."""
        with pytest.raises(
            ValueError, match="Exactly one of project_dir or repo_url must be provided"
        ):
            LabelsManager(None)

    def test_initialization_requires_git_repository(self, tmp_path: Path) -> None:
        """Test that non-git directory raises ValueError."""
        # Create regular directory (not a git repo)
        regular_dir = tmp_path / "regular_dir"
        regular_dir.mkdir()

        with pytest.raises(ValueError, match="Directory is not a git repository"):
            LabelsManager(regular_dir)

    def test_initialization_requires_github_token(self, tmp_path: Path) -> None:
        """Test that missing GitHub token raises ValueError."""
        # Setup git repo
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        # Mock config to return None (no token)
        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value=None,
        ):
            with pytest.raises(ValueError, match="GitHub token not found"):
                LabelsManager(git_dir)

    def test_label_name_validation(self, tmp_path: Path) -> None:
        """Test label name validation rules."""
        # Setup git repo with mocked config
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = LabelsManager(git_dir)

            # Valid names - should pass validation
            assert manager._validate_label_name("bug") == True
            assert manager._validate_label_name("feature-request") == True
            assert manager._validate_label_name("high priority") == True
            assert manager._validate_label_name("bug :bug:") == True
            assert manager._validate_label_name("type/enhancement") == True

            # Invalid names - should fail validation
            assert manager._validate_label_name("") == False
            assert manager._validate_label_name("   ") == False
            assert manager._validate_label_name("  leading") == False
            assert manager._validate_label_name("trailing  ") == False

    def test_color_validation_and_normalization(self, tmp_path: Path) -> None:
        """Test color validation and normalization."""
        # Setup git repo with mocked config
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = LabelsManager(git_dir)

            # Valid colors - should pass validation
            assert manager._validate_color("FF0000") == True
            assert manager._validate_color("#FF0000") == True
            assert manager._validate_color("00ff00") == True
            assert manager._validate_color("#00FF00") == True

            # Invalid colors - should fail validation
            assert manager._validate_color("red") == False
            assert manager._validate_color("12345") == False
            assert manager._validate_color("GGGGGG") == False
            assert manager._validate_color("#12345") == False

            # Test normalization (removing '#' prefix)
            assert manager._normalize_color("#FF0000") == "FF0000"
            assert manager._normalize_color("FF0000") == "FF0000"
            assert manager._normalize_color("#00ff00") == "00ff00"
            assert manager._normalize_color("00FF00") == "00FF00"


@pytest.mark.github_integration
class TestLabelsManagerIntegration:
    """Integration tests for LabelsManager with GitHub API."""

    def test_labels_manager_lifecycle(self, labels_manager: LabelsManager) -> None:
        """Test complete label lifecycle: create, get, list, update, delete.

        This test creates a label, retrieves it, lists labels, updates it, and deletes it.
        """
        # Create unique label name with timestamp
        import datetime

        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        label_name = f"test-label-{timestamp}"
        label_color = "FF0000"
        label_description = "Test label for CRUD operations"

        created_label = None
        try:
            # Create label
            created_label = labels_manager.create_label(
                name=label_name, color=label_color, description=label_description
            )

            # Verify label was created
            assert created_label, "Expected label creation to return data"
            assert "name" in created_label, "Expected label name in response"
            assert created_label["name"] == label_name, f"Expected name '{label_name}'"
            assert (
                created_label["color"] == label_color
            ), f"Expected color '{label_color}'"
            assert (
                created_label["description"] == label_description
            ), f"Expected description '{label_description}'"

            # Get specific label
            retrieved_label = labels_manager.get_label(label_name)
            assert retrieved_label, "Expected to retrieve label data"
            assert retrieved_label["name"] == label_name, "Expected same label name"
            assert retrieved_label["color"] == label_color, "Expected same label color"

            # List labels
            labels_list = labels_manager.get_labels()
            assert isinstance(labels_list, list), "Expected list of labels"
            assert len(labels_list) > 0, "Expected at least one label"

            # Verify our label is in the list
            our_label = next(
                (lbl for lbl in labels_list if lbl["name"] == label_name), None
            )
            assert our_label is not None, "Expected our label to be in the list"

            # Update label
            updated_color = "00FF00"
            updated_description = "Updated test label description"
            updated_label = labels_manager.update_label(
                name=label_name, color=updated_color, description=updated_description
            )
            assert updated_label, "Expected update operation to return data"
            assert updated_label["name"] == label_name, "Expected same label name"
            assert updated_label["color"] == updated_color, "Expected updated color"
            assert (
                updated_label["description"] == updated_description
            ), "Expected updated description"

            # Delete label
            delete_result = labels_manager.delete_label(label_name)
            assert delete_result, "Expected delete operation to succeed"

            # Verify label was deleted - get_label should return empty dict
            deleted_label = labels_manager.get_label(label_name)
            assert not deleted_label, "Expected label to be deleted"

        finally:
            # Cleanup: ensure label is deleted even if test fails
            if created_label and "name" in created_label:
                try:
                    labels_manager.delete_label(created_label["name"])
                except Exception:  # pylint: disable=broad-exception-caught
                    pass  # Ignore cleanup failures
