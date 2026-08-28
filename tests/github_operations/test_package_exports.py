"""Package-level export tests for mcp_workspace.github_operations.

Pure import tests (no external resources) verifying the public API surface.
"""

import mcp_workspace.github_operations as github_operations
from mcp_workspace.github_operations import (
    IssueIdentityMismatchError,
    MergeResult,
    PullRequestData,
)


def test_merge_result_and_pr_data_exported() -> None:
    """MergeResult and PullRequestData are importable and in __all__."""
    assert MergeResult is not None
    assert PullRequestData is not None
    assert "MergeResult" in github_operations.__all__
    assert "PullRequestData" in github_operations.__all__


def test_issue_identity_mismatch_error_exported() -> None:
    """IssueIdentityMismatchError is importable, a ValueError, and in __all__."""
    assert IssueIdentityMismatchError is not None
    assert issubclass(IssueIdentityMismatchError, ValueError)
    assert "IssueIdentityMismatchError" in github_operations.__all__
