"""PR feedback mixin for PullRequestManager.

This module provides the PRFeedbackMixin class containing the get_pr_feedback
and get_closing_issue_numbers operations for GitHub pull requests.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List

from mcp_coder_utils.log_utils import log_function_call

from . import _pr_feedback_sources
from ._diagnostics import format_rate_limit_error
from .base_manager import _handle_github_errors
from .pr_types import AlertData, PRFeedback

if TYPE_CHECKING:
    from .pr_manager import PullRequestManager

logger = logging.getLogger(__name__)

__all__ = ["PRFeedbackMixin"]


def _empty_pr_feedback() -> PRFeedback:
    """Return a fresh empty PRFeedback dict."""
    return {
        "unresolved_threads": [],
        "resolved_thread_count": 0,
        "changes_requested": [],
        "conversation_comments": [],
        "alerts": [],
        "unavailable": {},
        "skipped": {},
    }


class PRFeedbackMixin:
    """Mixin providing PR feedback and closing-issue-reference queries.

    This mixin is designed to be used with PullRequestManager, which supplies
    _validate_pr_number, _get_repository, and _github_client.
    """

    @log_function_call
    @_handle_github_errors(default_return=[])
    def get_closing_issue_numbers(
        self: "PullRequestManager", pr_number: int
    ) -> List[int]:
        """Query closing issue references for a PR via GraphQL.

        Args:
            pr_number: Pull request number to query

        Returns:
            List of issue numbers linked as closing references, or empty list on error
        """
        if not self._validate_pr_number(pr_number):
            return []

        repo = self._get_repository()
        if repo is None:
            return []

        owner, repo_name = repo.owner.login, repo.name

        query = """
        query($owner: String!, $repo: String!, $prNumber: Int!) {
          repository(owner: $owner, name: $repo) {
            pullRequest(number: $prNumber) {
              closingIssuesReferences(first: 10) {
                nodes {
                  number
                }
              }
            }
          }
        }
        """

        variables = {
            "owner": owner,
            "repo": repo_name,
            "prNumber": pr_number,
        }

        _, result = self._github_client._Github__requester.graphql_query(  # type: ignore[attr-defined]  # pylint: disable=protected-access  # no public GraphQL API in PyGithub
            query=query, variables=variables
        )

        try:
            pr_data = result.get("data", {}).get("repository", {}).get("pullRequest")
            if pr_data is None:
                logger.warning(f"PR #{pr_number} not found")
                return []

            nodes = pr_data.get("closingIssuesReferences", {}).get("nodes", [])
            return [node["number"] for node in nodes if node]

        except (KeyError, TypeError) as e:
            logger.error(f"Error parsing GraphQL response: {e}")
            return []

    @log_function_call
    @_handle_github_errors(default_return=_empty_pr_feedback)
    def get_pr_feedback(
        self: "PullRequestManager", pr_number: int, include_alerts: bool = True
    ) -> PRFeedback:
        """Fetch aggregated PR feedback (review threads, comments, alerts).

        Args:
            pr_number: Pull request number to query
            include_alerts: Fetch code-scanning alerts. When False, no
                code-scanning request is made: ``alerts`` is ``[]`` and neither
                ``unavailable`` nor ``skipped`` has an ``"alerts"`` key.

        Returns:
            PRFeedback dict containing unresolved threads, resolved thread count,
            standing CHANGES_REQUESTED reviews, conversation comments, code-scanning alerts,
            a dict mapping failed section names to the raised or returned
            exception (``unavailable``), and a dict of sections that could not
            be checked (``skipped``) — a 403/404 on alerts that is not a rate
            limit goes into ``skipped``, every other failure into ``unavailable``.
        """
        if not self._validate_pr_number(pr_number):
            return _empty_pr_feedback()

        unavailable: dict[str, Exception] = {}
        skipped: dict[str, Exception] = {}

        try:
            threads, resolved_count, changes_requested, review_error = (
                _pr_feedback_sources.fetch_review_data(self, pr_number)
            )
            if review_error is not None:
                # Returned, not raised — the except below never sees it, so the
                # WARNING has to be logged explicitly here.
                logger.warning(
                    f"Failed to fetch review data for PR #{pr_number}: {review_error}"
                )
                unavailable["threads"] = review_error
        except (
            Exception
        ) as e:  # pylint: disable=broad-exception-caught  # one section failure must not abort
            logger.warning(f"Failed to fetch review data for PR #{pr_number}: {e}")
            threads, resolved_count, changes_requested = ([], 0, [])
            unavailable["threads"] = e

        try:
            comments = _pr_feedback_sources.fetch_conversation_comments(self, pr_number)
        except (
            Exception
        ) as e:  # pylint: disable=broad-exception-caught  # one section failure must not abort
            logger.warning(
                f"Failed to fetch conversation comments for PR #{pr_number}: {e}"
            )
            comments = []
            unavailable["comments"] = e

        alerts: list[AlertData] = []
        if include_alerts:
            try:
                alerts = _pr_feedback_sources.fetch_code_scanning_alerts(
                    self, pr_number
                )
            except (
                Exception
            ) as e:  # pylint: disable=broad-exception-caught  # one section failure must not abort
                # 403/404 without a rate limit: token lacks security_events:read,
                # code scanning is disabled, or no analysis exists — not a failure.
                if (
                    getattr(e, "status", None) in (403, 404)
                    and format_rate_limit_error(e) is None
                ):
                    logger.debug(
                        f"Code-scanning alerts not checked for PR #{pr_number}: {e}"
                    )
                    skipped["alerts"] = e
                else:
                    logger.warning(
                        f"Failed to fetch code-scanning alerts for PR #{pr_number}: {e}"
                    )
                    unavailable["alerts"] = e

        return {
            "unresolved_threads": threads,
            "resolved_thread_count": resolved_count,
            "changes_requested": changes_requested,
            "conversation_comments": comments,
            "alerts": alerts,
            "unavailable": unavailable,
            "skipped": skipped,
        }
