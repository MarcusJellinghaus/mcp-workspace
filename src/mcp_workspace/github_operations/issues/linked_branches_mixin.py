"""Linked-branch mixin for IssueBranchManager.

This module provides the LinkedBranchesMixin class containing the GraphQL
operations that read an issue's linked branches and unlink a branch from an
issue, plus the issue-number validation helper they share with the manager.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from mcp_coder_utils.log_utils import log_function_call

from ..base_manager import BaseGitHubManager, _handle_github_errors
from .base import validate_issue_number_or_log

logger = logging.getLogger(__name__)

__all__ = ["LinkedBranchesMixin"]

# GraphQL query returning the ref names of an issue's linked branches.
_LINKED_BRANCHES_QUERY = """
query($owner: String!, $repo: String!, $issueNumber: Int!) {
  repository(owner: $owner, name: $repo) {
    issue(number: $issueNumber) {
      linkedBranches(first: 100) {
        nodes {
          ref {
            name
          }
        }
      }
    }
  }
}
"""

# Same query plus the linkedBranch ids the deleteLinkedBranch mutation needs.
_LINKED_BRANCHES_WITH_IDS_QUERY = """
query($owner: String!, $repo: String!, $issueNumber: Int!) {
  repository(owner: $owner, name: $repo) {
    issue(number: $issueNumber) {
      linkedBranches(first: 100) {
        nodes {
          id
          ref {
            name
          }
        }
      }
    }
  }
}
"""


def _query_linked_branches(
    manager: BaseGitHubManager, issue_number: int
) -> Optional[List[str]]:
    """Query linked branches for an issue via GraphQL, undecorated.

    Failure is signalled with a None sentinel rather than an exception, so
    that the decorated get_linked_branches() wrapper keeps its exact
    behaviour and logging (a ValueError would be re-raised by
    _handle_github_errors, and any other type would add a spurious
    "Unexpected error" log line to the invalid-issue-number path).

    Args:
        manager: Manager providing repository access and the GitHub client
        issue_number: Issue number to query linked branches for

    Returns:
        List of branch names on success (possibly empty), or None when the
        lookup could not be completed
    """
    # Validate issue number
    if not validate_issue_number_or_log(issue_number):
        return None

    # Get repository
    repo = manager._get_repository()
    if repo is None:
        logger.error("Failed to get repository")
        return None

    # Extract owner and repo name
    owner, repo_name = repo.owner.login, repo.name

    variables = {
        "owner": owner,
        "repo": repo_name,
        "issueNumber": issue_number,
    }

    # Execute GraphQL query
    # Note: Using private attribute is the documented way to access GraphQL in PyGithub
    # graphql_query returns (headers, data) tuple - we only need data
    _, result = manager._github_client._Github__requester.graphql_query(  # type: ignore[attr-defined]  # pylint: disable=protected-access  # no public GraphQL API in PyGithub
        query=_LINKED_BRANCHES_QUERY, variables=variables
    )

    # Parse response
    try:
        issue_data = result.get("data", {}).get("repository", {}).get("issue")
        if issue_data is None:
            logger.warning(f"Issue #{issue_number} not found")
            return None

        linked_branches = issue_data.get("linkedBranches", {}).get("nodes", [])
        branch_names = [
            node["ref"]["name"] for node in linked_branches if node and node.get("ref")
        ]
        return branch_names

    except (KeyError, TypeError) as e:
        logger.error(f"Error parsing GraphQL response: {e}")
        return None


class LinkedBranchesMixin:
    """Mixin providing an issue's linked-branch query and unlink operations.

    This mixin is designed to be used with BaseGitHubManager.
    """

    @log_function_call
    @_handle_github_errors(default_return=[])
    def get_linked_branches(self: "BaseGitHubManager", issue_number: int) -> List[str]:
        """Query linked branches for an issue via GraphQL.

        Args:
            issue_number: Issue number to query linked branches for

        Returns:
            List of branch names linked to the issue, or empty list on error

        Example:
            >>> manager = IssueBranchManager(Path.cwd())
            >>> branches = manager.get_linked_branches(123)
            >>> print(f"Linked branches: {branches}")
            ['123-feature-branch', '123-hotfix']
        """
        branch_names = _query_linked_branches(self, issue_number)
        return [] if branch_names is None else branch_names

    @log_function_call
    def get_linked_branches_or_none(
        self: "BaseGitHubManager", issue_number: int
    ) -> Optional[List[str]]:
        """Query linked branches for an issue, distinguishing failure from none.

        Unlike get_linked_branches(), a failed lookup returns None instead of
        an empty list, so callers can tell "this issue has no linked branch"
        ([]) apart from "the linked branch could not be determined" (None).

        Auth errors (401/403) are reported as None rather than re-raised: for
        callers of this method an auth failure is simply an undeterminable
        lookup.

        Args:
            issue_number: Issue number to query linked branches for

        Returns:
            List of branch names on success (possibly empty), or None when the
            lookup could not be completed

        Example:
            >>> manager = IssueBranchManager(Path.cwd())
            >>> manager.get_linked_branches_or_none(123)
            ['123-feature-branch']
        """
        try:
            return _query_linked_branches(self, issue_number)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error(f"Failed to query linked branches for #{issue_number}: {e}")
            return None

    @log_function_call
    @_handle_github_errors(default_return=False)
    def delete_linked_branch(
        self: "BaseGitHubManager", issue_number: int, branch_name: str
    ) -> bool:
        """Unlink branch from issue (doesn't delete Git branch).

        Args:
            issue_number: Issue number to unlink branch from
            branch_name: Name of the branch to unlink

        Returns:
            True if successfully unlinked, False otherwise

        Example:
            >>> manager = IssueBranchManager(Path.cwd())
            >>> success = manager.delete_linked_branch(123, "123-feature-branch")
            >>> if success:
            ...     print("Branch unlinked successfully")
            ... else:
            ...     print("Failed to unlink branch")
        """
        # Step 1: Validate inputs
        if not validate_issue_number_or_log(issue_number):
            return False

        if not branch_name or not branch_name.strip():
            logger.error("Branch name cannot be empty")
            return False

        # Step 2: Get repository
        repo = self._get_repository()
        if repo is None:
            logger.error("Failed to get repository")
            return False

        # Extract owner and repo name
        owner, repo_name = repo.owner.login, repo.name

        # Step 3: Query linked branches to get linkedBranch.id
        variables = {
            "owner": owner,
            "repo": repo_name,
            "issueNumber": issue_number,
        }

        # Execute GraphQL query
        _, result = self._github_client._Github__requester.graphql_query(  # type: ignore[attr-defined]  # pylint: disable=protected-access  # no public GraphQL API in PyGithub
            query=_LINKED_BRANCHES_WITH_IDS_QUERY, variables=variables
        )

        # Step 4: Find matching branch by name and extract its ID
        try:
            issue_data = result.get("data", {}).get("repository", {}).get("issue")
            if issue_data is None:
                logger.warning(f"Issue #{issue_number} not found")
                return False

            linked_branches = issue_data.get("linkedBranches", {}).get("nodes", [])

            # Find the branch with matching name
            linked_branch_id = None
            for node in linked_branches:
                if node and node.get("ref") and node["ref"].get("name") == branch_name:
                    linked_branch_id = node.get("id")
                    break

            # Step 5: If not found, log warning and return False
            if linked_branch_id is None:
                logger.warning(
                    f"Branch '{branch_name}' is not linked to issue #{issue_number}"
                )
                return False

            # Step 6: Execute deleteLinkedBranch mutation
            mutation_input = {"linkedBranchId": linked_branch_id}

            _, _ = self._github_client._Github__requester.graphql_named_mutation(  # type: ignore[attr-defined]  # pylint: disable=protected-access  # no public GraphQL API in PyGithub
                mutation_name="deleteLinkedBranch",
                mutation_input=mutation_input,
                output_schema="clientMutationId",
            )

            logger.info(
                f"Successfully unlinked branch '{branch_name}' from issue #{issue_number}",
            )
            return True

        except (KeyError, TypeError) as e:
            logger.error(f"Error parsing GraphQL response: {e}")
            return False
