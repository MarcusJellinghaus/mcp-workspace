"""PR merge mixin for PullRequestManager.

This module provides the PRMergeMixin class containing the merge_pull_request
operation for GitHub pull requests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from github.GithubException import GithubException
from mcp_coder_utils.log_utils import log_function_call

from .base_manager import _handle_github_errors
from .pr_types import MergeResult

if TYPE_CHECKING:
    from .pr_manager import PullRequestManager

__all__ = ["PRMergeMixin"]


def _failed_merge_result() -> MergeResult:
    """Return a fresh MergeResult for the decorator default (outcome='error')."""
    return {
        "merged": False,
        "outcome": "error",
        "sha": None,
        "message": "",
        "status": None,
    }


class PRMergeMixin:
    """Mixin providing the merge_pull_request operation.

    This mixin is designed to be used with PullRequestManager, which supplies
    _validate_pr_number and _get_repository.
    """

    @log_function_call
    @_handle_github_errors(default_return=_failed_merge_result)
    def merge_pull_request(
        self: "PullRequestManager",
        pr_number: int,
        merge_method: str = "squash",
        sha: Optional[str] = None,
        commit_title: Optional[str] = None,
        commit_message: Optional[str] = None,
    ) -> MergeResult:
        """Merge a pull request, wrapping PyGithub's PullRequest.merge().

        Performs one logical merge attempt (retry is the caller's
        responsibility) and returns a MergeResult whose ``outcome`` field is the
        sole cross-process contract:

        =========================================  =========  ========  ========
        HTTP / condition                           outcome    merged    status
        =========================================  =========  ========  ========
        200                                        merged     True      200
        405 and re-fetched pr.merged is True       merged     True      405
        405 (not merged / re-fetch failed),        refused    False     status
        409, 422
        404, 5xx, network, validation              error      False     status/None
        401 / 403                                  *raises*   -         -
        =========================================  =========  ========  ========

        The ``sha`` race guard: forwarding an expected head SHA makes GitHub
        return 409 if the branch moved since it was verified, preventing an
        unverified merge; consumers can re-verify CI on the new HEAD.

        The HTTP layer retries the merge PUT, so a merge whose response was lost
        can re-issue the PUT and get 405 "not mergeable" because it is already
        merged. On 405 the PR is therefore re-fetched once: ``merged=True``
        reports that the PR is merged as of that read - not that this call
        performed the merge.

        ``status`` is diagnostic-only for 405 (GitHub returns 405 for several
        distinct causes) but actionable for 409 (head SHA moved). No head-branch
        deletion is performed (out of scope).

        Args:
            pr_number: Pull request number to merge
            merge_method: Merge strategy, one of "squash", "merge", "rebase"
            sha: Expected head SHA; when set, GitHub refuses (409) if HEAD moved
            commit_title: Custom merge commit title (omitted when None)
            commit_message: Custom merge commit message (omitted when None)

        Returns:
            MergeResult describing the outcome of the merge attempt.

        Raises:
            ValueError: If merge_method is not one of "squash", "merge", "rebase"
            GithubException: If GitHub returns 401/403 (authentication or
                permission error); re-raised to the caller instead of being
                mapped to a MergeResult.
        """
        if merge_method not in {"squash", "merge", "rebase"}:
            raise ValueError(
                f"Invalid merge_method: {merge_method!r}. "
                "Must be one of 'squash', 'merge', 'rebase'."
            )

        if not self._validate_pr_number(pr_number):
            return _failed_merge_result()

        repo = self._get_repository()
        if repo is None:
            return _failed_merge_result()

        pr = repo.get_pull(pr_number)

        # Omit sha/commit_title/commit_message when None: PyGithub asserts
        # is_optional(v, str), so passing None surfaces as an AssertionError.
        kwargs: dict[str, Any] = {"merge_method": merge_method}
        for name, value in (
            ("sha", sha),
            ("commit_title", commit_title),
            ("commit_message", commit_message),
        ):
            if value is not None:
                kwargs[name] = value

        try:
            status = pr.merge(**kwargs)
            return {
                "merged": True,
                "outcome": "merged",
                "sha": status.sha,
                "message": status.message,
                "status": 200,
            }
        except GithubException as e:
            if e.status in (401, 403):
                raise  # config error — decorator re-raises to caller
            if e.status == 405:
                # HTTP-layer retry may have merged already; re-fetch once.
                try:
                    pr = repo.get_pull(pr_number)
                except Exception:  # pylint: disable=broad-exception-caught
                    # Any re-fetch failure (GithubException, network/socket
                    # timeout, ...) is a refusal per spec, not an error.
                    return {
                        "merged": False,
                        "outcome": "refused",
                        "sha": None,
                        "message": f"Merge refused (405); re-fetch failed: {e.data}",
                        "status": 405,
                    }
                if pr.merged:
                    return {
                        "merged": True,
                        "outcome": "merged",
                        "sha": pr.merge_commit_sha,
                        "message": "PR is merged as of re-fetch after 405.",
                        "status": 405,
                    }
                return {
                    "merged": False,
                    "outcome": "refused",
                    "sha": None,
                    "message": f"Merge refused (405); PR not merged: {e.data}",
                    "status": 405,
                }
            if e.status in (409, 422):
                return {
                    "merged": False,
                    "outcome": "refused",
                    "sha": None,
                    "message": f"Merge refused ({e.status}): {e.data}",
                    "status": e.status,
                }
            return {
                "merged": False,
                "outcome": "error",
                "sha": None,
                "message": f"Merge error ({e.status}): {e.data}",
                "status": e.status,
            }
