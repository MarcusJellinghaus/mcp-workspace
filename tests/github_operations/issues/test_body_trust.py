"""Tests for IssueManager.check_body_trust and the body_trust module."""

from collections.abc import Generator
from contextlib import nullcontext
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from github.GithubException import (
    GithubException,
    RateLimitExceededException,
    UnknownObjectException,
)
from requests.exceptions import RetryError
from urllib3.exceptions import MaxRetryError

from mcp_workspace.github_operations.caching.errors import GitHubRateLimitError
from mcp_workspace.github_operations.issues import (
    BodyTrust,
    BodyTrustResult,
    IssueData,
    IssueManager,
)
from tests.github_operations.conftest import make_retry_error

_ALLOWLIST_PATH = "mcp_workspace.config.get_trusted_commenters"
_REPO_IDENTIFIER_PATH = (
    "mcp_workspace.github_operations.base_manager.git_operations"
    ".get_repository_identifier"
)


def _issue(
    user: str = "stranger", association: str = "NONE", number: int = 7
) -> IssueData:
    """Build an IssueData for the given author and number."""
    return IssueData(
        number=number,
        title="t",
        body="b",
        state="open",
        labels=[],
        assignees=[],
        user=user,
        created_at=None,
        updated_at=None,
        url="",
        locked=False,
        author_association=association,
    )


@pytest.fixture
def client() -> MagicMock:
    """GitHub client mock with an owner/repo repository and a token user."""
    mock = MagicMock()
    mock.get_repo.return_value.owner.login = "owner"
    mock.get_repo.return_value.name = "repo"
    mock.get_user.return_value.login = "tokenbot"
    mock._Github__requester.graphql_query.return_value = ({}, {})
    return mock


@pytest.fixture
def manager(client: MagicMock) -> IssueManager:
    """Real IssueManager using the client mock."""
    mgr = IssueManager(repo_url="https://github.com/test/repo", github_token="t")
    mgr._cached_github_client = client
    return mgr


@pytest.fixture(autouse=True)
def allowlist() -> Generator[MagicMock, None, None]:
    """Patch the allowlist to contain only "alice"."""
    with patch(_ALLOWLIST_PATH, return_value=frozenset({"alice"})) as mock:
        yield mock


def _graphql(client: MagicMock) -> MagicMock:
    """Return the graphql_query mock of client."""
    mock: MagicMock = client._Github__requester.graphql_query
    return mock


def _body(editor: Any) -> dict[str, Any]:
    """Build a GraphQL response body with the given editor node."""
    return {"data": {"repository": {"issue": {"editor": editor}}}}


def _user(login: str) -> dict[str, Any]:
    """Build a User editor node."""
    return {"__typename": "User", "login": login}


def _bot(login: str) -> dict[str, Any]:
    """Build a Bot editor node."""
    return {"__typename": "Bot", "login": login}


def _break_repo_identity(manager: IssueManager, tmp_path: Path) -> Any:
    """Make manager.repo_identifier raise ValueError while the returned patch is active."""
    manager._cached_repo_identifier = None
    manager.project_dir = tmp_path
    return patch(_REPO_IDENTIFIER_PATH, return_value=None)


def _assert_no_calls(client: MagicMock) -> None:
    """Assert no repository, editor or token-user lookup happened."""
    client.get_repo.assert_not_called()
    _graphql(client).assert_not_called()
    client.get_user.assert_not_called()


class TestTypes:
    """Tests for the public types and exports."""

    def test_enum_values(self) -> None:
        """The enum values are the documented strings."""
        assert BodyTrust.TRUSTED.value == "trusted"
        assert BodyTrust.UNTRUSTED.value == "untrusted"
        assert BodyTrust.LOOKUP_FAILED.value == "lookup_failed"

    def test_result_constructible(self) -> None:
        """Callers can build a BodyTrustResult themselves."""
        result = BodyTrustResult(BodyTrust.LOOKUP_FAILED, "x")
        assert result.status is BodyTrust.LOOKUP_FAILED
        assert result.reason == "x"

    def test_exports(self) -> None:
        """The types are re-exported and IssueManager has the method."""
        from mcp_workspace.github_operations import issues

        assert issues.BodyTrust is BodyTrust
        assert issues.BodyTrustResult is BodyTrustResult
        assert "BodyTrust" in issues.__all__
        assert "BodyTrustResult" in issues.__all__
        assert callable(getattr(IssueManager, "check_body_trust", None))


class TestAuthor:
    """Author outcomes."""

    @pytest.mark.parametrize("association", ["OWNER", "MEMBER", "COLLABORATOR"])
    def test_trusted_role(
        self, manager: IssueManager, client: MagicMock, association: str
    ) -> None:
        """A trusted role is trusted without any GitHub call."""
        result = manager.check_body_trust(_issue(association=association))
        assert result == BodyTrustResult(BodyTrust.TRUSTED, "author trusted")
        _assert_no_calls(client)

    def test_allowlisted_author_mixed_case(
        self, manager: IssueManager, client: MagicMock
    ) -> None:
        """An allowlisted login matches case-insensitively, without GitHub calls."""
        result = manager.check_body_trust(_issue(user="AlIcE"))
        assert result == BodyTrustResult(BodyTrust.TRUSTED, "author trusted")
        _assert_no_calls(client)


class TestOrder:
    """Order of the checks and their short-circuits."""

    @pytest.mark.parametrize(
        "breakage", ["identity", "repo_none", "repo_rate_limit", "number_zero"]
    )
    def test_trusted_author_short_circuits(
        self,
        manager: IssueManager,
        client: MagicMock,
        tmp_path: Path,
        breakage: str,
    ) -> None:
        """A trusted author wins over every later failure."""
        number = 0 if breakage == "number_zero" else 7
        if breakage == "repo_none":
            client.get_repo.return_value = None
        if breakage == "repo_rate_limit":
            client.get_repo.side_effect = RateLimitExceededException(403, {}, {})
        identity = (
            _break_repo_identity(manager, tmp_path)
            if breakage == "identity"
            else nullcontext()
        )
        with identity:
            result = manager.check_body_trust(
                _issue(association="OWNER", number=number)
            )
        assert result == BodyTrustResult(BodyTrust.TRUSTED, "author trusted")
        client.get_repo.assert_not_called()

    @pytest.mark.parametrize("number", [7, 0])
    def test_repository_not_detected(
        self, manager: IssueManager, client: MagicMock, tmp_path: Path, number: int
    ) -> None:
        """A missing repository identity is reported before the number check."""
        with _break_repo_identity(manager, tmp_path):
            result = manager.check_body_trust(_issue(number=number))
        assert result == BodyTrustResult(
            BodyTrust.LOOKUP_FAILED, "repository not detected"
        )
        client.get_repo.assert_not_called()
        _graphql(client).assert_not_called()

    @pytest.mark.parametrize("number", [7, 0])
    def test_repository_unavailable(
        self, manager: IssueManager, client: MagicMock, number: int
    ) -> None:
        """A repository lookup returning None is reported before the number check."""
        client.get_repo.return_value = None
        result = manager.check_body_trust(_issue(number=number))
        assert result == BodyTrustResult(
            BodyTrust.LOOKUP_FAILED, "repository unavailable"
        )
        _graphql(client).assert_not_called()

    def test_issue_number_missing(
        self, manager: IssueManager, client: MagicMock
    ) -> None:
        """Number 0 is reported without a GraphQL request."""
        result = manager.check_body_trust(_issue(number=0))
        assert result == BodyTrustResult(
            BodyTrust.LOOKUP_FAILED, "issue number missing"
        )
        _graphql(client).assert_not_called()


class TestRepositoryExceptions:
    """Exceptions raised by the repository lookup."""

    @pytest.mark.parametrize(
        "exc",
        [
            ConnectionError("down"),
            GithubException(404, {"message": "Not Found"}, {}),
            GithubException(401, {"message": "Bad credentials"}, {}),
            GithubException(403, {"message": "Forbidden"}, {}),
            make_retry_error(503),
            GithubException(400, {"errors": [{"type": "RATE_LIMITED"}]}, {}),
        ],
        ids=["connection", "404", "401", "403", "retry-503", "400-rate-limited"],
    )
    def test_unavailable(
        self, manager: IssueManager, client: MagicMock, exc: BaseException
    ) -> None:
        """Non-rate-limit failures become "repository unavailable"."""
        client.get_repo.side_effect = exc
        result = manager.check_body_trust(_issue())
        assert result == BodyTrustResult(
            BodyTrust.LOOKUP_FAILED, "repository unavailable"
        )
        _graphql(client).assert_not_called()

    @pytest.mark.parametrize(
        "exc",
        [
            GithubException(403, {}, {"X-RateLimit-Remaining": "0"}),
            RateLimitExceededException(403, {}, {}),
            GithubException(429, {}, {}),
            make_retry_error(403),
            make_retry_error(429),
            RetryError(MaxRetryError(None, "u")),  # type: ignore[arg-type]
        ],
        ids=["header", "rate-limit-exc", "429", "retry-403", "retry-429", "retry-?"],
    )
    def test_rate_limit_raises(
        self, manager: IssueManager, client: MagicMock, exc: BaseException
    ) -> None:
        """Rate-limit shapes raise GitHubRateLimitError."""
        client.get_repo.side_effect = exc
        with pytest.raises(GitHubRateLimitError):
            manager.check_body_trust(_issue())
        _graphql(client).assert_not_called()


_TRUSTED_EDITOR = BodyTrustResult(BodyTrust.TRUSTED, "last editor trusted")
_UNTRUSTED = BodyTrustResult(BodyTrust.UNTRUSTED, "author and last editor untrusted")


def _set_body(client: MagicMock, body: Any) -> None:
    """Make the GraphQL query return body."""
    _graphql(client).return_value = ({}, body)


class TestEditor:
    """Editor, allowlist and token-user outcomes."""

    @pytest.mark.parametrize(
        ("allowlist_value", "editor"),
        [
            (frozenset({"alice"}), _user("AlIcE")),
            (frozenset({"helper[bot]"}), _bot("HeLpEr")),
        ],
        ids=["user", "bot"],
    )
    def test_allowlisted_editor(
        self,
        manager: IssueManager,
        client: MagicMock,
        allowlist: MagicMock,
        allowlist_value: frozenset[str],
        editor: dict[str, Any],
    ) -> None:
        """An allowlisted editor is trusted without a token-user lookup."""
        allowlist.return_value = allowlist_value
        client.get_user.side_effect = RuntimeError("must not be called")
        _set_body(client, _body(editor))
        assert manager.check_body_trust(_issue()) == _TRUSTED_EDITOR
        client.get_user.assert_not_called()

    @pytest.mark.parametrize("login", ["tokenbot", "TokenBot"])
    def test_token_user_editor(
        self, manager: IssueManager, client: MagicMock, login: str
    ) -> None:
        """The token user as editor is trusted, case-insensitively."""
        _set_body(client, _body(_user(login)))
        assert manager.check_body_trust(_issue()) == _TRUSTED_EDITOR

    def test_untrusted_author_re_edited(
        self, manager: IssueManager, client: MagicMock
    ) -> None:
        """An editor that is neither the token user nor allowlisted is untrusted."""
        _set_body(client, _body(_user("stranger")))
        assert manager.check_body_trust(_issue()) == _UNTRUSTED

    def test_bot_editor_needs_bot_suffix_in_allowlist(
        self, manager: IssueManager, client: MagicMock, allowlist: MagicMock
    ) -> None:
        """A Bot editor is compared as name[bot], so a bare name does not match."""
        allowlist.return_value = frozenset({"dependabot"})
        _set_body(client, _body(_bot("dependabot")))
        assert manager.check_body_trust(_issue()) == _UNTRUSTED

    def test_never_edited(self, manager: IssueManager, client: MagicMock) -> None:
        """A null editor is untrusted without a token-user lookup."""
        _set_body(client, _body(None))
        assert manager.check_body_trust(_issue()) == _UNTRUSTED
        client.get_user.assert_not_called()

    @pytest.mark.parametrize(
        ("editor", "expected"),
        [("stranger", _UNTRUSTED), ("alice", _TRUSTED_EDITOR)],
    )
    def test_missing_author_keys(
        self,
        manager: IssueManager,
        client: MagicMock,
        editor: str,
        expected: BodyTrustResult,
    ) -> None:
        """Missing user / author_association keys fall through to the editor."""
        issue: dict[str, Any] = dict(_issue())
        del issue["user"]
        del issue["author_association"]
        _set_body(client, _body(_user(editor)))
        assert manager.check_body_trust(issue) == expected


class TestResponseBodies:
    """GraphQL response bodies that cannot be used."""

    @pytest.mark.parametrize(
        "body",
        [
            {"data": {"repository": {"issue": {}}}},
            _body("alice"),
            _body(["alice"]),
            _body({"__typename": "User"}),
            _body(_user("")),
            _body(_user("  ")),
            _body({"__typename": "User", "login": 42}),
            _body({"__typename": "User", "login": None}),
        ],
        ids=[
            "editor-missing",
            "editor-str",
            "editor-list",
            "login-absent",
            "login-empty",
            "login-blank",
            "login-int",
            "login-none",
        ],
    )
    def test_editor_login_missing(
        self, manager: IssueManager, client: MagicMock, body: Any
    ) -> None:
        """An unusable editor node is a failed lookup."""
        _set_body(client, body)
        assert manager.check_body_trust(_issue()) == BodyTrustResult(
            BodyTrust.LOOKUP_FAILED, "editor login missing"
        )

    @pytest.mark.parametrize(
        "body",
        [
            {"errors": [], **_body(_user("alice"))},
            {"errors": None, **_body(_user("alice"))},
            {"errors": [{"type": "FORBIDDEN"}], **_body(_user("alice"))},
            {"errors": ["oops"], **_body(_user("alice"))},
            {"errors": "boom", **_body(_user("alice"))},
            {"errors": [{"type": "NOT_FOUND"}]},
            {
                "errors": [{"type": "NOT_FOUND"}],
                "data": {"repository": {"issue": None}},
            },
        ],
        ids=[
            "empty",
            "none",
            "forbidden",
            "str-entry",
            "str",
            "not-found",
            "null-issue",
        ],
    )
    def test_graphql_error(
        self, manager: IssueManager, client: MagicMock, body: Any
    ) -> None:
        """Any errors key without a rate limit is a failed lookup."""
        _set_body(client, body)
        assert manager.check_body_trust(_issue()) == BodyTrustResult(
            BodyTrust.LOOKUP_FAILED, "GraphQL error"
        )
        client.get_user.assert_not_called()

    def test_rate_limited_raises(
        self, manager: IssueManager, client: MagicMock
    ) -> None:
        """A RATE_LIMITED error entry raises GitHubRateLimitError."""
        _set_body(
            client,
            {"errors": [{"type": "NOT_FOUND"}, {"type": "RATE_LIMITED"}], "data": None},
        )
        with pytest.raises(GitHubRateLimitError):
            manager.check_body_trust(_issue())

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"data": None},
            {"data": {}},
            {"data": {"repository": None}},
            {"data": {"repository": {}}},
            {"data": {"repository": {"issue": None}}},
            {"data": "x"},
            {"data": {"repository": "x"}},
            {"data": {"repository": {"issue": "x"}}},
            None,
            ["data"],
            "body",
        ],
        ids=[
            "data-missing",
            "data-none",
            "data-empty",
            "repository-none",
            "issue-missing",
            "issue-none",
            "data-str",
            "repository-str",
            "issue-str",
            "body-none",
            "body-list",
            "body-str",
        ],
    )
    def test_issue_not_found(
        self, manager: IssueManager, client: MagicMock, body: Any
    ) -> None:
        """A body without an issue node is a failed lookup."""
        _set_body(client, body)
        assert manager.check_body_trust(_issue()) == BodyTrustResult(
            BodyTrust.LOOKUP_FAILED, "issue not found"
        )


_RATE_LIMIT_SHAPES = [
    GithubException(403, {}, {"X-RateLimit-Remaining": "0"}),
    make_retry_error(403),
    make_retry_error(429),
    RetryError(MaxRetryError(None, "u")),  # type: ignore[arg-type]
]
_RATE_LIMIT_IDS = ["header", "retry-403", "retry-429", "retry-?"]


def _failed(reason: str) -> BodyTrustResult:
    """Build a LOOKUP_FAILED result with reason."""
    return BodyTrustResult(BodyTrust.LOOKUP_FAILED, reason)


class TestEditorExceptions:
    """Exceptions raised by the editor GraphQL query."""

    @pytest.mark.parametrize(
        ("exc", "reason"),
        [
            (
                UnknownObjectException(404, {"message": "Not Found"}, {}),
                "UnknownObjectException",
            ),
            (
                GithubException(
                    400, {"errors": [{"type": "FORBIDDEN"}, {"type": "X"}]}, {}
                ),
                "GithubException",
            ),
            (
                GithubException(
                    400, {"errors": [{"type": "NOT_FOUND"}, {"type": "X"}]}, {}
                ),
                "GithubException",
            ),
            (GithubException(400, {"errors": []}, {}), "GithubException"),
            (
                GithubException(401, {"message": "Bad credentials"}, {}),
                "GithubException",
            ),
            (GithubException(403, {"message": "Forbidden"}, {}), "GithubException"),
            (GithubException(500, {"message": "Server Error"}, {}), "GithubException"),
            (TypeError("bad"), "TypeError"),
            (ConnectionError("secret-host down"), "ConnectionError"),
            (make_retry_error(503), "RetryError"),
        ],
        ids=[
            "unknown-object",
            "400-several",
            "400-not-found-plus",
            "400-empty",
            "401",
            "403",
            "500",
            "type-error",
            "connection",
            "retry-503",
        ],
    )
    def test_lookup_failed(
        self,
        manager: IssueManager,
        client: MagicMock,
        exc: BaseException,
        reason: str,
    ) -> None:
        """Non-rate-limit failures report the exception type name only."""
        _graphql(client).side_effect = exc
        result = manager.check_body_trust(_issue())
        assert result == _failed(reason)
        assert "secret" not in result.reason
        client.get_user.assert_not_called()

    @pytest.mark.parametrize(
        "exc",
        [
            GithubException(400, {"errors": [{"type": "RATE_LIMITED"}]}, {}),
            GithubException(502, {"errors": [{"type": "RATE_LIMITED"}]}, {}),
            RateLimitExceededException(403, {}, {}),
            GithubException(429, {}, {}),
            *_RATE_LIMIT_SHAPES,
        ],
        ids=["400-rate-limited", "502-rate-limited", "rate-limit-exc", "429"]
        + _RATE_LIMIT_IDS,
    )
    def test_rate_limit_raises(
        self, manager: IssueManager, client: MagicMock, exc: BaseException
    ) -> None:
        """Rate-limit shapes raise GitHubRateLimitError."""
        _graphql(client).side_effect = exc
        with pytest.raises(GitHubRateLimitError):
            manager.check_body_trust(_issue())
        client.get_user.assert_not_called()


class TestTokenUserExceptions:
    """Exceptions raised by the token-user lookup."""

    @pytest.mark.parametrize(
        ("exc", "reason"),
        [
            (GithubException(500, {"message": "Server Error"}, {}), "GithubException"),
            (make_retry_error(503), "RetryError"),
        ],
        ids=["500", "retry-503"],
    )
    def test_lookup_failed(
        self,
        manager: IssueManager,
        client: MagicMock,
        exc: BaseException,
        reason: str,
    ) -> None:
        """Non-rate-limit failures report the exception type name only."""
        _set_body(client, _body(_user("stranger")))
        client.get_user.side_effect = exc
        assert manager.check_body_trust(_issue()) == _failed(reason)

    @pytest.mark.parametrize("exc", _RATE_LIMIT_SHAPES, ids=_RATE_LIMIT_IDS)
    def test_rate_limit_raises(
        self, manager: IssueManager, client: MagicMock, exc: BaseException
    ) -> None:
        """Rate-limit shapes raise GitHubRateLimitError."""
        _set_body(client, _body(_user("stranger")))
        client.get_user.side_effect = exc
        with pytest.raises(GitHubRateLimitError):
            manager.check_body_trust(_issue())


class TestQuery:
    """The GraphQL request itself."""

    def test_no_caching(self, manager: IssueManager, client: MagicMock) -> None:
        """Each call makes a fresh editor query."""
        _set_body(client, _body(_user("stranger")))
        manager.check_body_trust(_issue())
        manager.check_body_trust(_issue())
        assert _graphql(client).call_count == 2

    def test_variables(self, manager: IssueManager, client: MagicMock) -> None:
        """The query is sent with the repository owner, name and issue number."""
        _set_body(client, _body(None))
        manager.check_body_trust(_issue(number=7))
        _graphql(client).assert_called_once()
        assert _graphql(client).call_args.kwargs["variables"] == {
            "owner": "owner",
            "repo": "repo",
            "number": 7,
        }
