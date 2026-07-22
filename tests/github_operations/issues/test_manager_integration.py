"""Integration tests for IssueManager with GitHub API.

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
import time
from pathlib import Path
from typing import TYPE_CHECKING, Generator

import pytest

from mcp_workspace.github_operations.issues import IssueManager

if TYPE_CHECKING:
    from tests.conftest import GitHubTestSetup


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
class TestIssueManagerIntegration:
    """Integration tests for IssueManager with GitHub API."""

    def test_complete_issue_workflow(  # pylint: disable=too-many-statements
        self, issue_manager: IssueManager
    ) -> None:
        """Comprehensive test of ALL issue operations on a SINGLE issue.

        This single test exercises the complete IssueManager API:
        - Issue lifecycle: create → close → reopen
        - Label operations: add → remove → set → edge cases
        - Comment operations: add → get → edit → delete
        - Error handling: invalid inputs, non-existent resources

        Only ONE issue is created and used for all operations.
        """
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        issue_title = f"Integration Test - Complete Workflow - {timestamp}"
        issue_body = (
            f"This is THE single integration test issue.\n\n"
            f"All operations (lifecycle, labels, comments, error handling) "
            f"are tested on this one issue.\n\n"
            f"Generated at: {datetime.datetime.now().isoformat()}"
        )

        created_issue = None
        try:
            # ============================================================
            # SECTION 1: Issue Creation
            # ============================================================
            print("\n" + "=" * 60)
            print("SECTION 1: Issue Creation")
            print("=" * 60)

            created_issue = issue_manager.create_issue(
                title=issue_title, body=issue_body, labels=["test", "integration"]
            )

            assert created_issue, "Expected issue creation to return data"
            assert created_issue["number"] > 0, "Expected valid issue number"
            assert created_issue["title"] == issue_title
            assert created_issue["body"] == issue_body
            assert created_issue["state"] == "open"
            assert "test" in created_issue["labels"]
            assert "integration" in created_issue["labels"]

            issue_number = created_issue["number"]
            print(f"✓ Created issue #{issue_number}")
            print(f"  Title: {issue_title}")
            print(f"  Labels: {created_issue['labels']}")

            # ============================================================
            # SECTION 1.5: Get Issue Verification
            # ============================================================
            print("\n" + "=" * 60)
            print("SECTION 1.5: Get Issue Verification")
            print("=" * 60)

            retrieved = issue_manager.get_issue(issue_number)
            assert retrieved["number"] == issue_number
            assert retrieved["title"] == issue_title
            assert retrieved["body"] == issue_body
            assert retrieved["state"] == "open"
            assert "assignees" in retrieved
            assert isinstance(retrieved["assignees"], list)
            print(f"✓ Retrieved issue #{issue_number} successfully")
            print(f"  Assignees: {retrieved['assignees']}")

            # ============================================================
            # SECTION 2: Label Operations
            # ============================================================
            print("\n" + "=" * 60)
            print("SECTION 2: Label Operations")
            print("=" * 60)

            # Add labels
            print("\n2.1: Adding labels...")
            labeled = issue_manager.add_labels(issue_number, "bug", "enhancement")
            assert "bug" in labeled["labels"]
            assert "enhancement" in labeled["labels"]
            assert "test" in labeled["labels"]  # Original labels remain
            assert "integration" in labeled["labels"]
            print(f"✓ Added labels: {labeled['labels']}")

            # Test duplicate label (idempotent)
            print("\n2.2: Testing duplicate label (should be idempotent)...")
            dup = issue_manager.add_labels(issue_number, "bug")
            assert (
                dup["labels"].count("bug") == 1
            ), "Duplicate label should not be added"
            print(f"✓ Duplicate handling works: {dup['labels']}")

            # Remove labels
            print("\n2.3: Removing labels...")
            removed = issue_manager.remove_labels(issue_number, "bug")
            assert "bug" not in removed["labels"]
            assert "enhancement" in removed["labels"]
            print(f"✓ Removed 'bug' label: {removed['labels']}")

            # Try removing non-existent label (should handle gracefully)
            print("\n2.4: Removing non-existent label (should not error)...")
            try:
                # This should either succeed gracefully or return empty dict
                result = issue_manager.remove_labels(
                    issue_number, "nonexistent-xyz-123"
                )
                # If it returns data, verify the issue wasn't affected
                if result and result.get("number") == issue_number:
                    assert (
                        "enhancement" in result["labels"]
                    ), "Existing labels should remain"
                    print(
                        f"✓ Gracefully handled non-existent label: {result['labels']}"
                    )
                else:
                    # Empty dict means error was caught
                    print("✓ Non-existent label returned empty result (error caught)")
            except Exception as e:  # pylint: disable=broad-exception-caught
                print(f"✓ Non-existent label handling: {e}")

            # Set labels (replace all)
            print("\n2.5: Setting labels (replace all)...")
            set_result = issue_manager.set_labels(
                issue_number, "documentation", "good first issue"
            )
            assert len(set_result["labels"]) == 2
            assert "documentation" in set_result["labels"]
            assert "good first issue" in set_result["labels"]
            assert "enhancement" not in set_result["labels"]  # Old labels removed
            print(f"✓ Set labels (replaced all): {set_result['labels']}")

            # Clear all labels
            print("\n2.6: Clearing all labels...")
            cleared = issue_manager.set_labels(issue_number)
            assert len(cleared["labels"]) == 0
            print("✓ Cleared all labels")

            # Add back test label for later operations
            issue_manager.add_labels(issue_number, "test")
            print("✓ Re-added 'test' label for cleanup identification")

            # ============================================================
            # SECTION 3: Comment Operations
            # ============================================================
            print("\n" + "=" * 60)
            print("SECTION 3: Comment Operations")
            print("=" * 60)

            # Add comment
            print("\n3.1: Adding comment...")
            comment1 = issue_manager.add_comment(issue_number, "First test comment")
            assert comment1["id"] > 0
            assert comment1["body"] == "First test comment"
            comment1_id = comment1["id"]
            print(f"✓ Added comment {comment1_id}")

            # Add second comment
            print("\n3.2: Adding second comment...")
            comment2 = issue_manager.add_comment(issue_number, "Second test comment")
            assert comment2["id"] > 0
            comment2_id = comment2["id"]
            print(f"✓ Added comment {comment2_id}")

            # Get all comments
            print("\n3.3: Retrieving all comments...")
            comments = issue_manager.get_comments(issue_number)
            assert len(comments) >= 2
            comment_ids = [c["id"] for c in comments]
            assert comment1_id in comment_ids
            assert comment2_id in comment_ids
            print(f"✓ Retrieved {len(comments)} comments")

            # Edit comment
            print("\n3.4: Editing comment...")
            edited = issue_manager.edit_comment(
                issue_number, comment1_id, "Updated first comment"
            )
            assert edited["id"] == comment1_id
            assert edited["body"] == "Updated first comment"
            print(f"✓ Edited comment {comment1_id}")

            # Verify edit
            comments_after_edit = issue_manager.get_comments(issue_number)
            edited_comment = next(
                (c for c in comments_after_edit if c["id"] == comment1_id), None
            )
            assert edited_comment is not None
            assert edited_comment["body"] == "Updated first comment"
            print("✓ Verified comment was updated")

            # Delete one comment
            print("\n3.5: Deleting comment...")
            delete_success = issue_manager.delete_comment(issue_number, comment2_id)
            assert delete_success is True
            print(f"✓ Deleted comment {comment2_id}")

            # Verify deletion
            comments_after_delete = issue_manager.get_comments(issue_number)
            remaining_ids = [c["id"] for c in comments_after_delete]
            assert comment2_id not in remaining_ids
            assert comment1_id in remaining_ids  # First comment still exists
            print("✓ Verified comment was deleted")

            # ============================================================
            # SECTION 4: Error Handling (using the same issue)
            # ============================================================
            print("\n" + "=" * 60)
            print("SECTION 4: Error Handling")
            print("=" * 60)

            # Test with invalid comment ID
            print("\n4.1: Trying to edit non-existent comment...")
            invalid_edit = issue_manager.edit_comment(
                issue_number, 999999999, "Should fail"
            )
            assert invalid_edit["id"] == 0, "Should return empty CommentData"
            print("✓ Non-existent comment edit handled correctly")

            # Test with invalid comment ID for deletion
            print("\n4.2: Trying to delete non-existent comment...")
            invalid_delete = issue_manager.delete_comment(issue_number, 999999999)
            assert invalid_delete is False
            print("✓ Non-existent comment deletion handled correctly")

            # Test adding comment with empty body
            print("\n4.3: Trying to add empty comment...")
            with pytest.raises(ValueError, match="Comment body cannot be empty"):
                issue_manager.add_comment(issue_number, "")
            print("✓ Empty comment body validation works")

            # Test adding comment with whitespace only
            print("\n4.4: Trying to add whitespace-only comment...")
            with pytest.raises(ValueError, match="Comment body cannot be empty"):
                issue_manager.add_comment(issue_number, "   \n\t   ")
            print("✓ Whitespace-only comment body validation works")

            # Test editing comment with empty body
            print("\n4.5: Trying to edit comment with empty body...")
            with pytest.raises(ValueError, match="Comment body cannot be empty"):
                issue_manager.edit_comment(issue_number, comment1_id, "")
            # Verify original comment unchanged
            verify_comments = issue_manager.get_comments(issue_number)
            unchanged = next(
                (c for c in verify_comments if c["id"] == comment1_id), None
            )
            assert unchanged is not None
            assert unchanged["body"] == "Updated first comment"
            print("✓ Empty edit body validation works, original unchanged")

            # ============================================================
            # SECTION 5: Issue Lifecycle
            # ============================================================
            print("\n" + "=" * 60)
            print("SECTION 5: Issue Lifecycle")
            print("=" * 60)

            # Close issue
            print("\n5.1: Closing issue...")
            closed = issue_manager.close_issue(issue_number)
            assert closed["state"] == "closed"
            print(f"✓ Closed issue #{issue_number}")

            # Reopen issue
            print("\n5.2: Reopening issue...")
            reopened = issue_manager.reopen_issue(issue_number)
            assert reopened["state"] == "open"
            print(f"✓ Reopened issue #{issue_number}")

            # Final close for cleanup
            print("\n5.3: Final close for cleanup...")
            final_close = issue_manager.close_issue(issue_number)
            assert final_close["state"] == "closed"
            print(f"✓ Final cleanup: Closed issue #{issue_number}")

            # ============================================================
            # SECTION 6: Summary
            # ============================================================
            print("\n" + "=" * 60)
            print("INTEGRATION TEST SUMMARY")
            print("=" * 60)
            print(f"✓ All operations completed successfully on issue #{issue_number}")
            print("  - Issue lifecycle: create → close → reopen → close")
            print("  - Labels: add, remove, set, clear, duplicates, non-existent")
            print("  - Comments: add, get, edit, delete")
            print("  - Error handling: invalid IDs, empty bodies, validation")
            print("\n✓ Integration test PASSED with ONE issue")
            print("=" * 60)

        finally:
            # Cleanup: ensure issue is closed
            if created_issue and "number" in created_issue:
                try:
                    issue_manager.close_issue(created_issue["number"])
                    print(
                        f"\n✓ Cleanup: Ensured issue #{created_issue['number']} is closed"
                    )
                except Exception:  # pylint: disable=broad-exception-caught
                    pass  # Ignore cleanup failures

    def test_error_handling_without_creating_issues(
        self, issue_manager: IssueManager
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
        result = issue_manager.close_issue(non_existent)
        assert result["number"] == 0
        print("✓ close_issue on non-existent issue")

        result = issue_manager.reopen_issue(non_existent)
        assert result["number"] == 0
        print("✓ reopen_issue on non-existent issue")

        result = issue_manager.add_labels(non_existent, "test")
        assert result["number"] == 0
        print("✓ add_labels on non-existent issue")

        result = issue_manager.remove_labels(non_existent, "test")
        assert result["number"] == 0
        print("✓ remove_labels on non-existent issue")

        result = issue_manager.set_labels(non_existent, "test")
        assert result["number"] == 0
        print("✓ set_labels on non-existent issue")

        comment_result = issue_manager.add_comment(non_existent, "test")
        assert comment_result["id"] == 0
        print("✓ add_comment on non-existent issue")

        comments = issue_manager.get_comments(non_existent)
        assert len(comments) == 0
        print("✓ get_comments on non-existent issue")

        # Test with invalid issue numbers
        print("\n2. Testing with invalid issue numbers...")
        with pytest.raises(ValueError, match="Issue number must be a positive integer"):
            issue_manager.close_issue(-1)
        print("✓ Negative issue number")

        with pytest.raises(ValueError, match="Issue number must be a positive integer"):
            issue_manager.close_issue(0)
        print("✓ Zero issue number")

        # Test creating issues with invalid input
        print("\n3. Testing issue creation with invalid input...")
        with pytest.raises(ValueError, match="Issue title cannot be empty"):
            issue_manager.create_issue(title="", body="Valid body")
        print("✓ Empty title")

        with pytest.raises(ValueError, match="Issue title cannot be empty"):
            issue_manager.create_issue(title="   \n\t   ", body="Valid body")
        print("✓ Whitespace-only title")

        print("\n✓ All error handling tests passed (0 issues created)")
        print("=" * 60)
