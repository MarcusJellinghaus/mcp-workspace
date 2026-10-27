"""Branch management operations for GitHub issues."""

import logging
import re
import time
from pathlib import Path
from typing import Any, List, Optional, cast

from github import GithubException
from mcp_coder_utils.log_utils import log_function_call

from ..base_manager import BaseGitHubManager, _handle_github_errors
from ..caching.errors import graphql_rate_limit_error
from .base import validate_issue_number_or_log
from .branch_naming import BranchCreationResult, generate_branch_name_from_issue
from .linked_branches_mixin import LinkedBranchesMixin, _query_linked_branches
from .types import BranchLookup

__all__ = ["BranchLookup", "BranchLookupError", "IssueBranchManager"]

# Configure logger for GitHub operations
logger = logging.getLogger(__name__)

# createLinkedBranch retry config — handles GitHub's eventual-consistency
# flake where the mutation succeeds but the response omits linkedBranch.ref.
_CREATE_LINKED_BRANCH_MAX_ATTEMPTS = 3
_CREATE_LINKED_BRANCH_RETRY_BASE_DELAY_SECONDS = 1.0

# Issue timeline query used by the open/closed-PR fallback of branch resolution.
_TIMELINE_PRS_QUERY = """
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


class BranchLookupError(Exception):
    """Branch resolution could not be completed (not a GitHub 'no branch' answer)."""


class IssueBranchManager(LinkedBranchesMixin, BaseGitHubManager):
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
        self,
        project_dir: Optional[Path] = None,
        repo_url: Optional[str] = None,
        github_token: Optional[str] = None,
    ) -> None:
        """Initialize the IssueBranchManager.

        Args:
            project_dir: Path to the project directory containing git repository
            repo_url: GitHub repository URL (e.g., "https://github.com/user/repo.git")
            github_token: Optional explicit token — overrides config lookup when provided.

        """
        super().__init__(
            project_dir=project_dir,
            repo_url=repo_url,
            github_token=github_token,
        )

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

        Args:
            issue_number: Issue number to search for
            repo: PyGithub Repository object

        Returns:
            Branch name if exactly one match found, None otherwise
        """
        return self._pattern_lookup(issue_number, repo).branch

    def _pattern_lookup(self, issue_number: int, repo: Any) -> BranchLookup:
        """Search for branches matching an issue number pattern.

        Uses a two-pass strategy:
        1. Prefix match (cheap) - catches "123-foo" style branches
        2. Full scan fallback - catches "feature/123-foo" style branches

        Args:
            issue_number: Issue number to search for
            repo: PyGithub Repository object

        Returns:
            ``found`` for exactly one match, ``ambiguous`` for several,
            ``not_found`` for none
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
            return BranchLookup("found", matches[0])
        if len(matches) > 1:
            logger.warning(
                f"Issue #{issue_number}: Ambiguous branch pattern match: {matches}"
            )
            return BranchLookup("ambiguous")

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
            return BranchLookup("found", matches[0])
        if len(matches) > 1:
            logger.warning(
                f"Issue #{issue_number}: Ambiguous branch pattern match in full scan: {matches}"
            )
            return BranchLookup("ambiguous")

        return BranchLookup("not_found")

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

        Raises:
            IssueIdentityMismatchError: If GitHub returns an issue from another
                repository (the issue was transferred) or with a different number.

        Example:
            >>> manager = IssueBranchManager(Path.cwd())
            >>> result = manager.create_remote_branch_for_issue(123)
            >>> if result["success"]:
            ...     print(f"Created branch: {result['branch_name']}")
            ... else:
            ...     print(f"Error: {result['error']}")
        """  # noqa: DOC502  # IssueIdentityMismatchError comes from _get_issue_checked
        # Validate issue number
        if not validate_issue_number_or_log(issue_number):
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
        issue = self._get_issue_checked(repo, issue_number)

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
            if last_result.get("success"):
                self._invalidate_branch_cache(issue_number)
                return last_result
            if not retryable:
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

    def _invalidate_branch_cache(self, issue_number: int) -> None:
        """Drop the issue's branch-lookup cache entry. Never raises."""
        # Function-local import avoids the load-time cycle
        # issues/_cache_io -> caching._store / caching.branches -> issues
        from ..caching.branches import (  # pylint: disable=import-outside-toplevel
            invalidate_branch_entry,
        )

        try:
            repo_identifier = self.repo_identifier
        except ValueError as e:
            logger.warning(f"Skipping branch cache invalidation: {e}")
            return
        invalidate_branch_entry(repo_identifier, issue_number)

    @staticmethod
    def _parse_create_linked_branch_response(
        result: Any, issue_number: int
    ) -> tuple[BranchCreationResult, bool]:
        """Parse the createLinkedBranch GraphQL response.

        Returns:
            ``(result, retryable)``. ``retryable`` is True only for the
            eventual-consistency case where the mutation appears to succeed
            but the response omits ``linkedBranch.ref`` — all other failures
            are permanent.
        """

        def _fail(
            msg: str, retryable: bool = False, log_level: int = logging.ERROR
        ) -> tuple[BranchCreationResult, bool]:
            logger.log(log_level, msg)
            logger.debug(f"GraphQL mutation response: {result}")
            return (
                BranchCreationResult(
                    success=False, branch_name="", error=msg, existing_branches=[]
                ),
                retryable,
            )

        try:
            if not isinstance(result, dict):
                return _fail(
                    "Failed to create linked branch: Malformed response from GitHub"
                )

            if "errors" in result:
                return _fail(f"Failed to create linked branch: {result['errors']}")

            # PyGithub returns the inner content directly, not wrapped in mutation name
            if "linkedBranch" in result:
                linked_branch = result["linkedBranch"]
            elif (
                "createLinkedBranch" in result
                and "linkedBranch" in result["createLinkedBranch"]
            ):
                linked_branch = result["createLinkedBranch"]["linkedBranch"]
            else:
                return _fail(
                    f"Failed to create linked branch: Invalid response from GitHub. "
                    f"Details: Full response: {result}, "
                    f"Available keys: {list(result.keys())}"
                )

            if linked_branch is None or "ref" not in linked_branch:
                return _fail(
                    "Failed to create linked branch: Missing branch reference in response",
                    retryable=True,
                    log_level=logging.DEBUG,
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
            return _fail(f"Error parsing GraphQL mutation response: {e}")

    @log_function_call
    @_handle_github_errors(default_return=None)
    def get_branch_with_pr_fallback(
        self, issue_number: int, repo_owner: str, repo_name: str
    ) -> Optional[str]:
        """Get branch for issue using a 4-step resolution strategy.

        Wraps resolve_branch_for_issue(): ambiguous, not-found and
        incomplete lookups all return None.

        Args:
            issue_number: Issue number to find branch for
            repo_owner: Repository owner (e.g., "anthropics")
            repo_name: Repository name (e.g., "mcp-coder")

        Returns:
            Branch name if found, None otherwise
        """
        if not validate_issue_number_or_log(issue_number):
            logger.debug(f"Invalid issue number: {issue_number}")
            return None

        try:
            return self.resolve_branch_for_issue(
                issue_number, repo_owner, repo_name
            ).branch
        except BranchLookupError as e:
            logger.debug(f"Issue #{issue_number}: Branch resolution incomplete: {e}")
            return None

    def _fetch_linked_branches(self, issue_number: int) -> list[str]:
        """Query the issue's linked branches, raising when they cannot be determined.

        Args:
            issue_number: Issue number to query linked branches for

        Returns:
            Linked branch names (possibly empty)

        Raises:
            BranchLookupError: If the linked-branch query could not be completed.
        """
        branch_names = _query_linked_branches(self, issue_number)
        if branch_names is None:
            raise BranchLookupError(
                f"Issue #{issue_number}: Linked-branch query could not be completed"
            )
        return branch_names

    def resolve_branch_for_issue(
        self, issue_number: int, repo_owner: str, repo_name: str
    ) -> BranchLookup:
        """Resolve the branch for an issue using a 4-step strategy, undecorated.

        Resolution order:
        1. Linked branches via GitHub's linked-branch API (fast)
        2. Open PRs mentioning the issue in the timeline
        3. Closed PRs whose branch still exists (most recent first)
        4. Pattern-matching branch names by issue number

        Returns the first unambiguous match. Steps 1, 2, and 4 treat
        multiple matches as ambiguous. Step 3 returns the most recent
        closed PR whose branch still exists.

        Unlike get_branch_with_pr_fallback(), every error raises, so a
        failed lookup is never mistaken for "no branch".

        Args:
            issue_number: Issue number to find branch for
            repo_owner: Repository owner (e.g., "anthropics")
            repo_name: Repository name (e.g., "mcp-coder")

        Returns:
            BranchLookup with status ``found``, ``not_found`` or ``ambiguous``

        Raises:
            ValueError: If the issue number is invalid.
            BranchLookupError: If the repository or a GraphQL response is
                unavailable or malformed.
            GitHubRateLimitError: If a GraphQL response reports a rate limit.
            GithubException: On any GitHub API error other than a closed-PR
                branch probe returning 404.
        """  # noqa: DOC502  # GithubException propagates from PyGithub calls
        # Step 1: Validate issue number
        if not validate_issue_number_or_log(issue_number):
            raise ValueError(f"Invalid issue number: {issue_number}")

        # Step 2: Get repository
        repo = self._get_repository()
        if repo is None:
            logger.warning("Failed to get repository for branch resolution")
            raise BranchLookupError("Failed to get repository for branch resolution")

        # Step 3: Try primary path - query linkedBranches (fast)
        linked_branches = self._fetch_linked_branches(issue_number)
        if len(linked_branches) == 1:
            branch_name = linked_branches[0]
            logger.debug(
                f"Issue #{issue_number}: Found branch via linkedBranches: {branch_name}"
            )
            return BranchLookup("found", branch_name)
        if len(linked_branches) > 1:
            logger.warning(
                f"Issue #{issue_number}: Multiple linked branches found: "
                f"{linked_branches}. Cannot determine which branch to use."
            )
            return BranchLookup("ambiguous")

        # Step 4: Fallback - query issue timeline for PRs
        logger.debug(
            f"Issue #{issue_number}: No linkedBranches found, querying PR timeline"
        )

        variables = {
            "owner": repo_owner,
            "repo": repo_name,
            "issueNumber": issue_number,
        }

        # Execute GraphQL query
        _, result = self._github_client._Github__requester.graphql_query(  # type: ignore[attr-defined]  # pylint: disable=protected-access  # no public GraphQL API in PyGithub
            query=_TIMELINE_PRS_QUERY, variables=variables
        )

        if (rl := graphql_rate_limit_error(result)) is not None:
            raise rl

        # Step 5: Parse response and filter for OPEN PRs
        try:
            data = result.get("data")
            if data is None:
                logger.debug(f"Issue #{issue_number}: Malformed GraphQL response")
                raise BranchLookupError(
                    f"Issue #{issue_number}: Malformed GraphQL response"
                )

            repository = data.get("repository")
            if repository is None:
                logger.debug(f"Issue #{issue_number}: Repository not found")
                raise BranchLookupError(f"Issue #{issue_number}: Repository not found")

            issue_data = repository.get("issue")
            if issue_data is None:
                logger.debug(f"Issue #{issue_number}: Issue not found")
                raise BranchLookupError(f"Issue #{issue_number}: Issue not found")

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
                return BranchLookup("found", branch_name)

            if len(open_prs) > 1:
                pr_numbers = [pr["number"] for pr in open_prs]
                logger.warning(
                    f"Issue #{issue_number}: Multiple open PRs found: {pr_numbers}. "
                    f"Cannot determine which branch to use."
                )
                return BranchLookup("ambiguous")

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
                    return BranchLookup("found", branch_name)
                except GithubException as e:
                    if e.status == 404:  # branch gone
                        continue
                    raise

        except (AttributeError, KeyError, TypeError) as e:
            logger.error(f"Issue #{issue_number}: Error parsing timeline response: {e}")
            raise BranchLookupError(
                f"Issue #{issue_number}: Error parsing timeline response: {e}"
            ) from e

        # Step 8: Pattern search fallback
        return self._pattern_lookup(issue_number, repo)
