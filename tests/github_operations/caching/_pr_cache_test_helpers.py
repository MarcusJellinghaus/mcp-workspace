"""Shared helpers for the PullRequestCache tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import Mock

from github.GithubException import GithubException

from mcp_workspace.github_operations.caching._store import cache_file_path
from mcp_workspace.github_operations.caching.pull_requests import (
    OpenPullRequest,
    PullRequestCache,
)
from mcp_workspace.github_operations.issues.types import IssueData
from mcp_workspace.github_operations.pr_manager import PullRequestManager
from mcp_workspace.github_operations.pr_types import PRFeedback
from mcp_workspace.utils.repo_identifier import RepoIdentifier
from mcp_workspace.utils.timezone_utils import format_for_cache, utc_now

_REPO = RepoIdentifier("o", "r")
_CREATED = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)
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


def _run(status: str = "completed", conclusion: str | None = "success") -> Mock:
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


def _feedback(unavailable: dict[str, Exception] | None = None) -> PRFeedback:
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

    def __init__(self, prs: list[int] | None = None) -> None:
        numbers = prs if prs is not None else [5]
        self.repo = Mock()
        self.repo.get_pulls.return_value = [_pr_list_item(n) for n in numbers]
        self.base_tip = "tip-main"
        self.repo.get_branch.side_effect = lambda _name: Mock(
            commit=Mock(sha=self.base_tip)
        )
        self.mergeable: str | None = "clean"
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
