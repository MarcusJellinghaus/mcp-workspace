"""Tests for IssueManager.check_body_trust and the body_trust module."""

from contextlib import nullcontext
from pathlib import Path
from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest
from github.GithubException import GithubException, RateLimitExceededException
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
