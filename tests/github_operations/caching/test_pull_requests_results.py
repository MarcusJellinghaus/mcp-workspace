"""Tests for PullRequestCache layer 2: the four fingerprinted result slots."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from unittest.mock import Mock

import pytest
from github.GithubException import GithubException

from mcp_workspace.github_operations.caching._store import cache_file_path
from mcp_workspace.github_operations.caching.errors import GitHubRateLimitError
from mcp_workspace.github_operations.caching.pull_requests import (
    OpenPullRequest,
    PullRequestCache,
    _fetch_ci_status,
)
from mcp_workspace.github_operations.issues.types import IssueData
from mcp_workspace.github_operations.pr_feedback_mixin import (
    PRFeedbackMixin,
    _empty_pr_feedback,
)
from mcp_workspace.github_operations.pr_manager import PullRequestManager
from mcp_workspace.github_operations.pr_types import PRFeedback
from mcp_workspace.utils.repo_identifier import RepoIdentifier
from mcp_workspace.utils.timezone_utils import format_for_cache, utc_now

_REPO = RepoIdentifier("o", "r")
_CREATED = datetime(2026, 10, 27, 9, 0, tzinfo=timezone.utc)
_PR_UPDATED = "2026-10-27T10:00:00+00:00"
_ISSUE_UPDATED = "2026-10-27T08:00:00+00:00"


def _open_pr(number: int = 5, **overrides: Any) -> OpenPullRequest:
    pr = OpenPullRequest(
        number=number,
        head_branch=f"{number}-x",
        head_sha=f"sha{number}",
        head_label=f"o:{number}-x",
        base_branch="main",
        updated_at=_PR_UPDATED,
        user="alice",
        author_association="OWNER",
        draft=False,
    )
    pr.update(overrides)  # type: ignore[typeddict-item]
    return pr


def _issue(number: int = 5, updated_at: str = _ISSUE_UPDATED) -> IssueData:
    return IssueData(
        number=number,
        title="t",
        body="",
        state="open",
        labels=["status-01"],
        assignees=[],
        user="alice",
        created_at=None,
        updated_at=updated_at,
        url="",
        locked=False,
        author_association="OWNER",
    )


def _run(status: str = "completed", conclusion: Optional[str] = "success") -> Mock:
    run = Mock()
    run.id = 100
    run.status = status
    run.conclusion = conclusion
    run.name = "CI"
    run.event = "pull_request"
    run.path = ".github/workflows/ci.yml"
    run.head_sha = "sha5"
    run.created_at = _CREATED
    run.html_url = "https://example/run/100"
    run.jobs.side_effect = AssertionError("run.jobs() called")
    return run


def _feedback(unavailable: Optional[dict[str, Exception]] = None) -> PRFeedback:
    return {
        "unresolved_threads": [],
        "resolved_thread_count": 1,
        "changes_requested": [],
        "conversation_comments": [
            {
                "author": "bob",
                "body": "hi",
                "id": 1,
                "created_at": None,
                "author_association": "MEMBER",
            }
        ],
        "alerts": [],
        "unavailable": unavailable or {},
        "skipped": {},
    }


def _event() -> Mock:
    event = Mock()
    event.event = "labeled"
    event.label.name = "status-01"
    event.actor.login = "bob"
    event.created_at = _CREATED
    return event


def _rate_limit() -> GithubException:
    return GithubException(
        403, {"message": "API rate limit exceeded"}, {"X-RateLimit-Remaining": "0"}
    )


def _server_error() -> GithubException:
    return GithubException(500, {"message": "boom"}, {})


class _Env:
    """A mocked repo + PullRequestManager whose call counts span several runs."""

    def __init__(self, prs: Optional[list[int]] = None) -> None:
        numbers = prs if prs is not None else [5]
        self.repo = Mock()
        self.repo.get_pulls.return_value = [_pr_list_item(n) for n in numbers]
        self.base_tip = "tip-main"
        self.repo.get_branch.side_effect = lambda _name: Mock(
            commit=Mock(sha=self.base_tip)
        )
        self.mergeable: Optional[str] = "clean"
        self.repo.get_pull.side_effect = lambda _n: Mock(mergeable_state=self.mergeable)
        self.runs: list[Mock] = [_run()]
        self.repo.get_workflow_runs.side_effect = lambda **_kw: list(self.runs)

        self.manager = Mock(spec=PullRequestManager)
        self.manager.repo_identifier = _REPO
        self.manager._get_repository.return_value = self.repo
        self.manager._collect_pr_feedback.side_effect = lambda *_a, **_kw: (_feedback())
        self.issue = Mock()
        self.issue.get_events.return_value = [_event()]
        self.manager._get_issue_checked.return_value = self.issue

    def load(self) -> PullRequestCache:
        return PullRequestCache.load(self.manager)


def _pr_list_item(number: int) -> Mock:
    pr = Mock()
    pr.number = number
    pr.head.ref = f"{number}-x"
    pr.head.sha = f"sha{number}"
    pr.head.label = f"o:{number}-x"
    pr.base.ref = "main"
    pr.updated_at = datetime.fromisoformat(_PR_UPDATED)
    pr.user.login = "alice"
    pr.author_association = "OWNER"
    pr.draft = False
    return pr


def _path() -> Any:
    return cache_file_path(_REPO, "prs")


def _read() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(_path().read_text(encoding="utf-8"))
    return data


def _age_snapshot(seconds: int = 120) -> None:
    """Move the saved snapshot's fetched_at past the duplicate-protection window."""
    data = _read()
    data["snapshot"]["fetched_at"] = format_for_cache(
        utc_now() - timedelta(seconds=seconds)
    )
    _path().write_text(json.dumps(data), encoding="utf-8")


def _expire_slot(number: int, slot: str) -> None:
    data = _read()
    data["results"][str(number)][slot]["expires_at"] = format_for_cache(
        utc_now() - timedelta(seconds=1)
    )
    _path().write_text(json.dumps(data), encoding="utf-8")


def _one_run(env: _Env, method: str, pr: OpenPullRequest, issue: IssueData) -> Any:
    """Load, call one slot method, save."""
    cache = env.load()
    value = getattr(cache, method)(pr, issue)
    cache.save()
    return value


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
    def test_not_final_not_stored(self, state: Optional[str]) -> None:
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
        env.manager._collect_pr_feedback.side_effect = (
            lambda n, include_alerts=True: PRFeedbackMixin._collect_pr_feedback(
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
