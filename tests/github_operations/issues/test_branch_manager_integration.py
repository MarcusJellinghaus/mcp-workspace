"""Integration tests for IssueBranchManager with GitHub API.

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

from mcp_workspace.github_operations.issues import IssueBranchManager, IssueManager

if TYPE_CHECKING:
    from tests.conftest import GitHubTestSetup


@pytest.fixture
def issue_branch_manager(
    github_test_setup: "GitHubTestSetup",
) -> Generator[IssueBranchManager, None, None]:
    """Create IssueBranchManager instance for testing.

    Uses shared github_test_setup fixture for configuration and repository setup.

    Args:
        github_test_setup: Shared GitHub test configuration fixture

    Returns:
        IssueBranchManager: Configured instance for testing

    Raises:
        pytest.skip: When GitHub token or test repository not configured
    """
    from tests.conftest import create_github_manager

    try:
        manager = create_github_manager(IssueBranchManager, github_test_setup)
        yield manager
    except Exception as e:  # pylint: disable=broad-exception-caught
        pytest.skip(f"Failed to create IssueBranchManager: {e}")


@pytest.fixture
def issue_manager(
    github_test_setup: "GitHubTestSetup",
) -> Generator[IssueManager, None, None]:
    """Create IssueManager instance for testing.

    Uses shared github_test_setup fixture for configuration and repository setup.

    Args:
        github_test_setup: Shared GitHub test configuration fixture

    Returns:
        IssueManager: Configured instance for testing

    Raises:
        pytest.skip: When GitHub token or test repository not configured
    """
    from tests.conftest import create_github_manager

    try:
        manager = create_github_manager(IssueManager, github_test_setup)
        yield manager
    except Exception as e:  # pylint: disable=broad-exception-caught
        pytest.skip(f"Failed to create IssueManager: {e}")


@pytest.mark.github_integration
class TestIssueBranchManagerIntegration:
    """Integration tests for IssueBranchManager with GitHub API."""

    def test_complete_branch_linking_workflow(  # pylint: disable=too-many-statements
        self,
        issue_branch_manager: IssueBranchManager,
        issue_manager: IssueManager,
    ) -> None:
        """Test full workflow: create issue → link branch → query → unlink → verify.

        This single test exercises the complete IssueBranchManager API:
        - Branch creation and linking
        - Querying linked branches
        - Duplicate prevention (allow_multiple=False)
        - Multiple branch creation (allow_multiple=True)
        - Branch unlinking
        - Git branch cleanup

        Only ONE issue is created and used for all operations.
        """
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        issue_title = f"Integration Test - Branch Linking - {timestamp}"
        issue_body = (
            f"This is THE single integration test issue for branch linking.\n\n"
            f"All branch operations are tested on this one issue.\n\n"
            f"Generated at: {datetime.datetime.now().isoformat()}"
        )

        created_issue = None
        created_branches = []

        try:
            # ============================================================
            # SECTION 1: Issue Creation
            # ============================================================
            print("\n" + "=" * 60)
            print("SECTION 1: Issue Creation")
            print("=" * 60)

            created_issue = issue_manager.create_issue(
                title=issue_title,
                body=issue_body,
                labels=["test", "integration"],
            )

            assert created_issue, "Expected issue creation to return data"
            assert created_issue["number"] > 0, "Expected valid issue number"
            issue_number = created_issue["number"]
            print(f"✓ Created issue #{issue_number}")
            print(f"  Title: {issue_title}")

            # ============================================================
            # SECTION 2: Create and Link First Branch
            # ============================================================
            print("\n" + "=" * 60)
            print("SECTION 2: Create and Link First Branch")
            print("=" * 60)

            result = issue_branch_manager.create_remote_branch_for_issue(
                issue_number=issue_number
            )

            assert (
                result["success"] is True
            ), f"Branch creation failed: {result['error']}"
            assert result["branch_name"], "Branch name should not be empty"
            assert result["error"] is None, "Error should be None on success"
            created_branches.append(result["branch_name"])
            print(f"✓ Created and linked branch: {result['branch_name']}")

            # ============================================================
            # SECTION 3: Query Linked Branches
            # ============================================================
            print("\n" + "=" * 60)
            print("SECTION 3: Query Linked Branches")
            print("=" * 60)

            branches = issue_branch_manager.get_linked_branches(issue_number)
            assert (
                result["branch_name"] in branches
            ), f"Expected branch '{result['branch_name']}' in linked branches"
            print(f"✓ Verified branch appears in linked branches: {branches}")

            # ============================================================
            # SECTION 4: Test Duplicate Prevention (allow_multiple=False)
            # ============================================================
            print("\n" + "=" * 60)
            print("SECTION 4: Test Duplicate Prevention (allow_multiple=False)")
            print("=" * 60)

            dup_result = issue_branch_manager.create_remote_branch_for_issue(
                issue_number=issue_number
            )

            assert (
                dup_result["success"] is False
            ), "Should fail when creating duplicate without allow_multiple=True"
            assert (
                len(dup_result["existing_branches"]) > 0
            ), "Should return list of existing branches"
            assert (
                result["branch_name"] in dup_result["existing_branches"]
            ), "Existing branches should include first branch"
            assert dup_result["error"] is not None, "Error message should be present"
            print("✓ Duplicate prevention works")
            print(f"  Error: {dup_result['error']}")
            print(f"  Existing branches: {dup_result['existing_branches']}")

            # ============================================================
            # SECTION 5: Test Multiple Branches (allow_multiple=True)
            # ============================================================
            print("\n" + "=" * 60)
            print("SECTION 5: Test Multiple Branches (allow_multiple=True)")
            print("=" * 60)

            second_branch_name = f"{issue_number}-second-branch-{timestamp}"
            result2 = issue_branch_manager.create_remote_branch_for_issue(
                issue_number=issue_number,
                branch_name=second_branch_name,
                allow_multiple=True,
            )

            assert (
                result2["success"] is True
            ), f"Second branch creation failed: {result2['error']}"
            assert (
                result2["branch_name"] == second_branch_name
            ), "Branch name should match requested name"
            created_branches.append(result2["branch_name"])
            print("✓ Created second branch with allow_multiple=True")
            print(f"  Branch name: {result2['branch_name']}")

            # Verify both branches are linked
            branches_after = issue_branch_manager.get_linked_branches(issue_number)
            assert (
                result["branch_name"] in branches_after
            ), "First branch should still be linked"
            assert (
                result2["branch_name"] in branches_after
            ), "Second branch should be linked"
            print(f"✓ Verified both branches are linked: {branches_after}")

            # ============================================================
            # SECTION 6: Unlink First Branch
            # ============================================================
            print("\n" + "=" * 60)
            print("SECTION 6: Unlink First Branch")
            print("=" * 60)

            unlinked = issue_branch_manager.delete_linked_branch(
                issue_number=issue_number,
                branch_name=result["branch_name"],
            )

            assert unlinked is True, "Should successfully unlink branch"
            print(f"✓ Unlinked branch: {result['branch_name']}")

            # Verify first branch is no longer linked
            branches_after_unlink = issue_branch_manager.get_linked_branches(
                issue_number
            )
            assert (
                result["branch_name"] not in branches_after_unlink
            ), "First branch should not be in linked branches after unlinking"
            assert (
                result2["branch_name"] in branches_after_unlink
            ), "Second branch should still be linked"
            print(f"✓ Verified first branch removed: {branches_after_unlink}")

            # ============================================================
            # SECTION 7: Git Branch Cleanup
            # ============================================================
            print("\n" + "=" * 60)
            print("SECTION 7: Git Branch Cleanup")
            print("=" * 60)

            repo = issue_branch_manager._get_repository()
            assert repo is not None, "Repository should be accessible"

            # Delete actual Git branches
            for branch_name in created_branches:
                try:
                    ref = repo.get_git_ref(f"heads/{branch_name}")
                    ref.delete()
                    print(f"✓ Deleted Git branch: {branch_name}")
                except Exception as e:  # pylint: disable=broad-exception-caught
                    print(f"⚠ Failed to delete Git branch {branch_name}: {e}")

            # ============================================================
            # SECTION 8: Cleanup Issue
            # ============================================================
            print("\n" + "=" * 60)
            print("SECTION 8: Cleanup Issue")
            print("=" * 60)

            closed = issue_manager.close_issue(issue_number)
            assert closed["state"] == "closed"
            print(f"✓ Closed issue #{issue_number}")

            # ============================================================
            # SECTION 9: Summary
            # ============================================================
            print("\n" + "=" * 60)
            print("INTEGRATION TEST SUMMARY")
            print("=" * 60)
            print(f"✓ All operations completed successfully on issue #{issue_number}")
            print("  - Issue creation")
            print("  - Branch creation and linking")
            print("  - Query linked branches")
            print("  - Duplicate prevention (allow_multiple=False)")
            print("  - Multiple branches (allow_multiple=True)")
            print("  - Branch unlinking")
            print("  - Git branch cleanup")
            print("\n✓ Integration test PASSED with ONE issue")
            print("=" * 60)

        finally:
            # Final cleanup: ensure issue is closed and branches are deleted
            if created_issue and "number" in created_issue:
                try:
                    issue_manager.close_issue(created_issue["number"])
                    print(
                        f"\n✓ Final cleanup: Ensured issue #{created_issue['number']} is closed"
                    )
                except Exception:  # pylint: disable=broad-exception-caught
                    pass  # Ignore cleanup failures

            # Attempt to delete any remaining branches
            if created_branches:
                try:
                    repo = issue_branch_manager._get_repository()
                    if repo is not None:
                        for branch_name in created_branches:
                            try:
                                ref = repo.get_git_ref(f"heads/{branch_name}")
                                ref.delete()
                                print(f"✓ Final cleanup: Deleted branch {branch_name}")
                            except Exception:  # pylint: disable=broad-exception-caught
                                pass  # Branch may already be deleted
                except Exception:  # pylint: disable=broad-exception-caught
                    pass  # Ignore cleanup failures

    def test_error_handling_without_creating_issues(
        self, issue_branch_manager: IssueBranchManager
    ) -> None:
        """Test error handling without creating any issues.

        Tests operations on non-existent issues and invalid inputs that don't
        require creating real issues.
        """
        print("\n" + "=" * 60)
        print("ERROR HANDLING: No Issues Created")
        print("=" * 60)

        non_existent = 999999999

        # Test operations on non-existent issue
        print("\n1. Testing operations on non-existent issue...")

        # Test get_linked_branches on non-existent issue
        branches = issue_branch_manager.get_linked_branches(non_existent)
        assert len(branches) == 0, "Should return empty list for non-existent issue"
        print("✓ get_linked_branches on non-existent issue")

        # Test create_remote_branch_for_issue on non-existent issue
        result = issue_branch_manager.create_remote_branch_for_issue(
            issue_number=non_existent
        )
        assert result["success"] is False, "Should fail for non-existent issue"
        print("✓ create_remote_branch_for_issue on non-existent issue")

        # Test delete_linked_branch on non-existent issue
        success = issue_branch_manager.delete_linked_branch(non_existent, "fake-branch")
        assert success is False, "Should fail for non-existent issue"
        print("✓ delete_linked_branch on non-existent issue")

        # Test with invalid issue numbers
        print("\n2. Testing with invalid issue numbers...")

        branches = issue_branch_manager.get_linked_branches(-1)
        assert len(branches) == 0, "Should return empty list for negative issue number"
        print("✓ Negative issue number")

        branches = issue_branch_manager.get_linked_branches(0)
        assert len(branches) == 0, "Should return empty list for zero issue number"
        print("✓ Zero issue number")

        result = issue_branch_manager.create_remote_branch_for_issue(issue_number=-1)
        assert result["success"] is False, "Should fail for negative issue number"
        print("✓ create_remote_branch_for_issue with negative number")

        # Test delete_linked_branch with invalid inputs
        print("\n3. Testing delete_linked_branch with invalid inputs...")

        success = issue_branch_manager.delete_linked_branch(123, "")
        assert success is False, "Should fail for empty branch name"
        print("✓ Empty branch name")

        success = issue_branch_manager.delete_linked_branch(123, "   ")
        assert success is False, "Should fail for whitespace-only branch name"
        print("✓ Whitespace-only branch name")

        print("\n✓ All error handling tests passed (0 issues created)")
        print("=" * 60)
