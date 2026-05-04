"""Branch management operations for GitHub issues."""

import logging
import re
import time
from pathlib import Path
from typing import Any, List, Optional, cast

from github import GithubException
from mcp_coder_utils.log_utils import log_function_call

from ..base_manager import BaseGitHubManager, _handle_github_errors
from .branch_naming import BranchCreationResult, generate_branch_name_from_issue

# Configure logger for GitHub operations
logger = logging.getLogger(__name__)

# createLinkedBranch retry config — handles GitHub's eventual-consistency
# flake where the mutation succeeds but the response omits linkedBranch.ref.
_CREATE_LINKED_BRANCH_MAX_ATTEMPTS = 3
_CREATE_LINKED_BRANCH_RETRY_BASE_DELAY_SECONDS = 1.0


class IssueBranchManager(BaseGitHubManager):
    """Manages GitHub issue-branch linking operations using GraphQL API.

    This class provides methods for creating, querying, and managing
    branch-issue associations that appear in GitHub's "Development" section.

    Configuration:
        Requires GitHub token in config file (~/.mcp_coder/config.toml):

        [github]
        token = "ghp_your_personal_access_token_here"

        Token needs 'repo' scope for private repositories, 'public_repo' for public.
    """

    def __init__(
        self, project_dir: Optional[Path] = None, repo_url: Optional[str] = None
    ) -> None:
        """Initialize the IssueBranchManager.

        Args:
            project_dir: Path to the project directory containing git repository
            repo_url: GitHub repository URL (e.g., "https://github.com/user/repo.git")

        """
        super().__init__(project_dir=project_dir, repo_url=repo_url)

    def _validate_issue_number(self, issue_number: int) -> bool:
        """Validate issue number.

        Args:
            issue_number: Issue number to validate

        Returns:
            True if valid, False otherwise
        """
        if not isinstance(issue_number, int) or issue_number <= 0:
            logger.error(
                f"Invalid issue number: {issue_number}. Must be a positive integer."
            )
            return False
        return True

    @staticmethod
    def _extract_prs_by_states(
        timeline_items: List[dict[str, Any]],
        states: set[str],
    ) -> List[dict[str, Any]]:
        """Extract PRs matching given states from timeline items.

        Args:
            timeline_items: List of timeline item nodes from GraphQL response
            states: Set of PR states to include (e.g. {"OPEN"}, {"CLOSED"})

        Returns:
            List of PR source objects whose state is in the given set
        """
        matched_prs = []
        for node in timeline_items:
            if not node or node.get("__typename") != "CrossReferencedEvent":
                continue

            source = node.get("source")
            if not source:
                continue

            # Check if source is a PR (has PR-specific fields)
            if "state" not in source or "headRefName" not in source:
                continue

            if source["state"] in states:
                matched_prs.append(source)

        return matched_prs

    def _search_branches_by_pattern(
        self,
        issue_number: int,
        repo: Any,
    ) -> Optional[str]:
        """Search for branches matching an issue number pattern.

        Uses a two-pass strategy:
        1. Prefix match (cheap) - catches "123-foo" style branches
        2. Full scan fallback - catches "feature/123-foo" style branches

        Args:
            issue_number: Issue number to search for
            repo: PyGithub Repository object

        Returns:
            Branch name if exactly one match found, None otherwise
        """
        pattern = re.compile(r"(^|/)" + str(issue_number) + r"[-_]")

        # Pass 1: prefix match (cheap, catches "123-foo" style)
        refs = list(repo.get_git_matching_refs(f"heads/{issue_number}"))
        matches: list[str] = [
            cast(str, ref.ref.removeprefix("refs/heads/"))
            for ref in refs
            if pattern.search(ref.ref.removeprefix("refs/heads/"))
        ]
        if len(matches) == 1:
            logger.info(
                f"Issue #{issue_number}: Found branch via pattern match: {matches[0]}"
            )
            return matches[0]
        if len(matches) > 1:
            logger.warning(
                f"Issue #{issue_number}: Ambiguous branch pattern match: {matches}"
            )
            return None

        # Pass 2: full scan fallback (catches "feature/123-foo" style)
        all_refs = list(repo.get_git_matching_refs("heads/"))
        if len(all_refs) > 500:
            logger.warning(
                f"Issue #{issue_number}: Repository has {len(all_refs)} branches, "
                f"only scanning first 500"
            )
            all_refs = all_refs[:500]

        matches = [
            cast(str, ref.ref.removeprefix("refs/heads/"))
            for ref in all_refs
            if pattern.search(ref.ref.removeprefix("refs/heads/"))
        ]
        if len(matches) == 1:
            logger.info(
                f"Issue #{issue_number}: Found branch via full scan pattern match: {matches[0]}"
            )
            return matches[0]
        if len(matches) > 1:
            logger.warning(
                f"Issue #{issue_number}: Ambiguous branch pattern match in full scan: {matches}"
            )
            return None

        return None

    @log_function_call
    @_handle_github_errors(default_return=[])
    def get_linked_branches(self, issue_number: int) -> List[str]:
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
        # Validate issue number
        if not self._validate_issue_number(issue_number):
            return []

        # Get repository
        repo = self._get_repository()
        if repo is None:
            logger.error("Failed to get repository")
            return []

        # Extract owner and repo name
        owner, repo_name = repo.owner.login, repo.name

        # GraphQL query for linked branches
        query = """
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

        variables = {
            "owner": owner,
            "repo": repo_name,
            "issueNumber": issue_number,
        }

        # Execute GraphQL query
        # Note: Using private attribute is the documented way to access GraphQL in PyGithub
        # graphql_query returns (headers, data) tuple - we only need data
        _, result = self._github_client._Github__requester.graphql_query(  # type: ignore[attr-defined]  # pylint: disable=protected-access  # no public GraphQL API in PyGithub
            query=query, variables=variables
        )

        # Parse response
        try:
            issue_data = result.get("data", {}).get("repository", {}).get("issue")
            if issue_data is None:
                logger.warning(f"Issue #{issue_number} not found")
                return []

            linked_branches = issue_data.get("linkedBranches", {}).get("nodes", [])
            branch_names = [
                node["ref"]["name"]
                for node in linked_branches
                if node and node.get("ref")
            ]
            return branch_names

        except (KeyError, TypeError) as e:
            logger.error(f"Error parsing GraphQL response: {e}")
            return []

    @log_function_call
    @_handle_github_errors(
        default_return=BranchCreationResult(
            success=False, branch_name="", error=None, existing_branches=[]
        )
    )
    def create_remote_branch_for_issue(
        self,
        issue_number: int,
        branch_name: Optional[str] = None,
        base_branch: Optional[str] = None,
        allow_multiple: bool = False,
    ) -> BranchCreationResult:
        """Create and link branch to issue via GraphQL.

        Args:
            issue_number: Issue number to link branch to
            branch_name: Custom branch name (optional, auto-generated if not provided)
            base_branch: Base branch to branch from (optional, uses default branch if not provided)
            allow_multiple: If False (default), blocks if issue has any linked branches.
                           If True, allows multiple branches per issue.

        Returns:
            BranchCreationResult with success status, branch name, error, and existing branches

        Example:
            >>> manager = IssueBranchManager(Path.cwd())
            >>> result = manager.create_remote_branch_for_issue(123)
            >>> if result["success"]:
            ...     print(f"Created branch: {result['branch_name']}")
            ... else:
            ...     print(f"Error: {result['error']}")
        """
        # Validate issue number
        if not self._validate_issue_number(issue_number):
            return BranchCreationResult(
                success=False,
                branch_name="",
                error="Invalid issue number. Must be a positive integer.",
                existing_branches=[],
            )

        # Get repository
        repo = self._get_repository()
        if repo is None:
            logger.error("Failed to get repository")
            return BranchCreationResult(
                success=False,
                branch_name="",
                error="Failed to get repository",
                existing_branches=[],
            )

        # Step 1: Check for existing branches if allow_multiple=False
        if not allow_multiple:
            existing_branches = self.get_linked_branches(issue_number)
            if existing_branches:
                error_msg = (
                    f"Issue #{issue_number} already has linked branches. "
                    f"Use allow_multiple=True to create additional branches."
                )
                logger.warning(error_msg)
                return BranchCreationResult(
                    success=False,
                    branch_name="",
                    error=error_msg,
                    existing_branches=existing_branches,
                )

        # Step 2: Get issue to access node_id and title
        issue = repo.get_issue(issue_number)

        # Step 3: Generate branch name if not provided
        if branch_name is None:
            branch_name = generate_branch_name_from_issue(issue_number, issue.title)

        # Step 4: Get base commit SHA
        base_branch_name = base_branch if base_branch else repo.default_branch
        branch = repo.get_branch(base_branch_name)
        base_commit_sha = branch.commit.sha

        # Step 5: Execute createLinkedBranch mutation
        mutation_input = {
            "issueId": issue.node_id,
            "repositoryId": repo.node_id,
            "oid": base_commit_sha,
            "name": branch_name,
        }

        # Step 6: Run mutation with retry-on-missing-ref (eventual-consistency flake)
        last_result: Optional[BranchCreationResult] = None
        for attempt in range(_CREATE_LINKED_BRANCH_MAX_ATTEMPTS):
            # Execute GraphQL mutation
            # Note: Using private attribute is the documented way to access GraphQL in PyGithub
            # graphql_named_mutation returns (headers, data) tuple - we only need data
            _, result = self._github_client._Github__requester.graphql_named_mutation(  # type: ignore[attr-defined]  # pylint: disable=protected-access  # no public GraphQL API in PyGithub
                mutation_name="createLinkedBranch",
                mutation_input=mutation_input,
                output_schema="linkedBranch { id ref { name target { oid } } }",
            )

            last_result, retryable = self._parse_create_linked_branch_response(
                result, issue_number
            )
            if last_result.get("success") or not retryable:
                return last_result

            if attempt < _CREATE_LINKED_BRANCH_MAX_ATTEMPTS - 1:
                delay = _CREATE_LINKED_BRANCH_RETRY_BASE_DELAY_SECONDS * (2**attempt)
                logger.warning(
                    "createLinkedBranch returned no ref for issue #%d "
                    "(attempt %d/%d); retrying in %.1fs",
                    issue_number,
                    attempt + 1,
                    _CREATE_LINKED_BRANCH_MAX_ATTEMPTS,
                    delay,
                )
                time.sleep(delay)

        # Retries exhausted — last_result holds the final failure
        assert last_result is not None
        return last_result

    @staticmethod
    def _parse_create_linked_branch_response(
        result: Any, issue_number: int
    ) -> tuple[BranchCreationResult, bool]:
        """Parse the createLinkedBranch GraphQL response.

        Returns ``(result, retryable)``. ``retryable`` is True only for the
        eventual-consistency case where the mutation appears to succeed but the
        response omits ``linkedBranch.ref`` — all other failures are permanent.
        """
        try:
            if not isinstance(result, dict):
                error_msg = (
                    "Failed to create linked branch: Malformed response from GitHub"
                )
                logger.error(error_msg)
                logger.debug(f"GraphQL mutation response: {result}")
                return (
                    BranchCreationResult(
                        success=False,
                        branch_name="",
                        error=error_msg,
                        existing_branches=[],
                    ),
                    False,
                )

            if "errors" in result:
                errors = result["errors"]
                error_msg = f"Failed to create linked branch: {errors}"
                logger.error(error_msg)
                logger.debug(f"GraphQL mutation response: {result}")
                return (
                    BranchCreationResult(
                        success=False,
                        branch_name="",
                        error=error_msg,
                        existing_branches=[],
                    ),
                    False,
                )

            # PyGithub returns the inner content directly, not wrapped in mutation name
            if "linkedBranch" in result:
                linked_branch = result["linkedBranch"]
            elif (
                "createLinkedBranch" in result
                and "linkedBranch" in result["createLinkedBranch"]
            ):
                linked_branch = result["createLinkedBranch"]["linkedBranch"]
            else:
                error_details = (
                    f"Full response: {result}, "
                    f"Available keys: {list(result.keys())}"
                )
                error_msg = (
                    f"Failed to create linked branch: Invalid response from GitHub. "
                    f"Details: {error_details}"
                )
                logger.error(error_msg)
                return (
                    BranchCreationResult(
                        success=False,
                        branch_name="",
                        error=error_msg,
                        existing_branches=[],
                    ),
                    False,
                )

            if linked_branch is None or "ref" not in linked_branch:
                error_msg = "Failed to create linked branch: Missing branch reference in response"
                logger.debug(f"GraphQL mutation response: {result}")
                return (
                    BranchCreationResult(
                        success=False,
                        branch_name="",
                        error=error_msg,
                        existing_branches=[],
                    ),
                    True,
                )

            created_branch_name = linked_branch["ref"]["name"]

            logger.info(
                f"Successfully created and linked branch '{created_branch_name}' to issue #{issue_number}",
            )
            return (
                BranchCreationResult(
                    success=True,
                    branch_name=created_branch_name,
                    error=None,
                    existing_branches=[],
                ),
                False,
            )

        except (KeyError, TypeError) as e:
            error_msg = f"Error parsing GraphQL mutation response: {e}"
            logger.error(error_msg)
            return (
                BranchCreationResult(
                    success=False,
                    branch_name="",
                    error=error_msg,
                    existing_branches=[],
                ),
                False,
            )

    @log_function_call
    @_handle_github_errors(default_return=None)
    def get_branch_with_pr_fallback(
        self, issue_number: int, repo_owner: str, repo_name: str
    ) -> Optional[str]:
        """Get branch for issue using a 4-step resolution strategy.

        Resolution order:
        1. Linked branches via GitHub's linked-branch API (fast)
        2. Open PRs mentioning the issue in the timeline
        3. Closed PRs whose branch still exists (most recent first)
        4. Pattern-matching branch names by issue number

        Returns the first unambiguous match. Steps 1, 2, and 4 treat
        multiple matches as ambiguous (returns None). Step 3 returns
        the most recent closed PR whose branch still exists.

        Args:
            issue_number: Issue number to find branch for
            repo_owner: Repository owner (e.g., "anthropics")
            repo_name: Repository name (e.g., "mcp-coder")

        Returns:
            Branch name if found, None otherwise
        """
        # Step 1: Validate issue number
        if not self._validate_issue_number(issue_number):
            logger.debug(f"Invalid issue number: {issue_number}")
            return None

        # Step 2: Get repository
        repo = self._get_repository()
        if repo is None:
            logger.warning("Failed to get repository for branch resolution")
            return None

        # Step 3: Try primary path - query linkedBranches (fast)
        linked_branches = self.get_linked_branches(issue_number)
        if len(linked_branches) == 1:
            branch_name = linked_branches[0]
            logger.debug(
                f"Issue #{issue_number}: Found branch via linkedBranches: {branch_name}"
            )
            return branch_name
        if len(linked_branches) > 1:
            logger.warning(
                f"Issue #{issue_number}: Multiple linked branches found: "
                f"{linked_branches}. Cannot determine which branch to use."
            )
            return None

        # Step 4: Fallback - query issue timeline for PRs
        logger.debug(
            f"Issue #{issue_number}: No linkedBranches found, querying PR timeline"
        )

        query = """
        query($owner: String!, $repo: String!, $issueNumber: Int!) {
          repository(owner: $owner, name: $repo) {
            issue(number: $issueNumber) {
              timelineItems(itemTypes: [CROSS_REFERENCED_EVENT], first: 100) {
                nodes {
                  __typename
                  ... on CrossReferencedEvent {
                    source {
                      ... on PullRequest {
                        number
                        state
                        isDraft
                        headRefName
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """

        variables = {
            "owner": repo_owner,
            "repo": repo_name,
            "issueNumber": issue_number,
        }

        # Execute GraphQL query
        _, result = self._github_client._Github__requester.graphql_query(  # type: ignore[attr-defined]  # pylint: disable=protected-access  # no public GraphQL API in PyGithub
            query=query, variables=variables
        )

        # Step 5: Parse response and filter for OPEN PRs
        try:
            data = result.get("data")
            if data is None:
                logger.debug(f"Issue #{issue_number}: Malformed GraphQL response")
                return None

            repository = data.get("repository")
            if repository is None:
                logger.debug(f"Issue #{issue_number}: Repository not found")
                return None

            issue_data = repository.get("issue")
            if issue_data is None:
                logger.debug(f"Issue #{issue_number}: Issue not found")
                return None

            timeline_items = issue_data.get("timelineItems", {}).get("nodes", [])

            if len(timeline_items) == 100:
                logger.debug(
                    f"Issue #{issue_number}: Retrieved 100 timeline items (API limit reached, may be truncated)"
                )

            # Filter for OPEN PRs using helper method
            open_prs = self._extract_prs_by_states(timeline_items, {"OPEN"})

            # Step 6: Handle open PR results
            if len(open_prs) == 1:
                pr_data: dict[str, Any] = open_prs[0]
                branch_name = cast(str, pr_data["headRefName"])
                pr_number = pr_data["number"]
                is_draft = pr_data.get("isDraft", False)
                pr_type = "draft" if is_draft else "open"
                logger.debug(
                    f"Issue #{issue_number}: Found branch via {pr_type} PR #{pr_number}: {branch_name}"
                )
                return branch_name

            if len(open_prs) > 1:
                pr_numbers = [pr["number"] for pr in open_prs]
                logger.warning(
                    f"Issue #{issue_number}: Multiple open PRs found: {pr_numbers}. "
                    f"Cannot determine which branch to use."
                )
                return None

            # Step 7: Closed PR fallback
            logger.debug(
                f"Issue #{issue_number}: No open PRs found, checking closed PRs"
            )
            closed_prs = self._extract_prs_by_states(timeline_items, {"CLOSED"})
            closed_prs.sort(key=lambda pr: pr["number"], reverse=True)
            branch_checks = 0
            for pr in closed_prs:
                if branch_checks >= 25:
                    logger.debug(
                        f"Issue #{issue_number}: Reached 25 branch check limit "
                        f"for closed PRs"
                    )
                    break
                branch_checks += 1
                try:
                    repo.get_branch(cast(str, pr["headRefName"]))
                    branch_name = cast(str, pr["headRefName"])
                    logger.debug(
                        f"Issue #{issue_number}: Found branch via closed "
                        f"PR #{pr['number']}: {branch_name}"
                    )
                    return branch_name
                except GithubException:
                    continue

            # Step 8: Pattern search fallback
            return self._search_branches_by_pattern(issue_number, repo)

        except (KeyError, TypeError) as e:
            logger.error(f"Issue #{issue_number}: Error parsing timeline response: {e}")
            return None

    @log_function_call
    @_handle_github_errors(default_return=False)
    def delete_linked_branch(self, issue_number: int, branch_name: str) -> bool:
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
        if not self._validate_issue_number(issue_number):
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
        query = """
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

        variables = {
            "owner": owner,
            "repo": repo_name,
            "issueNumber": issue_number,
        }

        # Execute GraphQL query
        _, result = self._github_client._Github__requester.graphql_query(  # type: ignore[attr-defined]  # pylint: disable=protected-access  # no public GraphQL API in PyGithub
            query=query, variables=variables
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
