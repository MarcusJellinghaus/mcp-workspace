"""Unit tests for PullRequestManager.get_pr_feedback() and mergeable_state field."""

import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import git
import pytest
from github.GithubException import GithubException, UnknownObjectException
from github.Requester import Requester

from mcp_workspace.checks.pr_feedback import collect_pr_feedback
from mcp_workspace.github_operations import IssueIdentityMismatchError
from mcp_workspace.github_operations._pr_feedback_sources import (
    fetch_code_scanning_alerts,
    fetch_conversation_comments,
)
from mcp_workspace.github_operations.exception_renderer import (
    render_exception_for_display,
)
from mcp_workspace.github_operations.pr_manager import PullRequestManager

from ._issue_test_helpers import make_mock_issue

# An empty-but-valid GraphQL body used as the default POST response. It must
# resolve data.repository.pullRequest to a dict: a null pullRequest is exactly
# the retry trigger, so a thinner default would make every test that omits
# graphql_response run 3 attempts and sleep for real.
_EMPTY_REVIEW_DATA: dict[str, Any] = {
    "data": {
        "repository": {
            "pullRequest": {
                "reviewThreads": {"nodes": []},
                "reviews": {"nodes": []},
            }
        }
    }
}


def _null_pr_body(*errors: dict[str, Any]) -> dict[str, Any]:
    """Build a GraphQL body with a null pullRequest plus optional errors."""
    body: dict[str, Any] = {"data": {"repository": {"pullRequest": None}}}
    if errors:
        body["errors"] = list(errors)
    return body


def _post_call_count(manager: PullRequestManager) -> int:
    """Count GraphQL (POST) calls made through the mocked requester."""
    requester = manager._github_client._Github__requester  # type: ignore[attr-defined]
    return sum(
        1 for c in requester.requestJsonAndCheck.call_args_list if c.args[0] == "POST"
    )


@pytest.mark.git_integration
class TestGetPRFeedback:
    """Tests for PullRequestManager.get_pr_feedback() method."""

    @pytest.fixture
    def mock_manager(self, tmp_path: Path) -> PullRequestManager:
        """Create a PullRequestManager with mocked dependencies."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)
            return manager

    def _setup_mocks(
        self,
        manager: PullRequestManager,
        graphql_response: Any = None,
        graphql_responses: Any = None,
        graphql_raises: Any = None,
        comments: Any = None,
        comments_raises: Any = None,
        alerts_response: Any = None,
        alerts_raises: Any = None,
    ) -> Mock:
        """Set up requester and repository mocks on manager.

        Both review data and code-scanning alerts now go through
        `requestJsonAndCheck`, so the single mock dispatches on the verb:
        GraphQL is the only POST, alerts the only GET.

        `graphql_responses` supplies one body per successive POST (retry tests);
        `graphql_response` supplies one body for every POST. `graphql_raises`
        means an HTTP-level failure of the GraphQL request.

        Returns the mocked repository for additional configuration.
        """
        mock_repo = Mock()
        mock_repo.owner.login = "test"
        mock_repo.name = "repo"
        mock_repo.full_name = "test/repo"
        manager._repository = mock_repo

        mock_requester = Mock()
        manager._github_client._Github__requester = mock_requester  # type: ignore[attr-defined]

        # Concrete string, not an auto-created Mock, so call-arg assertions read
        # cleanly; the real classmethod, so isinstance(..., GithubException)
        # assertions cannot pass vacuously against a Mock.
        mock_requester.graphql_url = "https://api.github.com/graphql"
        mock_requester.createException = Requester.createException

        post_bodies = iter(graphql_responses) if graphql_responses is not None else None

        def _request(verb: str, url: str, **kwargs: Any) -> tuple[dict[str, Any], Any]:
            if verb == "POST":
                if graphql_raises is not None:
                    raise graphql_raises
                if post_bodies is not None:
                    try:
                        return ({}, next(post_bodies))
                    except StopIteration:
                        # BaseException, so get_pr_feedback's broad `except
                        # Exception` cannot turn a short harness into a
                        # plausible-looking "threads unavailable" pass.
                        pytest.fail(
                            "graphql_responses exhausted: the code under test "
                            "made more POSTs than bodies were supplied for"
                        )
                return ({}, graphql_response or _EMPTY_REVIEW_DATA)
            if alerts_raises is not None:
                raise alerts_raises
            return ({}, alerts_response or [])

        mock_requester.requestJsonAndCheck = Mock(side_effect=_request)

        # REST conversation comments via repo.get_issue(...).get_comments()
        mock_issue = make_mock_issue(42)
        if comments_raises is not None:
            mock_issue.get_comments = Mock(side_effect=comments_raises)
        else:
            mock_issue.get_comments = Mock(return_value=comments or [])
        mock_repo.get_issue = Mock(return_value=mock_issue)

        return mock_repo

    def _make_comment(self, login: str, body: str) -> Mock:
        """Create a mock conversation comment."""
        comment = Mock()
        comment.user.login = login
        comment.body = body
        return comment

    def test_happy_path(self, mock_manager: PullRequestManager) -> None:
        """All sources return data — populated PRFeedback."""
        graphql_response = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {
                                    "isResolved": False,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "author": {"login": "alice"},
                                                "body": "issue here",
                                                "path": "src/foo.py",
                                                "line": 10,
                                                "diffSide": "RIGHT",
                                                "diffHunk": "@@ ... @@",
                                            }
                                        ]
                                    },
                                },
                                {
                                    "isResolved": False,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "author": {"login": "bob"},
                                                "body": "another",
                                                "path": "src/bar.py",
                                                "line": 5,
                                                "diffSide": "RIGHT",
                                                "diffHunk": "@@ ... @@",
                                            }
                                        ]
                                    },
                                },
                                {
                                    "isResolved": True,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "author": {"login": "carol"},
                                                "body": "fixed",
                                                "path": "src/baz.py",
                                                "line": 1,
                                                "diffSide": "RIGHT",
                                                "diffHunk": "@@ ... @@",
                                            }
                                        ]
                                    },
                                },
                            ]
                        },
                        "reviews": {
                            "nodes": [
                                {
                                    "state": "CHANGES_REQUESTED",
                                    "author": {"login": "alice"},
                                    "body": "please fix",
                                    "submittedAt": "2025-01-01T00:00:00Z",
                                },
                                {
                                    "state": "APPROVED",
                                    "author": {"login": "bob"},
                                    "body": "lgtm",
                                    "submittedAt": "2025-01-02T00:00:00Z",
                                },
                            ]
                        },
                    }
                }
            }
        }
        comments = [
            self._make_comment("alice", "general comment 1"),
            self._make_comment("bob", "general comment 2"),
        ]
        alerts_response = [
            {
                "rule": {"description": "SQL injection"},
                "most_recent_instance": {
                    "message": {"text": "potential SQLi"},
                    "location": {"path": "src/foo.py", "start_line": 42},
                },
            }
        ]
        self._setup_mocks(
            mock_manager,
            graphql_response=graphql_response,
            comments=comments,
            alerts_response=alerts_response,
        )

        result = mock_manager.get_pr_feedback(42)

        assert len(result["unresolved_threads"]) == 2
        assert result["unresolved_threads"][0]["path"] == "src/foo.py"
        assert result["unresolved_threads"][0]["line"] == 10
        assert result["unresolved_threads"][0]["author"] == "alice"
        assert result["unresolved_threads"][0]["body"] == "issue here"
        assert result["unresolved_threads"][0]["diff_hunk"] == "@@ ... @@"
        assert result["resolved_thread_count"] == 1
        assert len(result["changes_requested"]) == 1
        assert result["changes_requested"][0]["author"] == "alice"
        assert result["changes_requested"][0]["body"] == "please fix"
        assert len(result["conversation_comments"]) == 2
        assert result["conversation_comments"][0]["author"] == "alice"
        assert result["conversation_comments"][0]["body"] == "general comment 1"
        assert len(result["alerts"]) == 1
        assert result["alerts"][0]["rule_description"] == "SQL injection"
        assert result["alerts"][0]["message"] == "potential SQLi"
        assert result["alerts"][0]["path"] == "src/foo.py"
        assert result["alerts"][0]["line"] == 42
        assert result["unavailable"] == {}

    def test_clean_state(self, mock_manager: PullRequestManager) -> None:
        """All sources return empty — empty PRFeedback, no unavailable entries."""
        graphql_response: dict[str, Any] = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {"nodes": []},
                        "reviews": {"nodes": []},
                    }
                }
            }
        }
        self._setup_mocks(
            mock_manager,
            graphql_response=graphql_response,
            comments=[],
            alerts_response=[],
        )

        result = mock_manager.get_pr_feedback(42)

        assert result["unresolved_threads"] == []
        assert result["resolved_thread_count"] == 0
        assert result["changes_requested"] == []
        assert result["conversation_comments"] == []
        assert result["alerts"] == []
        assert result["unavailable"] == {}

    def test_code_scanning_403_silent_skip(
        self, mock_manager: PullRequestManager
    ) -> None:
        """403 on code-scanning → empty alerts, NOT in unavailable."""
        graphql_response: dict[str, Any] = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {"nodes": []},
                        "reviews": {"nodes": []},
                    }
                }
            }
        }
        self._setup_mocks(
            mock_manager,
            graphql_response=graphql_response,
            comments=[],
            alerts_raises=GithubException(403, {"message": "forbidden"}, None),
        )

        result = mock_manager.get_pr_feedback(42)

        assert result["alerts"] == []
        assert "alerts" not in result["unavailable"]

    def test_code_scanning_500_unavailable(
        self, mock_manager: PullRequestManager
    ) -> None:
        """500 on code-scanning → empty alerts, 'alerts' in unavailable."""
        graphql_response: dict[str, Any] = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {"nodes": []},
                        "reviews": {"nodes": []},
                    }
                }
            }
        }
        self._setup_mocks(
            mock_manager,
            graphql_response=graphql_response,
            comments=[],
            alerts_raises=GithubException(500, {"message": "server error"}, None),
        )

        result = mock_manager.get_pr_feedback(42)

        assert result["alerts"] == []
        assert "alerts" in result["unavailable"]
        assert isinstance(result["unavailable"]["alerts"], GithubException)

    def test_code_scanning_alerts_unpacks_two_tuple(
        self, mock_manager: PullRequestManager
    ) -> None:
        """requestJsonAndCheck returns (headers, data) — a 2-tuple, not a 3-tuple."""
        alerts_response = [
            {
                "rule": {"description": "SQL injection"},
                "most_recent_instance": {
                    "message": {"text": "potential SQLi"},
                    "location": {"path": "src/foo.py", "start_line": 42},
                },
            }
        ]
        self._setup_mocks(mock_manager, alerts_response=alerts_response)

        alerts = fetch_code_scanning_alerts(mock_manager, 42)

        assert alerts is not None
        assert len(alerts) == 1
        assert alerts[0]["rule_description"] == "SQL injection"
        assert alerts[0]["message"] == "potential SQLi"
        assert alerts[0]["path"] == "src/foo.py"
        assert alerts[0]["line"] == 42

    def test_graphql_request_shape(self, mock_manager: PullRequestManager) -> None:
        """The direct call must reproduce `graphql_query`'s URL and payload.

        Every other test mocks `requestJsonAndCheck` and would pass against a
        wrong wrapper, so the request shape needs its own assertion.
        """
        self._setup_mocks(mock_manager, comments=[], alerts_response=[])

        mock_manager.get_pr_feedback(42)

        requester = mock_manager._github_client._Github__requester  # type: ignore[attr-defined]
        post = next(
            c
            for c in requester.requestJsonAndCheck.call_args_list
            if c.args[0] == "POST"
        )
        assert post.args[1] == requester.graphql_url
        payload = post.kwargs["input"]
        assert set(payload) == {"query", "variables"}
        assert payload["variables"] == {
            "owner": "test",
            "repo": "repo",
            "prNumber": 42,
        }
        assert "pullRequest(number: $prNumber)" in payload["query"]

    def test_repository_unavailable_fails_closed(
        self, mock_manager: PullRequestManager
    ) -> None:
        """Repository not accessible → flagged, not rendered as clean."""
        self._setup_mocks(mock_manager, comments=[], alerts_response=[])

        with patch.object(mock_manager, "_get_repository", return_value=None):
            result = mock_manager.get_pr_feedback(42)
            _, _, undeterminable = collect_pr_feedback(mock_manager, 42)

        assert _post_call_count(mock_manager) == 0
        exc = result["unavailable"]["threads"]
        assert isinstance(exc, ValueError)
        assert (
            render_exception_for_display(exc)
            == "ValueError — Repository not accessible"
        )
        assert undeterminable is True

    def test_graphql_http_failure(self, mock_manager: PullRequestManager) -> None:
        """GraphQL HTTP failure raises → 'threads' unavailable, not retried."""
        self._setup_mocks(
            mock_manager,
            graphql_raises=GithubException(500, {"message": "boom"}, None),
            comments=[],
            alerts_response=[],
        )

        with patch(
            "mcp_workspace.github_operations._pr_feedback_sources.time.sleep"
        ) as sleep:
            result = mock_manager.get_pr_feedback(42)

        assert _post_call_count(mock_manager) == 1
        sleep.assert_not_called()
        assert result["unresolved_threads"] == []
        assert result["resolved_thread_count"] == 0
        assert result["changes_requested"] == []
        assert "threads" in result["unavailable"]
        assert isinstance(result["unavailable"]["threads"], GithubException)

    def test_review_data_retry_then_success(
        self, mock_manager: PullRequestManager
    ) -> None:
        """Null PR + non-permanent error, then success → retried once."""
        valid_response = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {
                                    "isResolved": False,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "author": {"login": "alice"},
                                                "body": "issue here",
                                                "path": "src/foo.py",
                                                "line": 10,
                                                "diffSide": "RIGHT",
                                                "diffHunk": "@@ ... @@",
                                            }
                                        ]
                                    },
                                }
                            ]
                        },
                        "reviews": {"nodes": []},
                    }
                }
            }
        }
        self._setup_mocks(
            mock_manager,
            graphql_responses=[
                _null_pr_body({"message": "Could not resolve to a PullRequest"}),
                valid_response,
            ],
            comments=[],
            alerts_response=[],
        )

        with patch(
            "mcp_workspace.github_operations._pr_feedback_sources.time.sleep"
        ) as sleep:
            result = mock_manager.get_pr_feedback(42)

        assert _post_call_count(mock_manager) == 2
        assert len(result["unresolved_threads"]) == 1
        assert result["unresolved_threads"][0]["author"] == "alice"
        assert "threads" not in result["unavailable"]
        assert sleep.call_count == 1

    def test_review_data_retry_exhausted_unavailable(
        self, mock_manager: PullRequestManager
    ) -> None:
        """Persistent null PR + non-permanent error → 3 attempts, then flagged."""
        self._setup_mocks(
            mock_manager,
            graphql_response=_null_pr_body({"message": "Could not resolve"}),
            comments=[],
            alerts_response=[],
        )

        with patch(
            "mcp_workspace.github_operations._pr_feedback_sources.time.sleep"
        ) as sleep:
            result = mock_manager.get_pr_feedback(42)

        assert _post_call_count(mock_manager) == 3
        assert "threads" in result["unavailable"]
        assert isinstance(result["unavailable"]["threads"], GithubException)
        assert sleep.call_count == 2

    def test_permanent_error_not_retried(
        self, mock_manager: PullRequestManager
    ) -> None:
        """A permanent error type gives up after one attempt."""
        self._setup_mocks(
            mock_manager,
            graphql_response=_null_pr_body(
                {"type": "FORBIDDEN", "message": "Resource not accessible"}
            ),
            comments=[],
            alerts_response=[],
        )

        with patch(
            "mcp_workspace.github_operations._pr_feedback_sources.time.sleep"
        ) as sleep:
            result = mock_manager.get_pr_feedback(42)

        assert _post_call_count(mock_manager) == 1
        sleep.assert_not_called()
        assert "threads" in result["unavailable"]

    def test_message_less_permanent_error_not_retried(
        self, mock_manager: PullRequestManager
    ) -> None:
        """A permanent error type with no message still stops the retry loop."""
        self._setup_mocks(
            mock_manager,
            graphql_response=_null_pr_body({"type": "RATE_LIMITED"}),
            comments=[],
            alerts_response=[],
        )

        with patch(
            "mcp_workspace.github_operations._pr_feedback_sources.time.sleep"
        ) as sleep:
            result = mock_manager.get_pr_feedback(42)

        assert _post_call_count(mock_manager) == 1
        sleep.assert_not_called()
        assert "threads" in result["unavailable"]

    def test_usable_data_with_errors_not_retried(
        self, mock_manager: PullRequestManager
    ) -> None:
        """Data came back alongside errors → no retry, but still flagged."""
        body: dict[str, Any] = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {"nodes": []},
                        "reviews": {"nodes": []},
                    }
                }
            },
            "errors": [{"message": "something partial"}],
        }
        self._setup_mocks(
            mock_manager,
            graphql_response=body,
            comments=[],
            alerts_response=[],
        )

        with patch(
            "mcp_workspace.github_operations._pr_feedback_sources.time.sleep"
        ) as sleep:
            result = mock_manager.get_pr_feedback(42)

        assert _post_call_count(mock_manager) == 1
        sleep.assert_not_called()
        assert "threads" in result["unavailable"]

    def test_partial_data_threads_nulled_still_recovers_reviews(
        self, mock_manager: PullRequestManager
    ) -> None:
        """reviewThreads errored → reviews still recovered, threads flagged."""
        body: dict[str, Any] = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": None,
                        "reviews": {
                            "nodes": [
                                {
                                    "state": "CHANGES_REQUESTED",
                                    "author": {"login": "alice"},
                                    "body": "fix",
                                }
                            ]
                        },
                    }
                }
            },
            "errors": [
                {
                    "type": "FORBIDDEN",
                    "message": "Resource not accessible",
                    "path": ["repository", "pullRequest", "reviewThreads"],
                }
            ],
        }
        self._setup_mocks(
            mock_manager, graphql_response=body, comments=[], alerts_response=[]
        )

        result = mock_manager.get_pr_feedback(42)

        assert len(result["changes_requested"]) == 1
        assert result["changes_requested"][0]["author"] == "alice"
        assert "threads" in result["unavailable"]
        assert (
            render_exception_for_display(result["unavailable"]["threads"])
            == "GraphQL FORBIDDEN — Resource not accessible"
        )

    def test_partial_data_reviews_nulled_still_recovers_threads(
        self, mock_manager: PullRequestManager
    ) -> None:
        """reviews errored → unresolved threads still recovered, threads flagged."""
        body: dict[str, Any] = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {
                                    "isResolved": False,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "author": {"login": "bob"},
                                                "body": "issue here",
                                                "path": "src/foo.py",
                                                "line": 10,
                                                "diffSide": "RIGHT",
                                                "diffHunk": "@@ ... @@",
                                            }
                                        ]
                                    },
                                }
                            ]
                        },
                        "reviews": None,
                    }
                }
            },
            "errors": [
                {
                    "type": "FORBIDDEN",
                    "message": "Resource not accessible",
                    "path": ["repository", "pullRequest", "reviews"],
                }
            ],
        }
        self._setup_mocks(
            mock_manager, graphql_response=body, comments=[], alerts_response=[]
        )

        result = mock_manager.get_pr_feedback(42)

        assert len(result["unresolved_threads"]) == 1
        assert result["unresolved_threads"][0]["author"] == "bob"
        assert result["changes_requested"] == []
        assert "threads" in result["unavailable"]
        assert (
            render_exception_for_display(result["unavailable"]["threads"])
            == "GraphQL FORBIDDEN — Resource not accessible"
        )

    def test_null_thread_nodes_skipped_siblings_recovered(
        self, mock_manager: PullRequestManager
    ) -> None:
        """A nulled thread node and a nulled comment skip only themselves."""
        body: dict[str, Any] = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                None,
                                {
                                    "isResolved": False,
                                    "comments": {"nodes": [None]},
                                },
                                {
                                    "isResolved": False,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "author": {"login": "bob"},
                                                "body": "issue here",
                                                "path": "src/foo.py",
                                                "line": 10,
                                                "diffSide": "RIGHT",
                                                "diffHunk": "@@ ... @@",
                                            }
                                        ]
                                    },
                                },
                            ]
                        },
                        "reviews": {"nodes": []},
                    }
                }
            },
            "errors": [
                {
                    "type": "FORBIDDEN",
                    "message": "Resource not accessible",
                    "path": ["repository", "pullRequest", "reviewThreads", "nodes", 0],
                }
            ],
        }
        self._setup_mocks(
            mock_manager, graphql_response=body, comments=[], alerts_response=[]
        )

        result = mock_manager.get_pr_feedback(42)

        assert len(result["unresolved_threads"]) == 1
        assert result["unresolved_threads"][0]["author"] == "bob"
        assert (
            render_exception_for_display(result["unavailable"]["threads"])
            == "GraphQL FORBIDDEN — Resource not accessible"
        )

    def test_null_review_nodes_skipped_threads_recovered(
        self, mock_manager: PullRequestManager
    ) -> None:
        """A nulled review node does not discard already-recovered threads."""
        body: dict[str, Any] = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {
                                    "isResolved": False,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "author": {"login": "bob"},
                                                "body": "issue here",
                                                "path": "src/foo.py",
                                                "line": 10,
                                                "diffSide": "RIGHT",
                                                "diffHunk": "@@ ... @@",
                                            }
                                        ]
                                    },
                                }
                            ]
                        },
                        "reviews": {
                            "nodes": [
                                None,
                                {
                                    "state": "CHANGES_REQUESTED",
                                    "author": {"login": "alice"},
                                    "body": "fix",
                                },
                            ]
                        },
                    }
                }
            },
            "errors": [
                {
                    "type": "FORBIDDEN",
                    "message": "Resource not accessible",
                    "path": ["repository", "pullRequest", "reviews", "nodes", 0],
                }
            ],
        }
        self._setup_mocks(
            mock_manager, graphql_response=body, comments=[], alerts_response=[]
        )

        result = mock_manager.get_pr_feedback(42)

        assert len(result["unresolved_threads"]) == 1
        assert result["unresolved_threads"][0]["author"] == "bob"
        assert len(result["changes_requested"]) == 1
        assert result["changes_requested"][0]["author"] == "alice"
        assert (
            render_exception_for_display(result["unavailable"]["threads"])
            == "GraphQL FORBIDDEN — Resource not accessible"
        )

    def test_single_not_found_yields_unknown_object_exception(
        self, mock_manager: PullRequestManager
    ) -> None:
        """A lone NOT_FOUND is retried and surfaces as UnknownObjectException."""
        self._setup_mocks(
            mock_manager,
            graphql_response=_null_pr_body(
                {"type": "NOT_FOUND", "message": "Could not resolve to a PullRequest"}
            ),
            comments=[],
            alerts_response=[],
        )

        with patch(
            "mcp_workspace.github_operations._pr_feedback_sources.time.sleep"
        ) as sleep:
            result = mock_manager.get_pr_feedback(42)

        assert _post_call_count(mock_manager) == 3
        assert sleep.call_count == 2
        exc = result["unavailable"]["threads"]
        assert isinstance(exc, UnknownObjectException)
        assert exc.status == 404
        assert exc.message == "Could not resolve to a PullRequest"

    def test_multiple_errors_yield_plain_github_exception(
        self, mock_manager: PullRequestManager
    ) -> None:
        """Two errors → plain GithubException 400 with no message."""
        self._setup_mocks(
            mock_manager,
            graphql_response=_null_pr_body(
                {"type": "NOT_FOUND", "message": "first"},
                {"type": "NOT_FOUND", "message": "second"},
            ),
            comments=[],
            alerts_response=[],
        )

        with patch("mcp_workspace.github_operations._pr_feedback_sources.time.sleep"):
            result = mock_manager.get_pr_feedback(42)

        exc = result["unavailable"]["threads"]
        assert type(exc) is GithubException  # pylint: disable=unidiomatic-typecheck
        assert exc.status == 400
        assert exc.message is None

    def test_null_pull_request_no_errors_flagged(
        self, mock_manager: PullRequestManager
    ) -> None:
        """Null pullRequest with no errors → synthesized status-200 exception."""
        self._setup_mocks(
            mock_manager,
            graphql_response=_null_pr_body(),
            comments=[],
            alerts_response=[],
        )

        with patch(
            "mcp_workspace.github_operations._pr_feedback_sources.time.sleep"
        ) as sleep:
            result = mock_manager.get_pr_feedback(42)

        assert _post_call_count(mock_manager) == 3
        assert sleep.call_count == 2
        exc = result["unavailable"]["threads"]
        assert isinstance(exc, GithubException)
        assert exc.status == 200
        assert (
            render_exception_for_display(exc)
            == "GraphQL error — pullRequest not returned"
        )

    def test_null_pull_request_with_error_flagged(
        self, mock_manager: PullRequestManager
    ) -> None:
        """A real GraphQL error wins over the synthesized 'not returned' one."""
        self._setup_mocks(
            mock_manager,
            graphql_response=_null_pr_body(
                {"message": "Field 'x' doesn't exist on type 'Y'"}
            ),
            comments=[],
            alerts_response=[],
        )

        with patch(
            "mcp_workspace.github_operations._pr_feedback_sources.time.sleep"
        ) as sleep:
            result = mock_manager.get_pr_feedback(42)

        assert _post_call_count(mock_manager) == 3
        assert sleep.call_count == 2
        assert (
            render_exception_for_display(result["unavailable"]["threads"])
            == "GraphQL error — Field 'x' doesn't exist on type 'Y'"
        )

    def test_returned_graphql_error_logged_at_warning(
        self, mock_manager: PullRequestManager, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The returned (not raised) exception still gets its own WARNING log."""
        self._setup_mocks(
            mock_manager,
            graphql_response=_null_pr_body(
                {"type": "FORBIDDEN", "message": "Resource not accessible"}
            ),
            comments=[],
            alerts_response=[],
        )

        with caplog.at_level(
            logging.WARNING, logger="mcp_workspace.github_operations.pr_manager"
        ):
            mock_manager.get_pr_feedback(42)

        assert "Failed to fetch review data for PR #42" in caplog.text

    def test_conversation_comments_failure(
        self, mock_manager: PullRequestManager
    ) -> None:
        """Comments fetch raises → 'comments' in unavailable, comments empty."""
        graphql_response: dict[str, Any] = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {"nodes": []},
                        "reviews": {"nodes": []},
                    }
                }
            }
        }
        self._setup_mocks(
            mock_manager,
            graphql_response=graphql_response,
            comments_raises=GithubException(500, {"message": "boom"}, None),
            alerts_response=[],
        )

        result = mock_manager.get_pr_feedback(42)

        assert result["conversation_comments"] == []
        assert "comments" in result["unavailable"]
        assert isinstance(result["unavailable"]["comments"], GithubException)

    def test_conversation_comments_transferred_raises(
        self, mock_manager: PullRequestManager
    ) -> None:
        """The inherited guard fires on the PR-feedback REST fetch too."""
        mock_repo = self._setup_mocks(mock_manager)
        mock_repo.get_issue = Mock(
            return_value=make_mock_issue(220, repo_full_name="test/other-repo")
        )

        with pytest.raises(IssueIdentityMismatchError):
            fetch_conversation_comments(mock_manager, 72)

    def test_conversation_comments_transferred_reported_unavailable(
        self, mock_manager: PullRequestManager
    ) -> None:
        """Through get_pr_feedback the guard surfaces as unavailable['comments']."""
        graphql_response: dict[str, Any] = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {"nodes": []},
                        "reviews": {"nodes": []},
                    }
                }
            }
        }
        mock_repo = self._setup_mocks(
            mock_manager,
            graphql_response=graphql_response,
            alerts_response=[],
        )
        transferred = make_mock_issue(220, repo_full_name="test/other-repo")
        mock_repo.get_issue = Mock(return_value=transferred)

        result = mock_manager.get_pr_feedback(72)

        assert result["conversation_comments"] == []
        reason = result["unavailable"]["comments"]
        assert isinstance(reason, IssueIdentityMismatchError)
        assert "was transferred to test/other-repo#220" in str(reason)
        transferred.get_comments.assert_not_called()

    def test_invalid_pr_number(self, mock_manager: PullRequestManager) -> None:
        """pr_number=0 → empty PRFeedback."""
        result = mock_manager.get_pr_feedback(0)

        assert result["unresolved_threads"] == []
        assert result["resolved_thread_count"] == 0
        assert result["changes_requested"] == []
        assert result["conversation_comments"] == []
        assert result["alerts"] == []
        assert result["unavailable"] == {}


@pytest.mark.git_integration
class TestMergeableStateField:
    """Verify mergeable_state flows through PullRequestData unchanged."""

    @pytest.mark.parametrize(
        "state_value", ["clean", "dirty", "unstable", "blocked", None]
    )
    @patch("mcp_workspace.github_operations._client.Github")
    def test_get_pull_request_mergeable_state_flows_through(
        self,
        mock_github: Mock,
        state_value: Any,
        tmp_path: Path,
    ) -> None:
        """mergeable_state flows from PyGithub PR to PullRequestData unchanged."""
        git_dir = tmp_path / "git_dir"
        git_dir.mkdir()
        repo = git.Repo.init(git_dir)
        repo.create_remote("origin", "https://github.com/test/repo.git")

        mock_pr = MagicMock()
        mock_pr.number = 123
        mock_pr.title = "Test PR"
        mock_pr.body = "Test description"
        mock_pr.state = "open"
        mock_pr.head.ref = "feature-branch"
        mock_pr.base.ref = "main"
        mock_pr.html_url = "https://github.com/test/repo/pull/123"
        mock_pr.mergeable = True
        mock_pr.mergeable_state = state_value
        mock_pr.merged = False
        mock_pr.draft = False
        mock_pr.created_at.isoformat.return_value = "2023-01-01T00:00:00Z"
        mock_pr.updated_at.isoformat.return_value = "2023-01-01T00:00:00Z"
        mock_pr.user.login = "testuser"

        mock_repo = MagicMock()
        mock_repo.get_pull.return_value = mock_pr
        mock_github_client = MagicMock()
        mock_github_client.get_repo.return_value = mock_repo
        mock_github.return_value = mock_github_client

        with patch(
            "mcp_workspace.github_operations.base_manager.get_github_token",
            return_value="dummy-token",
        ):
            manager = PullRequestManager(git_dir)
            result = manager.get_pull_request(123)
            assert result["mergeable_state"] == state_value
