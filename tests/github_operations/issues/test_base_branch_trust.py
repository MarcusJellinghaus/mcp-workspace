"""Tests for the Base Branch trust decision in base_branch_trust.py."""

from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest
from github.GithubException import GithubException

from mcp_workspace.github_operations.issues.base_branch_trust import (
    fetch_body_editor,
    is_body_trusted,
)

_LOGIN_PATH = "mcp_workspace.github_operations.issues.base_branch_trust._cached_login"


def _editor_response(editor: Optional[dict[str, str]]) -> dict[str, Any]:
    """Build a GraphQL response carrying the given issue editor."""
    return {"data": {"repository": {"issue": {"editor": editor}}}}


def _make_manager(
    response: Optional[dict[str, Any]] = None,
    side_effect: Optional[BaseException] = None,
) -> MagicMock:
    """Return a manager mock whose graphql_query returns response or raises."""
    manager = MagicMock()
    graphql_query = manager._github_client._Github__requester.graphql_query
    if side_effect is not None:
        graphql_query.side_effect = side_effect
    else:
        graphql_query.return_value = ({}, response)
    return manager


def _graphql_query(manager: MagicMock) -> MagicMock:
    """Return the graphql_query mock of a manager built by _make_manager."""
    mock: MagicMock = manager._github_client._Github__requester.graphql_query
    return mock


def _make_repo() -> MagicMock:
    """Return a repository mock for owner/repo."""
    repo = MagicMock()
    repo.owner.login = "owner"
    repo.name = "repo"
    return repo


class TestFetchBodyEditor:
    """Tests for fetch_body_editor."""

    def test_user_editor_returns_login(self) -> None:
        """A User editor yields its login."""
        manager = _make_manager(
            _editor_response({"__typename": "User", "login": "alice"})
        )
        assert fetch_body_editor(manager, _make_repo(), 7) == "alice"

    def test_query_variables(self) -> None:
        """The query is sent with owner, repo name and issue number."""
        manager = _make_manager(_editor_response(None))
        fetch_body_editor(manager, _make_repo(), 7)
        variables = _graphql_query(manager).call_args.kwargs["variables"]
        assert variables == {"owner": "owner", "repo": "repo", "number": 7}

    def test_bot_editor_gets_bot_suffix(self) -> None:
        """A Bot editor yields "name[bot]"."""
        manager = _make_manager(
            _editor_response({"__typename": "Bot", "login": "dependabot"})
        )
        assert fetch_body_editor(manager, _make_repo(), 7) == "dependabot[bot]"

    def test_null_editor_returns_none(self) -> None:
        """A body never edited has a null editor."""
        manager = _make_manager(_editor_response(None))
        assert fetch_body_editor(manager, _make_repo(), 7) is None

    def test_graphql_error_response_returns_none(self) -> None:
        """A {"data": None, "errors": [...]} response yields None."""
        manager = _make_manager({"data": None, "errors": [{"message": "boom"}]})
        assert fetch_body_editor(manager, _make_repo(), 7) is None

    def test_missing_issue_returns_none(self) -> None:
        """A null issue yields None."""
        manager = _make_manager({"data": {"repository": {"issue": None}}})
        assert fetch_body_editor(manager, _make_repo(), 7) is None

    def test_github_exception_returns_none(self) -> None:
        """A GithubException from graphql_query is swallowed."""
        manager = _make_manager(
            side_effect=GithubException(500, {"message": "error"}, None)
        )
        assert fetch_body_editor(manager, _make_repo(), 7) is None


class TestIsBodyTrusted:
    """Tests for is_body_trusted."""

    @pytest.mark.parametrize("association", ["OWNER", "MEMBER", "COLLABORATOR"])
    def test_trusted_role_skips_allowlist_and_graphql(self, association: str) -> None:
        """A trusted role short-circuits before the allowlist or GraphQL."""
        manager = _make_manager(_editor_response(None))
        allowlist = MagicMock(return_value=frozenset())
        assert is_body_trusted(
            manager, _make_repo(), 7, "alice", association, allowlist
        )
        allowlist.assert_not_called()
        _graphql_query(manager).assert_not_called()

    def test_allowlisted_author_skips_graphql(self) -> None:
        """An allowlisted author with association NONE needs no GraphQL request."""
        manager = _make_manager(_editor_response(None))
        allowlist = MagicMock(return_value=frozenset({"alice"}))
        assert is_body_trusted(manager, _make_repo(), 7, "Alice", "NONE", allowlist)
        _graphql_query(manager).assert_not_called()

    def test_editor_is_token_user(self) -> None:
        """An untrusted author whose body was edited by the token user is trusted."""
        manager = _make_manager(_editor_response({"__typename": "User", "login": "Me"}))
        with patch(_LOGIN_PATH, return_value="me"):
            assert is_body_trusted(
                manager, _make_repo(), 7, "mallory", "NONE", lambda: frozenset()
            )

    def test_allowlisted_editor_skips_login_lookup(self) -> None:
        """An allowlisted editor is trusted without resolving the token user."""
        manager = _make_manager(
            _editor_response({"__typename": "User", "login": "Bob"})
        )
        with patch(_LOGIN_PATH) as login:
            assert is_body_trusted(
                manager, _make_repo(), 7, "mallory", "NONE", lambda: frozenset({"bob"})
            )
        login.assert_not_called()

    def test_allowlisted_bot_editor(self) -> None:
        """An allowlisted Bot editor is matched with its [bot] suffix."""
        manager = _make_manager(
            _editor_response({"__typename": "Bot", "login": "dependabot"})
        )
        with patch(_LOGIN_PATH, return_value="me"):
            assert is_body_trusted(
                manager,
                _make_repo(),
                7,
                "mallory",
                "NONE",
                lambda: frozenset({"dependabot[bot]"}),
            )

    def test_untrusted_editor(self) -> None:
        """An untrusted author and an untrusted editor is untrusted."""
        manager = _make_manager(
            _editor_response({"__typename": "User", "login": "eve"})
        )
        with patch(_LOGIN_PATH, return_value="me"):
            assert not is_body_trusted(
                manager, _make_repo(), 7, "mallory", "NONE", lambda: frozenset()
            )

    def test_no_editor(self) -> None:
        """An untrusted author with an unedited body is untrusted."""
        manager = _make_manager(_editor_response(None))
        with patch(_LOGIN_PATH, return_value="me"):
            assert not is_body_trusted(
                manager, _make_repo(), 7, "mallory", "NONE", lambda: frozenset()
            )

    def test_editor_lookup_fails(self) -> None:
        """A failed editor lookup means untrusted."""
        manager = _make_manager(
            side_effect=GithubException(500, {"message": "error"}, None)
        )
        with patch(_LOGIN_PATH, return_value="me"):
            assert not is_body_trusted(
                manager, _make_repo(), 7, "mallory", "NONE", lambda: frozenset()
            )

    def test_cached_login_raises(self) -> None:
        """A failing token-user lookup means the editor is untrusted."""
        manager = _make_manager(_editor_response({"__typename": "User", "login": "me"}))
        with patch(
            _LOGIN_PATH, side_effect=GithubException(401, {"message": "bad"}, None)
        ):
            assert not is_body_trusted(
                manager, _make_repo(), 7, "mallory", "NONE", lambda: frozenset()
            )

    def test_ghost_author_no_editor(self) -> None:
        """A ghost author with no editor is untrusted and does not crash."""
        manager = _make_manager(_editor_response(None))
        with patch(_LOGIN_PATH, return_value="me"):
            assert not is_body_trusted(
                manager, _make_repo(), 7, None, None, lambda: frozenset()
            )
