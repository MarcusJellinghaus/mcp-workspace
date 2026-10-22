"""Decide whether an issue body may choose the base branch.

A body is trusted when its author is trusted (role, then allowlist) or when its
last editor is trusted (the token user, or an allowlisted login). Nothing here
raises: any lookup failure means "untrusted".
"""

import logging
from typing import Callable, Optional

from github.Repository import Repository

from ..base_manager import BaseGitHubManager, _cached_login
from ..trust import is_trusted_author

logger = logging.getLogger(__name__)

__all__ = ["fetch_body_editor", "is_body_trusted"]

# GraphQL query returning the last editor of an issue body.
_BODY_EDITOR_QUERY = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    issue(number: $number) {
      editor {
        __typename
        login
      }
    }
  }
}
"""


def fetch_body_editor(
    manager: BaseGitHubManager, repo: Repository, issue_number: int
) -> Optional[str]:
    """Return the login of the issue body's last editor.

    Args:
        manager: Manager providing the GitHub client.
        repo: Repository the issue belongs to.
        issue_number: Issue whose body editor is looked up.

    Returns:
        The editor's login, with a "[bot]" suffix for bots, or None when the
        body was never edited or the lookup failed. Never raises.
    """
    variables = {"owner": repo.owner.login, "repo": repo.name, "number": issue_number}
    try:
        _, result = manager._github_client._Github__requester.graphql_query(  # type: ignore[attr-defined]  # pylint: disable=protected-access  # no public GraphQL API in PyGithub
            query=_BODY_EDITOR_QUERY, variables=variables
        )
        data = (result or {}).get("data") or {}
        issue = (data.get("repository") or {}).get("issue") or {}
        editor = issue.get("editor")
        if not editor or not editor.get("login"):
            return None
        login: str = editor["login"]
        return f"{login}[bot]" if editor.get("__typename") == "Bot" else login
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug(
            "Body editor lookup failed for issue #%s", issue_number, exc_info=True
        )
        return None


def is_body_trusted(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    manager: BaseGitHubManager,
    repo: Repository,
    issue_number: int,
    author_login: Optional[str],
    author_association: Optional[str],
    allowlist: Callable[[], frozenset[str]],
) -> bool:
    """Decide whether an issue body may choose the base branch.

    Args:
        manager: Manager providing the GitHub client and token.
        repo: Repository the issue belongs to.
        issue_number: Issue whose body is checked.
        author_login: Login of the issue author; None for ghost users.
        author_association: GitHub ``author_association`` of the author.
        allowlist: Zero-argument callable returning the lowercased allowlist;
            called only when the author's role is not trusted.

    Returns:
        True when the author or the last body editor is trusted. Never raises.
    """
    # Role first, so a trusted role never reads the allowlist.
    if is_trusted_author(author_login, author_association, frozenset()):
        return True
    if is_trusted_author(author_login, author_association, allowlist()):
        return True
    editor = fetch_body_editor(manager, repo, issue_number)
    if editor is None:
        return False
    if editor.lower() in allowlist():
        return True
    try:
        # pylint: disable=protected-access
        token_user = _cached_login(
            manager.github_token,
            manager._repo_identifier.api_base_url,
            manager._github_client,
        )
        return editor.lower() == token_user.lower()
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug(
            "Token user lookup failed for issue #%s", issue_number, exc_info=True
        )
        return False
