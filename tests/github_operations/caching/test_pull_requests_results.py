"""Tests for PullRequestCache layer 2: the four fingerprinted result slots."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from github.GithubException import GithubException

from mcp_workspace.github_operations.caching.errors import GitHubRateLimitError
from mcp_workspace.github_operations.caching.pull_requests import _fetch_ci_status
from mcp_workspace.github_operations.pr_feedback_mixin import (
    PRFeedbackMixin,
    _empty_pr_feedback,
)

from ._pr_cache_test_helpers import (
    _CREATED,
    _age_snapshot,
    _Env,
    _expire_slot,
    _feedback,
    _issue,
    _one_run,
    _open_pr,
    _path,
    _rate_limit,
    _read,
    _run,
    _server_error,
)


class TestMergeableState:
    """Fingerprint of the mergeable_state slot."""

    def test_cached_on_unchanged_fp(self) -> None:
        env = _Env()
        assert _one_run(env, "mergeable_state", _open_pr(), _issue()) == "clean"
        assert _one_run(env, "mergeable_state", _open_pr(), _issue()) == "clean"
        assert env.repo.get_pull.call_count == 1

    def test_head_sha_change_refetches(self) -> None:
        env = _Env()
        _one_run(env, "mergeable_state", _open_pr(), _issue())
        _one_run(env, "mergeable_state", _open_pr(head_sha="new"), _issue())
        assert env.repo.get_pull.call_count == 2

    def test_base_tip_change_refetches(self) -> None:
        env = _Env()
        _one_run(env, "mergeable_state", _open_pr(), _issue())
        _age_snapshot()
        env.base_tip = "tip-moved"
        _one_run(env, "mergeable_state", _open_pr(), _issue())
        assert env.repo.get_pull.call_count == 2

    def test_issue_updated_at_change_refetches(self) -> None:
        env = _Env()
        _one_run(env, "mergeable_state", _open_pr(), _issue())
        _one_run(env, "mergeable_state", _open_pr(), _issue(updated_at="later"))
        assert env.repo.get_pull.call_count == 2

    @pytest.mark.parametrize("state", ["unknown", None])
    def test_not_final_not_stored(self, state: str | None) -> None:
        env = _Env()
        env.mergeable = state
        assert _one_run(env, "mergeable_state", _open_pr(), _issue()) == state
        _one_run(env, "mergeable_state", _open_pr(), _issue())
        assert env.repo.get_pull.call_count == 2

    def test_server_error_propagates_not_stored(self) -> None:
        env = _Env()
        env.repo.get_pull.side_effect = _server_error()
        cache = env.load()
        with pytest.raises(GithubException):
            cache.mergeable_state(_open_pr(), _issue())
        cache.save()
        assert "5" not in _read()["results"]


class TestCiStatus:
    """Fingerprint and finality of the ci slot."""

    def test_cached_on_unchanged_fp(self) -> None:
        env = _Env()
        first = _one_run(env, "ci_status", _open_pr(), _issue())
        second = _one_run(env, "ci_status", _open_pr(), _issue())
        assert first == second
        assert first["run"]["conclusion"] == "success"
        assert env.repo.get_workflow_runs.call_count == 1

    def test_head_sha_change_refetches(self) -> None:
        env = _Env()
        _one_run(env, "ci_status", _open_pr(), _issue())
        _one_run(env, "ci_status", _open_pr(head_sha="new"), _issue())
        assert env.repo.get_workflow_runs.call_count == 2

    def test_issue_updated_at_change_refetches(self) -> None:
        env = _Env()
        _one_run(env, "ci_status", _open_pr(), _issue())
        _one_run(env, "ci_status", _open_pr(), _issue(updated_at="later"))
        assert env.repo.get_workflow_runs.call_count == 2

    def test_in_progress_not_stored(self) -> None:
        env = _Env()
        env.runs = [_run("in_progress", None)]
        status = _one_run(env, "ci_status", _open_pr(), _issue())
        assert status["run"]["status"] == "in_progress"
        _one_run(env, "ci_status", _open_pr(), _issue())
        assert env.repo.get_workflow_runs.call_count == 2

    def test_no_runs_not_stored(self) -> None:
        env = _Env()
        env.runs = []
        assert _one_run(env, "ci_status", _open_pr(), _issue()) == {
            "run": {},
            "jobs": [],
        }
        _one_run(env, "ci_status", _open_pr(), _issue())
        assert env.repo.get_workflow_runs.call_count == 2

    def test_failure_with_other_run_in_progress_not_stored(self) -> None:
        env = _Env()
        env.runs = [_run("completed", "failure"), _run("in_progress", None)]
        status = _one_run(env, "ci_status", _open_pr(), _issue())
        assert (status["run"]["conclusion"], status["run"]["status"]) == (
            "failure",
            "completed",
        )
        _one_run(env, "ci_status", _open_pr(), _issue())
        assert env.repo.get_workflow_runs.call_count == 2

    def test_rate_limit_raises_and_save_is_noop(self) -> None:
        env = _Env()
        env.repo.get_workflow_runs.side_effect = _rate_limit()
        cache = env.load()
        cache.find_pr("5-x")
        with pytest.raises(GitHubRateLimitError):
            cache.ci_status(_open_pr(), _issue())
        cache.save()
        assert not _path().exists()


class TestFetchCiStatus:
    """Tests for the undecorated _fetch_ci_status."""

    def test_builds_run_data_without_jobs(self) -> None:
        repo = Mock()
        runs = [_run(), _run()]
        runs[1].id = 101
        repo.get_workflow_runs.return_value = runs
        status, final = _fetch_ci_status(repo, "sha5", "5-x")
        repo.get_workflow_runs.assert_called_once_with(head_sha="sha5")
        assert final is True
        assert status["jobs"] == []
        assert status["run"]["run_ids"] == [100, 101]
        assert status["run"]["branch"] == "5-x"
        assert status["run"]["commit_sha"] == "sha5"
        assert status["run"]["created_at"] == _CREATED.isoformat()
        for run in runs:
            run.jobs.assert_not_called()

    def test_error_propagates(self) -> None:
        repo = Mock()
        repo.get_workflow_runs.side_effect = _server_error()
        with pytest.raises(GithubException):
            _fetch_ci_status(repo, "sha5", "5-x")


class TestFeedback:
    """Fingerprint, finality and errors of the feedback slot."""

    def test_cached_on_unchanged_fp_without_alerts(self) -> None:
        env = _Env()
        first = _one_run(env, "feedback", _open_pr(), _issue())
        second = _one_run(env, "feedback", _open_pr(), _issue())
        assert first == second == _feedback()
        env.manager._collect_pr_feedback.assert_called_once_with(
            5, include_alerts=False
        )

    def test_pr_updated_at_change_refetches(self) -> None:
        env = _Env()
        _one_run(env, "feedback", _open_pr(), _issue())
        _one_run(env, "feedback", _open_pr(updated_at="later"), _issue())
        assert env.manager._collect_pr_feedback.call_count == 2

    def test_issue_updated_at_change_invalidates_feedback_and_ci(self) -> None:
        env = _Env()
        cache = env.load()
        cache.feedback(_open_pr(), _issue())
        cache.ci_status(_open_pr(), _issue())
        cache.save()

        relabelled = _issue(updated_at="later")
        cache = env.load()
        cache.feedback(_open_pr(), relabelled)
        cache.ci_status(_open_pr(), relabelled)
        assert env.manager._collect_pr_feedback.call_count == 2
        assert env.repo.get_workflow_runs.call_count == 2

    def test_unavailable_section_not_stored(self) -> None:
        env = _Env()
        env.manager._collect_pr_feedback.side_effect = lambda *_a, **_kw: _feedback(
            {"threads": _server_error()}
        )
        result = _one_run(env, "feedback", _open_pr(), _issue())
        assert "threads" in result["unavailable"]
        _one_run(env, "feedback", _open_pr(), _issue())
        assert env.manager._collect_pr_feedback.call_count == 2

    def test_rate_limited_section_raises_and_save_is_noop(self) -> None:
        env = _Env()
        env.manager._collect_pr_feedback.side_effect = lambda *_a, **_kw: _feedback(
            {"comments": _rate_limit()}
        )
        cache = env.load()
        cache.find_pr("5-x")
        with pytest.raises(GitHubRateLimitError):
            cache.feedback(_open_pr(), _issue())
        cache.save()
        assert not _path().exists()

    def test_graphql_rate_limited_threads_raises_and_save_is_noop(self) -> None:
        env = _Env()
        graphql_error = GithubException(
            400, {"data": None, "errors": [{"type": "RATE_LIMITED"}]}, {}
        )
        env.manager._collect_pr_feedback.side_effect = lambda *_a, **_kw: _feedback(
            {"threads": graphql_error}
        )
        cache = env.load()
        cache.find_pr("5-x")
        with pytest.raises(GitHubRateLimitError):
            cache.feedback(_open_pr(), _issue())
        cache.save()
        assert not _path().exists()

    def test_error_outside_sections_propagates_not_stored(self) -> None:
        env = _Env()
        env.manager._validate_pr_number.side_effect = _server_error()
        env.manager._collect_pr_feedback.side_effect = lambda n, include_alerts=True: (
            PRFeedbackMixin._collect_pr_feedback(
                env.manager, n, include_alerts=include_alerts
            )
        )

        # The decorated public method still swallows it into the empty default.
        assert PRFeedbackMixin.get_pr_feedback(env.manager, 5) == _empty_pr_feedback()

        cache = env.load()
        cache.find_pr("5-x")
        with pytest.raises(GithubException):
            cache.feedback(_open_pr(), _issue())
        cache.save()
        assert "5" not in _read()["results"]

        calls = env.manager._collect_pr_feedback.call_count
        with pytest.raises(GithubException):
            env.load().feedback(_open_pr(), _issue())
        assert env.manager._collect_pr_feedback.call_count == calls + 1


class TestLabelEvents:
    """Fingerprint of the label_events slot."""

    def test_cached_on_unchanged_fp(self) -> None:
        env = _Env()
        first = _one_run(env, "label_events", _open_pr(), _issue())
        second = _one_run(env, "label_events", _open_pr(), _issue())
        assert first == second
        assert first == [
            {
                "event": "labeled",
                "label": "status-01",
                "created_at": _CREATED.isoformat(),
                "actor": "bob",
            }
        ]
        assert env.issue.get_events.call_count == 1

    def test_issue_updated_at_change_refetches(self) -> None:
        env = _Env()
        _one_run(env, "label_events", _open_pr(), _issue())
        _one_run(env, "label_events", _open_pr(), _issue(updated_at="later"))
        assert env.issue.get_events.call_count == 2

    def test_repository_unavailable_raises_not_stored(self) -> None:
        env = _Env()
        cache = env.load()
        cache.find_pr("5-x")
        cache.save()  # snapshot on disk, reused by the next run
        env.manager._get_repository.return_value = None

        cache = env.load()
        with pytest.raises(RuntimeError):
            cache.label_events(_open_pr(), _issue())
        cache.save()

        assert "5" not in _read()["results"]
        env.issue.get_events.assert_not_called()


class TestSlotOnlyRun:
    """A run that calls a slot without find_pr still saves its result."""

    @pytest.mark.parametrize(
        ("method", "slot"),
        [
            ("ci_status", "ci"),
            ("feedback", "feedback"),
            ("label_events", "label_events"),
        ],
    )
    def test_result_written_to_disk(self, method: str, slot: str) -> None:
        env = _Env()
        _one_run(env, method, _open_pr(), _issue())
        assert slot in _read()["results"]["5"]


class TestExpiry:
    """The max-age safety net."""

    def test_expired_slot_refetched(self) -> None:
        env = _Env()
        _one_run(env, "mergeable_state", _open_pr(), _issue())
        _expire_slot(5, "mergeable_state")
        _one_run(env, "mergeable_state", _open_pr(), _issue())
        assert env.repo.get_pull.call_count == 2


class TestSteadyState:
    """Acceptance: unchanged fingerprints cost two repo calls per run."""

    def test_two_repo_calls(self) -> None:
        numbers = [1, 2, 3]
        env = _Env(numbers)

        def full_pass() -> None:
            cache = env.load()
            for n in numbers:
                pr = cache.find_pr(f"{n}-x")
                assert pr is not None
                issue = _issue(n)
                assert cache.mergeable_state(pr, issue) == "clean"
                cache.ci_status(pr, issue)
                cache.feedback(pr, issue)
                cache.label_events(pr, issue)
            cache.save()

        full_pass()
        _age_snapshot()
        env.repo.reset_mock()
        env.manager._collect_pr_feedback.reset_mock()
        env.issue.reset_mock()

        full_pass()

        assert env.repo.get_pulls.call_count == 1
        assert env.repo.get_branch.call_count == 1
        assert len(env.repo.method_calls) == 2
        env.repo.get_pull.assert_not_called()
        env.repo.get_workflow_runs.assert_not_called()
        env.manager._collect_pr_feedback.assert_not_called()
        env.issue.get_events.assert_not_called()
