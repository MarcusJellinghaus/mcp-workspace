"""Tests for PullRequestCache's alerts slot (code-scanning alerts of a PR head)."""

from __future__ import annotations

from typing import Iterator
from unittest.mock import Mock, patch

import pytest
from github.GithubException import GithubException, UnknownObjectException
from requests.exceptions import RetryError

from mcp_workspace.github_operations.caching.errors import GitHubRateLimitError
from mcp_workspace.github_operations.pr_types import AlertData

from ..conftest import make_retry_error
from ._pr_cache_test_helpers import (
    _age_snapshot,
    _Env,
    _expire_slot,
    _issue,
    _one_run,
    _open_pr,
    _path,
    _rate_limit,
    _read,
    _run,
    _server_error,
)

_FETCH = (
    "mcp_workspace.github_operations._pr_feedback_sources.fetch_code_scanning_alerts"
)

_ALERTS: list[AlertData] = [
    {
        "number": 1,
        "rule_id": "py/sql-injection",
        "rule_description": "SQL injection",
        "message": "Unsanitized input",
        "path": "src/a.py",
        "line": 12,
    },
    {
        "number": 2,
        "rule_id": "py/unused",
        "rule_description": "Unused import",
        "message": "Unused",
        "path": "src/b.py",
        "line": None,
    },
]


@pytest.fixture(name="fetch")
def _fetch() -> Iterator[Mock]:
    with patch(_FETCH, return_value=[]) as mock:
        yield mock


def _stored() -> bool:
    # A run that stores nothing writes no file at all.
    return _path().exists() and "alerts" in _read()["results"].get("5", {})


class TestFingerprint:
    """Fingerprint of the alerts slot."""

    def test_cached_on_unchanged_fp(self, fetch: Mock) -> None:
        env = _Env()
        _one_run(env, "alerts", _open_pr(), _issue())
        _one_run(env, "alerts", _open_pr(), _issue())
        fetch.assert_called_once_with(env.manager, 5)

    def test_head_sha_change_refetches(self, fetch: Mock) -> None:
        env = _Env()
        _one_run(env, "alerts", _open_pr(), _issue())
        _one_run(env, "alerts", _open_pr(head_sha="new"), _issue())
        assert fetch.call_count == 2

    def test_issue_updated_at_change_refetches(self, fetch: Mock) -> None:
        env = _Env()
        _one_run(env, "alerts", _open_pr(), _issue())
        _one_run(env, "alerts", _open_pr(), _issue(updated_at="later"))
        assert fetch.call_count == 2


class TestStoredResults:
    """What a fresh fetch stores, and that a hit equals it."""

    @pytest.mark.parametrize(
        "outcome",
        [_ALERTS, GithubException(403, {"message": "Resource not accessible"}, {})],
        ids=["alerts", "skip-403"],
    )
    def test_json_round_trip(
        self, fetch: Mock, outcome: list[AlertData] | Exception
    ) -> None:
        if isinstance(outcome, Exception):
            fetch.side_effect = outcome
        else:
            fetch.return_value = outcome
        env = _Env()
        first = _one_run(env, "alerts", _open_pr(), _issue())
        second = _one_run(env, "alerts", _open_pr(), _issue())
        assert second == first
        assert fetch.call_count == 1
        if isinstance(outcome, Exception):
            assert first == {"alerts": [], "skipped": 403, "final": True}
        else:
            assert first == {"alerts": _ALERTS, "skipped": None, "final": True}

    def test_404_skip_stored(self, fetch: Mock) -> None:
        fetch.side_effect = UnknownObjectException(404, {"message": "no analysis"}, {})
        env = _Env()
        result = _one_run(env, "alerts", _open_pr(), _issue())
        assert result == {"alerts": [], "skipped": 404, "final": True}
        assert _stored()


class TestCiGate:
    """Alerts are fetched and stored only once CI on the head is final."""

    @pytest.mark.parametrize(
        "runs",
        [
            [_run("in_progress", None)],
            [_run("completed", "failure"), _run("in_progress", None)],
            [],
        ],
        ids=["in-progress", "failure-with-in-progress", "no-runs"],
    )
    def test_not_final(self, fetch: Mock, runs: list[Mock]) -> None:
        env = _Env()
        env.runs = runs
        result = _one_run(env, "alerts", _open_pr(), _issue())
        assert result == {"alerts": [], "skipped": None, "final": False}
        fetch.assert_not_called()
        assert not _stored()
        _one_run(env, "alerts", _open_pr(), _issue())
        assert env.repo.get_workflow_runs.call_count == 2

    @pytest.mark.parametrize("conclusion", ["skipped", "neutral"])
    def test_skipped_or_neutral_run_is_final(
        self, fetch: Mock, conclusion: str
    ) -> None:
        env = _Env()
        env.runs = [_run(), _run("completed", conclusion)]
        result = _one_run(env, "alerts", _open_pr(), _issue())
        assert result["final"] is True
        assert _stored()
        fetch.assert_called_once()

    def test_ci_hit_from_disk(self, fetch: Mock) -> None:
        env = _Env()
        _one_run(env, "ci_status", _open_pr(), _issue())
        result = _one_run(env, "alerts", _open_pr(), _issue())
        assert result["final"] is True
        assert _read()["results"]["5"]["alerts"]["value"]["final"] is True
        assert env.repo.get_workflow_runs.call_count == 1
        fetch.assert_called_once()

    def test_alerts_hit_while_ci_expired(self, fetch: Mock) -> None:
        env = _Env()
        _one_run(env, "alerts", _open_pr(), _issue())
        _expire_slot(5, "ci")
        _one_run(env, "alerts", _open_pr(), _issue())
        assert env.repo.get_workflow_runs.call_count == 1
        fetch.assert_called_once()

    def test_same_run_ci_status_then_alerts(self, fetch: Mock) -> None:
        env = _Env()
        cache = env.load()
        cache.ci_status(_open_pr(), _issue())
        cache.alerts(_open_pr(), _issue())
        assert env.repo.get_workflow_runs.call_count == 1
        fetch.assert_called_once()


class TestErrors:
    """Errors raised from alerts() are never stored."""

    @pytest.mark.parametrize(
        "error",
        [_rate_limit(), make_retry_error(403), RetryError()],
        ids=["rate-limit", "retry-403", "retry-unknown"],
    )
    def test_rate_limit_raises_and_save_is_noop(
        self, fetch: Mock, error: Exception
    ) -> None:
        fetch.side_effect = error
        env = _Env()
        cache = env.load()
        cache.find_pr("5-x")
        with pytest.raises(GitHubRateLimitError):
            cache.alerts(_open_pr(), _issue())
        cache.save()
        assert not _path().exists()

    @pytest.mark.parametrize(
        "error",
        [_server_error(), make_retry_error(500)],
        ids=["server-error", "retry-500"],
    )
    def test_error_raises_not_stored(self, fetch: Mock, error: Exception) -> None:
        fetch.side_effect = error
        env = _Env()
        cache = env.load()
        cache.find_pr("5-x")
        with pytest.raises(type(error)):
            cache.alerts(_open_pr(), _issue())
        cache.save()
        assert not _stored()

    def test_repository_unavailable_raises_not_stored(self, fetch: Mock) -> None:
        env = _Env()
        _one_run(env, "ci_status", _open_pr(), _issue())  # CI hit on disk
        env.manager._get_repository.return_value = None

        cache = env.load()
        with pytest.raises(RuntimeError):
            cache.alerts(_open_pr(), _issue())
        cache.save()

        assert not _stored()
        fetch.assert_not_called()

    def test_ci_failure_propagates(self, fetch: Mock) -> None:
        env = _Env()
        env.repo.get_workflow_runs.side_effect = _server_error()
        with pytest.raises(GithubException):
            env.load().alerts(_open_pr(), _issue())
        fetch.assert_not_called()


class TestSlotOnlyRun:
    """A run that calls alerts() without find_pr still saves its result."""

    @pytest.mark.usefixtures("fetch")
    def test_result_written_to_disk(self) -> None:
        env = _Env()
        _one_run(env, "alerts", _open_pr(), _issue())
        assert "alerts" in _read()["results"]["5"]


class TestSteadyState:
    """Acceptance: a second pass with unchanged fingerprints only lists PRs."""

    def test_one_repo_call_and_pruning(self, fetch: Mock) -> None:
        env = _Env([1, 2, 3])

        def full_pass(numbers: list[int]) -> None:
            cache = env.load()
            for n in numbers:
                pr = cache.find_pr(f"{n}-x")
                assert pr is not None
                issue = _issue(n)
                cache.ci_status(pr, issue)
                assert cache.alerts(pr, issue)["final"] is True
            cache.save()

        full_pass([1, 2, 3])
        _age_snapshot()
        env.repo.reset_mock()
        fetch.reset_mock()

        full_pass([1, 2, 3])

        assert len(env.repo.method_calls) == 1
        env.repo.get_pulls.assert_called_once()
        env.repo.get_workflow_runs.assert_not_called()
        fetch.assert_not_called()

        env.repo.get_pulls.return_value = env.repo.get_pulls.return_value[:2]
        _age_snapshot()
        full_pass([1, 2])
        assert "3" not in _read()["results"]
