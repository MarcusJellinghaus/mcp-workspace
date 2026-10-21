"""Tests for the one-shot re-read of a stale ``unstable`` mergeable_state."""

from pathlib import Path
from typing import Any, Iterator, Optional
from unittest.mock import MagicMock, patch

import pytest
from github.GithubException import GithubException, RateLimitExceededException

from mcp_workspace.checks.branch_status import (
    BranchStatusReport,
    collect_branch_status,
)
from mcp_workspace.checks.branch_status_rendering import CIStatus, LinkedBranchStatus
from mcp_workspace.github_operations.pr_checks_mixin import PERMISSION_ERROR_TEXT
from mcp_workspace.workflows.task_tracker import TaskTrackerStatus

_MODULE = "mcp_workspace.checks.branch_status"
_STALE = (
    "CI passed but GitHub reports mergeable_state=unstable — likely stale, re-check"
)


@pytest.fixture(name="env")
def fixture_env() -> Iterator[dict[str, MagicMock]]:
    """Patch every collaborator of collect_branch_status except CI and PR info."""
    pr_mgr = MagicMock()
    issue_mgr = MagicMock()
    issue_mgr.get_issue.return_value = {"number": 338, "labels": []}
    with (
        patch(f"{_MODULE}.get_current_branch_name", return_value="338-x"),
        patch(f"{_MODULE}.IssueManager", return_value=issue_mgr),
        patch(f"{_MODULE}.PullRequestManager", return_value=pr_mgr),
        patch(f"{_MODULE}.detect_base_branch", return_value="main"),
        patch(
            f"{_MODULE}._collect_linked_branch_status",
            return_value=(LinkedBranchStatus.OK, ("338-x",), 338, None),
        ),
        patch(f"{_MODULE}._collect_rebase_status", return_value=(False, "up-to-date")),
        patch(
            f"{_MODULE}._collect_task_status",
            return_value=(TaskTrackerStatus.N_A, "No pr_info folder found", False),
        ),
        patch(f"{_MODULE}.collect_pr_feedback", return_value=(None, False, False)),
        patch(f"{_MODULE}.get_default_branch_name", return_value="main"),
        patch(f"{_MODULE}._collect_ci_status") as ci,
        patch(f"{_MODULE}._collect_pr_info") as pr_info,
        patch("mcp_workspace.checks.branch_status_unstable.time.sleep") as sleep,
    ):
        yield {"pr_mgr": pr_mgr, "sleep": sleep, "ci": ci, "pr_info": pr_info}


def _run(
    env: dict[str, MagicMock],
    ci_status: CIStatus,
    state: Optional[str],
    reread: Any = None,
    checks: tuple[tuple[str, ...], Optional[str]] = ((), None),
) -> BranchStatusReport:
    """Configure CI/PR info, the re-read and the lookup, then collect."""
    env["ci"].return_value = (ci_status, None, [])
    env["pr_info"].return_value = (45, "https://url", True, True, state)
    if isinstance(reread, BaseException):
        env["pr_mgr"].get_pull_request.side_effect = reread
    else:
        env["pr_mgr"].get_pull_request.return_value = reread
    env["pr_mgr"].get_non_green_checks.return_value = checks
    return collect_branch_status(Path("/tmp"))


def _no_ready(report: BranchStatusReport) -> None:
    assert not any(r.startswith("Ready to merge") for r in report.recommendations)


def test_reread_clean_becomes_ready(env: dict[str, MagicMock]) -> None:
    """A re-read that returns clean is accepted; no check lookup."""
    report = _run(
        env,
        CIStatus.PASSED,
        "unstable",
        reread={"mergeable": True, "mergeable_state": "clean", "head_sha": "abc"},
    )
    env["pr_mgr"].get_pull_request.assert_called_once_with(45)
    env["sleep"].assert_called_once_with(5.0)
    env["pr_mgr"].get_non_green_checks.assert_not_called()
    assert report.pr_mergeable_state == "clean"
    assert "Ready to merge (squash-merge safe)" in report.recommendations


def test_not_configured_still_unstable_looks_up_with_head_sha(
    env: dict[str, MagicMock],
) -> None:
    """NOT_CONFIGURED CI also triggers the re-read and lookup."""
    _run(
        env,
        CIStatus.NOT_CONFIGURED,
        "unstable",
        reread={"mergeable": True, "mergeable_state": "unstable", "head_sha": "abc"},
    )
    env["pr_mgr"].get_non_green_checks.assert_called_once_with(45, "abc")


def test_still_unstable_with_names(env: dict[str, MagicMock]) -> None:
    """Non-green names reach the recommendation and both formats."""
    report = _run(
        env,
        CIStatus.PASSED,
        "unstable",
        reread={"mergeable": True, "mergeable_state": "unstable", "head_sha": "abc"},
        checks=(("codecov/patch (failure)",), None),
    )
    assert (
        "Not ready to merge — non-green checks: codecov/patch (failure)"
        in report.recommendations
    )
    line = "Non-green checks: codecov/patch (failure)"
    assert line in report.format_for_human()
    assert line in report.format_for_llm()
    _no_ready(report)


def test_still_unstable_no_names_is_stale(env: dict[str, MagicMock]) -> None:
    """An empty lookup result says 'likely stale, re-check'."""
    report = _run(
        env,
        CIStatus.PASSED,
        "unstable",
        reread={"mergeable": True, "mergeable_state": "unstable", "head_sha": "abc"},
    )
    assert _STALE in report.recommendations
    assert report.non_green_checks == ()
    _no_ready(report)


@pytest.mark.parametrize(
    "reread, expected_sha",
    [
        ({"mergeable": True, "mergeable_state": "unknown", "head_sha": "abc"}, "abc"),
        ({"mergeable": True, "mergeable_state": None, "head_sha": "abc"}, "abc"),
        ({}, None),
    ],
)
def test_indefinite_reread_keeps_unstable(
    env: dict[str, MagicMock], reread: dict[str, Any], expected_sha: Optional[str]
) -> None:
    """unknown / None / missing state is not accepted."""
    report = _run(env, CIStatus.PASSED, "unstable", reread=reread)
    assert report.pr_mergeable_state == "unstable"
    env["pr_mgr"].get_non_green_checks.assert_called_once_with(45, expected_sha)
    _no_ready(report)


@pytest.mark.parametrize(
    "error",
    [
        GithubException(403, {"message": "Forbidden"}, None),
        RateLimitExceededException(
            403, {"message": "API rate limit exceeded"}, {"x-ratelimit-remaining": "0"}
        ),
        RuntimeError("boom"),
    ],
)
def test_reread_error_keeps_unstable(
    env: dict[str, MagicMock], error: BaseException
) -> None:
    """A failing re-read never breaks the report."""
    report = _run(env, CIStatus.PASSED, "unstable", reread=error)
    assert report.pr_mergeable_state == "unstable"
    env["pr_mgr"].get_non_green_checks.assert_called_once_with(45, None)
    assert report.branch_name == "338-x"
    assert report.pr_number == 45
    _no_ready(report)


@pytest.mark.parametrize(
    "reason",
    [
        PERMISSION_ERROR_TEXT,
        "GitHub API rate limit exceeded; resets at 12:00 UTC",
        "GitHub API error: 500 Internal Server Error",
    ],
)
def test_lookup_error_is_reported(env: dict[str, MagicMock], reason: str) -> None:
    """A failed lookup reaches the recommendation and the line."""
    report = _run(
        env,
        CIStatus.PASSED,
        "unstable",
        reread={"mergeable": True, "mergeable_state": "unstable", "head_sha": "abc"},
        checks=((), reason),
    )
    assert (
        "CI passed but GitHub reports mergeable_state=unstable"
        f" — could not list checks: {reason}"
    ) in report.recommendations
    line = f"Non-green checks: lookup failed — {reason}"
    assert line in report.format_for_human()
    assert line in report.format_for_llm()
    assert report.branch_name == "338-x"
    assert report.pr_number == 45
    _no_ready(report)


@pytest.mark.parametrize(
    "ci_status, state",
    [
        (CIStatus.PASSED, "clean"),
        (CIStatus.NOT_CONFIGURED, "clean"),
        (CIStatus.FAILED, "unstable"),
        (CIStatus.PASSED, "blocked"),
    ],
)
def test_no_extra_requests(
    env: dict[str, MagicMock], ci_status: CIStatus, state: str
) -> None:
    """Outside CI-ok + unstable, nothing is re-read or looked up."""
    report = _run(env, ci_status, state, reread={"mergeable_state": "clean"})
    env["pr_mgr"].get_pull_request.assert_not_called()
    env["pr_mgr"].get_non_green_checks.assert_not_called()
    env["sleep"].assert_not_called()
    assert report.non_green_checks is None
    assert report.non_green_checks_error is None
    if ci_status == CIStatus.FAILED:
        assert (
            "Not ready to merge (GitHub mergeable_state: unstable)"
            in report.recommendations
        )
