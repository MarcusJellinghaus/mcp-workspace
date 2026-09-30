"""Smoke tests for GitHub API integration.

These tests verify basic connectivity and functionality with the GitHub API.
All detailed testing of our wrapper logic is in test_pr_manager.py and test_labels_manager.py.

Integration tests require GitHub configuration:

Environment Variables (recommended):
    GITHUB_TOKEN: GitHub Personal Access Token with repo scope
    GITHUB_TEST_REPO_URL: URL of test repository

Config File Alternative (~/.mcp_coder/config.toml):
    [github]
    token = "ghp_your_token_here"
    test_repo_url = "https://github.com/user/test-repo"

Note: Tests will be skipped if configuration is missing.
"""

import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Generator

import pytest

from mcp_workspace.github_operations import (
    CIResultsManager,
    LabelsManager,
    PullRequestManager,
)

if TYPE_CHECKING:
    from tests.conftest import GitHubTestSetup


@pytest.fixture
def labels_manager(
    github_test_setup: "GitHubTestSetup",
) -> Generator[LabelsManager, None, None]:
    """Create LabelsManager instance for testing."""
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
    """Create PullRequestManager instance for testing."""
    from tests.conftest import create_github_manager

    try:
        manager = create_github_manager(PullRequestManager, github_test_setup)
        yield manager
    except Exception as e:  # pylint: disable=broad-exception-caught
        pytest.skip(f"Failed to create PullRequestManager: {e}")


@pytest.fixture
def ci_manager(
    github_test_setup: "GitHubTestSetup",
) -> Generator[CIResultsManager, None, None]:
    """Create CIResultsManager instance for testing."""
    from tests.conftest import create_github_manager

    try:
        manager = create_github_manager(CIResultsManager, github_test_setup)
        yield manager
    except Exception as e:  # pylint: disable=broad-exception-caught
        pytest.skip(f"Failed to create CIResultsManager: {e}")


@pytest.mark.github_integration
class TestPullRequestManagerSmoke:
    """Smoke test for PullRequestManager GitHub API integration."""

    def test_basic_api_connectivity(self, pr_manager: PullRequestManager) -> None:
        """Smoke test: Verify basic GitHub API connectivity for PR operations.

        This is a minimal integration test that verifies:
        1. Authentication works
        2. Repository access works
        3. Basic PR listing works

        Detailed functionality testing is in test_pr_manager.py with mocked APIs.
        """
        # Test that we can list PRs (tests auth + repo access)
        # Only fetch a few to keep the test fast
        open_prs = pr_manager.list_pull_requests(state="open", max_results=5)
        assert isinstance(open_prs, list), "Expected list for open PRs"

        # Verify manager properties work
        repo_name = pr_manager.repository_name
        assert repo_name, "Expected repository name"
        assert "/" in repo_name, "Expected repository name in 'owner/repo' format"

    def test_pr_feedback_query_accepted(self, pr_manager: PullRequestManager) -> None:
        """The reviewThreads query passes GitHub's schema validation."""
        # An existing PR avoids the not-found retry loop; GitHub validates the
        # query before looking up the PR, so any PR will do.
        prs = pr_manager.list_pull_requests(state="all", max_results=1)
        if not prs:
            pytest.skip("test repo has no pull requests")

        result = pr_manager.get_pr_feedback(prs[0]["number"])
        assert "threads" not in result["unavailable"], result["unavailable"]

    def test_invalid_graphql_query_returns_errors_without_data(
        self, pr_manager: PullRequestManager
    ) -> None:
        """GitHub answers an invalid query with HTTP 200, `errors`, and no `data` key."""
        requester = pr_manager._github_client._Github__requester  # type: ignore[attr-defined]  # pylint: disable=protected-access

        # requestJsonAndCheck raises on a 4xx, which checks the HTTP 200 assumption.
        _, body = requester.requestJsonAndCheck(
            "POST",
            requester.graphql_url,
            input={"query": "query { viewer { notAField } }"},
        )
        assert "errors" in body
        assert "data" not in body

    def test_pr_crud_lifecycle(self, pr_manager: PullRequestManager) -> None:
        """Smoke test: Verify full PR CRUD lifecycle with real GitHub API.

        This test verifies:
        1. Branch creation and commit works
        2. PR creation works
        3. PR retrieval works
        4. PR closing works

        This is the minimal end-to-end test for PR operations.
        """
        import git

        from mcp_workspace.git_operations import (
            branch_exists,
            checkout_branch,
            create_branch,
            delete_branch,
        )

        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        test_branch = f"smoke-test-pr-{timestamp}"
        pr_title = f"Smoke test PR - {timestamp}"
        pr_body = "Automated smoke test for PR CRUD operations"

        repo = git.Repo(pr_manager.project_dir)
        original_branch = repo.active_branch.name
        created_pr = None

        try:
            # Create branch
            assert pr_manager.project_dir is not None, "project_dir should not be None"
            if not branch_exists(pr_manager.project_dir, test_branch):
                create_branch(test_branch, pr_manager.project_dir, from_branch="main")

            checkout_branch(test_branch, pr_manager.project_dir)

            # Create commit
            test_file = pr_manager.project_dir / f"smoke_test_{timestamp}.txt"
            test_file.write_text(f"Smoke test at {timestamp}\n")
            repo.index.add([str(test_file)])
            repo.index.commit(f"Smoke test commit {timestamp}")

            # Push branch
            repo.git.push("--set-upstream", "origin", test_branch)

            # Create PR
            created_pr = pr_manager.create_pull_request(
                title=pr_title,
                head_branch=test_branch,
                base_branch="main",
                body=pr_body,
            )
            assert created_pr, "Expected PR creation to return data"
            assert created_pr["number"] > 0, "Expected valid PR number"

            pr_number = created_pr["number"]
            print(f"\n[OK] Created PR #{pr_number}: {created_pr['url']}")

            # Read PR
            retrieved_pr = pr_manager.get_pull_request(pr_number)
            assert retrieved_pr["number"] == pr_number
            assert retrieved_pr["title"] == pr_title

            # Close PR
            closed_pr = pr_manager.close_pull_request(pr_number)
            assert closed_pr["state"] == "closed"
            print(
                f"[OK] Closed PR #{pr_number} - Check closed PRs in your repo to verify!"
            )

        finally:
            # Cleanup
            if created_pr and "number" in created_pr:
                try:
                    pr_manager.close_pull_request(created_pr["number"])
                except Exception:  # pylint: disable=broad-exception-caught
                    pass

            # Switch back to original branch and delete test branch
            try:
                repo.git.checkout(original_branch)
                # Delete the test branch locally and remotely
                assert (
                    pr_manager.project_dir is not None
                ), "project_dir should not be None"
                delete_branch(
                    test_branch, pr_manager.project_dir, force=True, delete_remote=True
                )
                print(f"[OK] Cleaned up test branch: {test_branch}")
            except Exception as e:  # pylint: disable=broad-exception-caught
                print(f"[WARN] Branch cleanup failed: {e}")


@pytest.mark.github_integration
class TestLabelsManagerSmoke:
    """Smoke test for LabelsManager GitHub API integration."""

    def test_basic_api_connectivity(self, labels_manager: LabelsManager) -> None:
        """Smoke test: Verify basic GitHub API connectivity for label operations.

        This is a minimal integration test that verifies:
        1. Authentication works
        2. Repository access works
        3. Basic label listing works
        4. CRUD operations work end-to-end

        Detailed functionality testing is in test_labels_manager.py with mocked APIs.
        """
        # Test that we can list labels (tests auth + repo access)
        labels_list = labels_manager.get_labels()
        assert isinstance(labels_list, list), "Expected list of labels"

        # Quick CRUD test with one label
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        label_name = f"smoke-test-{timestamp}"

        created_label = None
        try:
            # Create
            created_label = labels_manager.create_label(
                name=label_name, color="FF0000", description="Smoke test label"
            )
            assert created_label, "Expected label creation to return data"
            assert created_label["name"] == label_name

            # Read
            retrieved_label = labels_manager.get_label(label_name)
            assert retrieved_label["name"] == label_name

            # Update
            updated_label = labels_manager.update_label(name=label_name, color="00FF00")
            assert updated_label["color"] == "00FF00"

            # Delete
            delete_result = labels_manager.delete_label(label_name)
            assert delete_result is True

        finally:
            # Cleanup
            if created_label and "name" in created_label:
                try:
                    labels_manager.delete_label(created_label["name"])
                except Exception:  # pylint: disable=broad-exception-caught
                    pass  # Ignore cleanup failures


@pytest.mark.github_integration
class TestCIResultsManagerSmoke:
    """Smoke test for CIResultsManager GitHub API integration."""

    def test_basic_api_connectivity(
        self, ci_manager: CIResultsManager, github_test_setup: "GitHubTestSetup"
    ) -> None:
        """Verify basic GitHub Actions API connectivity."""
        # Get default branch dynamically (Decision 21)
        from mcp_workspace.git_operations import get_default_branch_name

        project_dir = github_test_setup["project_dir"]
        default_branch = get_default_branch_name(project_dir) or "main"

        # Test CI status retrieval works
        status = ci_manager.get_latest_ci_status(default_branch)
        assert isinstance(status, dict)
        assert "run" in status
        assert "jobs" in status

        print(f"[OK] CI status retrieved for branch '{default_branch}'")

    def test_ci_analysis_workflow(
        self, ci_manager: CIResultsManager, github_test_setup: "GitHubTestSetup"
    ) -> None:
        """Verify complete CI analysis workflow."""
        # Get default branch dynamically (Decision 21)
        from mcp_workspace.git_operations import get_default_branch_name

        project_dir = github_test_setup["project_dir"]
        default_branch = get_default_branch_name(project_dir) or "main"

        # Get CI status
        status = ci_manager.get_latest_ci_status(default_branch)

        if status["run"]:  # If there are CI runs
            run_id = status["run"]["run_ids"][0]

            # Test log retrieval (returns all logs - Decision 15)
            logs = ci_manager.get_run_logs(run_id)
            assert isinstance(logs, dict)
            # Logs are {filename: content} - consumer filters by job name

            # Test artifact retrieval (may be empty if no artifacts)
            artifacts = ci_manager.get_artifacts(run_id)
            assert isinstance(artifacts, dict)

            print(f"[OK] CI analysis workflow tested for run {run_id}")
        else:
            print("[INFO] No CI runs found for testing workflow")
