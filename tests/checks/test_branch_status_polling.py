"""Unit tests for async polling primitives in branch_status.

Tests `_wait_for_ci` and `_wait_for_pr` private helpers. `asyncio.sleep`
is patched with `AsyncMock` so tests run instantly.
"""

from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_workspace.checks.branch_status import (
    BranchStatusReport,
    CIStatus,
    WaitContext,
    _wait_for_ci,
    _wait_for_pr,
)
from mcp_workspace.workflows.task_tracker import TaskTrackerStatus


@pytest.fixture
def project_dir() -> Path:
    """Dummy project directory path."""
    return Path("/tmp/fake-project")


class TestWaitForCI:
    """Tests for `_wait_for_ci`."""

    @pytest.mark.asyncio
    async def test_returns_immediately_on_success(self, project_dir: Path) -> None:
        ci_manager = MagicMock()
        ci_manager.get_latest_ci_status.return_value = {
            "run": {"conclusion": "success"}
        }
        with (
            patch(
                "mcp_workspace.checks.branch_status.CIResultsManager",
                return_value=ci_manager,
            ),
            patch(
                "mcp_workspace.checks.branch_status.asyncio.sleep",
                new_callable=AsyncMock,
            ) as mock_sleep,
        ):
            elapsed = await _wait_for_ci(project_dir, "feature/x", timeout=60)
        assert ci_manager.get_latest_ci_status.call_count == 1
        mock_sleep.assert_not_called()
        assert isinstance(elapsed, float)
        assert elapsed >= 0.0

    @pytest.mark.asyncio
    async def test_returns_immediately_on_failure(self, project_dir: Path) -> None:
        ci_manager = MagicMock()
        ci_manager.get_latest_ci_status.return_value = {
            "run": {"conclusion": "failure"}
        }
        with (
            patch(
                "mcp_workspace.checks.branch_status.CIResultsManager",
                return_value=ci_manager,
            ),
            patch(
                "mcp_workspace.checks.branch_status.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            elapsed = await _wait_for_ci(project_dir, "feature/x", timeout=60)
        assert ci_manager.get_latest_ci_status.call_count == 1
        assert isinstance(elapsed, float)
        assert elapsed >= 0.0

    @pytest.mark.asyncio
    async def test_returns_after_timeout_when_in_progress(
        self, project_dir: Path
    ) -> None:
        ci_manager = MagicMock()
        ci_manager.get_latest_ci_status.return_value = {
            "run": {"conclusion": None, "status": "in_progress"}
        }
        # New loop shape: 1 call for `start`, then per iteration 1 call
        # for the deadline check and 1 call for `remaining`, plus 1 final
        # call on the return path.
        times = iter([0.0, 0.0, 5.0, 10.0, 100.0, 100.0, 100.0])
        with (
            patch(
                "mcp_workspace.checks.branch_status.CIResultsManager",
                return_value=ci_manager,
            ),
            patch(
                "mcp_workspace.checks.branch_status.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch(
                "mcp_workspace.checks.branch_status.time.monotonic",
                side_effect=lambda: next(times),
            ),
        ):
            elapsed = await _wait_for_ci(project_dir, "feature/x", timeout=60)
        assert ci_manager.get_latest_ci_status.call_count >= 1
        assert isinstance(elapsed, float)

    @pytest.mark.asyncio
    async def test_tolerates_two_errors_then_succeeds(self, project_dir: Path) -> None:
        ci_manager = MagicMock()
        ci_manager.get_latest_ci_status.side_effect = [
            RuntimeError("boom1"),
            RuntimeError("boom2"),
            {"run": {"conclusion": "success"}},
        ]
        with (
            patch(
                "mcp_workspace.checks.branch_status.CIResultsManager",
                return_value=ci_manager,
            ),
            patch(
                "mcp_workspace.checks.branch_status.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            await _wait_for_ci(project_dir, "feature/x", timeout=600)
        assert ci_manager.get_latest_ci_status.call_count == 3

    @pytest.mark.asyncio
    async def test_aborts_after_three_consecutive_errors(
        self, project_dir: Path
    ) -> None:
        ci_manager = MagicMock()
        ci_manager.get_latest_ci_status.side_effect = RuntimeError("boom")
        with (
            patch(
                "mcp_workspace.checks.branch_status.CIResultsManager",
                return_value=ci_manager,
            ),
            patch(
                "mcp_workspace.checks.branch_status.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            await _wait_for_ci(project_dir, "feature/x", timeout=600)
        assert ci_manager.get_latest_ci_status.call_count == 3

    @pytest.mark.asyncio
    async def test_timeout_zero_returns_immediately(self, project_dir: Path) -> None:
        ci_manager = MagicMock()
        with (
            patch(
                "mcp_workspace.checks.branch_status.CIResultsManager",
                return_value=ci_manager,
            ),
            patch(
                "mcp_workspace.checks.branch_status.asyncio.sleep",
                new_callable=AsyncMock,
            ) as mock_sleep,
        ):
            elapsed = await _wait_for_ci(project_dir, "feature/x", timeout=0)
        assert ci_manager.get_latest_ci_status.call_count == 0
        mock_sleep.assert_not_called()
        assert isinstance(elapsed, float)
        assert elapsed == pytest.approx(0.0, abs=0.5)

    @pytest.mark.asyncio
    async def test_ci_deadline_aware_sleep_caps_at_remaining_time(
        self, project_dir: Path
    ) -> None:
        ci_manager = MagicMock()
        ci_manager.get_latest_ci_status.return_value = {
            "run": {"conclusion": None, "status": "in_progress"}
        }
        # ci_timeout=5 < _CI_POLL_INTERVAL (15); sleep must cap at remaining.
        # Use a generator that advances by 1.0 per call so the loop will
        # eventually exit (asyncio internals may also call time.monotonic).
        counter = {"n": 0}

        def fake_monotonic() -> float:
            counter["n"] += 1
            return float(counter["n"])

        with (
            patch(
                "mcp_workspace.checks.branch_status.CIResultsManager",
                return_value=ci_manager,
            ),
            patch(
                "mcp_workspace.checks.branch_status.asyncio.sleep",
                new_callable=AsyncMock,
            ) as mock_sleep,
            patch(
                "mcp_workspace.checks.branch_status.time.monotonic",
                side_effect=fake_monotonic,
            ),
        ):
            await _wait_for_ci(project_dir, "feature/x", timeout=5)
        assert mock_sleep.call_count >= 1
        for call in mock_sleep.call_args_list:
            assert call.args[0] <= 5.0


class TestWaitForPR:
    """Tests for `_wait_for_pr`."""

    @pytest.mark.asyncio
    async def test_returns_immediately_when_pr_found(self, project_dir: Path) -> None:
        pr_manager = MagicMock()
        pr_manager.find_pull_request_by_head.return_value = [{"number": 42}]
        with (
            patch(
                "mcp_workspace.checks.branch_status.PullRequestManager",
                return_value=pr_manager,
            ),
            patch(
                "mcp_workspace.checks.branch_status.asyncio.sleep",
                new_callable=AsyncMock,
            ) as mock_sleep,
        ):
            elapsed = await _wait_for_pr(project_dir, "feature/x", timeout=60)
        assert pr_manager.find_pull_request_by_head.call_count == 1
        mock_sleep.assert_not_called()
        assert isinstance(elapsed, float)
        assert elapsed >= 0.0

    @pytest.mark.asyncio
    async def test_returns_after_timeout_when_no_pr(self, project_dir: Path) -> None:
        pr_manager = MagicMock()
        pr_manager.find_pull_request_by_head.return_value = []
        times = iter([0.0, 0.0, 5.0, 10.0, 100.0, 100.0, 100.0])
        with (
            patch(
                "mcp_workspace.checks.branch_status.PullRequestManager",
                return_value=pr_manager,
            ),
            patch(
                "mcp_workspace.checks.branch_status.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch(
                "mcp_workspace.checks.branch_status.time.monotonic",
                side_effect=lambda: next(times),
            ),
        ):
            elapsed = await _wait_for_pr(project_dir, "feature/x", timeout=60)
        assert pr_manager.find_pull_request_by_head.call_count >= 1
        assert isinstance(elapsed, float)

    @pytest.mark.asyncio
    async def test_aborts_after_three_consecutive_errors(
        self, project_dir: Path
    ) -> None:
        pr_manager = MagicMock()
        pr_manager.find_pull_request_by_head.side_effect = RuntimeError("boom")
        with (
            patch(
                "mcp_workspace.checks.branch_status.PullRequestManager",
                return_value=pr_manager,
            ),
            patch(
                "mcp_workspace.checks.branch_status.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            await _wait_for_pr(project_dir, "feature/x", timeout=600)
        assert pr_manager.find_pull_request_by_head.call_count == 3

    @pytest.mark.asyncio
    async def test_timeout_zero_returns_immediately(self, project_dir: Path) -> None:
        pr_manager = MagicMock()
        with (
            patch(
                "mcp_workspace.checks.branch_status.PullRequestManager",
                return_value=pr_manager,
            ),
            patch(
                "mcp_workspace.checks.branch_status.asyncio.sleep",
                new_callable=AsyncMock,
            ) as mock_sleep,
        ):
            elapsed = await _wait_for_pr(project_dir, "feature/x", timeout=0)
        assert pr_manager.find_pull_request_by_head.call_count == 0
        mock_sleep.assert_not_called()
        assert isinstance(elapsed, float)
        assert elapsed == pytest.approx(0.0, abs=0.5)

    @pytest.mark.asyncio
    async def test_pr_deadline_aware_sleep_caps_at_remaining_time(
        self, project_dir: Path
    ) -> None:
        pr_manager = MagicMock()
        pr_manager.find_pull_request_by_head.return_value = []
        # pr_timeout=5 < _PR_POLL_INTERVAL (20); sleep must cap at remaining.
        counter = {"n": 0}

        def fake_monotonic() -> float:
            counter["n"] += 1
            return float(counter["n"])

        with (
            patch(
                "mcp_workspace.checks.branch_status.PullRequestManager",
                return_value=pr_manager,
            ),
            patch(
                "mcp_workspace.checks.branch_status.asyncio.sleep",
                new_callable=AsyncMock,
            ) as mock_sleep,
            patch(
                "mcp_workspace.checks.branch_status.time.monotonic",
                side_effect=fake_monotonic,
            ),
        ):
            await _wait_for_pr(project_dir, "feature/x", timeout=5)
        assert mock_sleep.call_count >= 1
        for call in mock_sleep.call_args_list:
            assert call.args[0] <= 5.0


class TestAsyncPollBranchStatus:
    """Tests for `async_poll_branch_status` orchestrator."""

    @staticmethod
    def _make_report() -> BranchStatusReport:
        from mcp_workspace.checks.branch_status import CIStatus
        from mcp_workspace.workflows.task_tracker import TaskTrackerStatus

        return BranchStatusReport(
            branch_name="feature/x",
            base_branch="main",
            ci_status=CIStatus.PASSED,
            ci_details=None,
            rebase_needed=False,
            rebase_reason="up to date",
            tasks_status=TaskTrackerStatus.COMPLETE,
            tasks_reason="all done",
            tasks_is_blocking=False,
            current_github_label="status-ready",
            recommendations=["Ready to merge"],
        )

    @pytest.mark.asyncio
    async def test_defaults_call_no_helpers_and_skip_remote_check(
        self, project_dir: Path
    ) -> None:
        from mcp_workspace.checks.branch_status import async_poll_branch_status

        report = self._make_report()
        with (
            patch(
                "mcp_workspace.checks.branch_status.get_current_branch_name",
                return_value="feature/x",
            ),
            patch(
                "mcp_workspace.checks.branch_status.remote_branch_exists",
            ) as mock_remote,
            patch(
                "mcp_workspace.checks.branch_status.collect_branch_status",
                return_value=report,
            ) as mock_collect,
            patch(
                "mcp_workspace.checks.branch_status._wait_for_ci",
                new_callable=AsyncMock,
            ) as mock_wait_ci,
            patch(
                "mcp_workspace.checks.branch_status._wait_for_pr",
                new_callable=AsyncMock,
            ) as mock_wait_pr,
        ):
            result = await async_poll_branch_status(project_dir)

        mock_wait_ci.assert_not_called()
        mock_wait_pr.assert_not_called()
        mock_remote.assert_not_called()
        assert mock_collect.call_count == 1
        assert result == report.format_for_llm()

    @pytest.mark.asyncio
    async def test_ci_timeout_with_remote_branch_present(
        self, project_dir: Path
    ) -> None:
        from mcp_workspace.checks.branch_status import async_poll_branch_status

        report = self._make_report()
        with (
            patch(
                "mcp_workspace.checks.branch_status.get_current_branch_name",
                return_value="feature/x",
            ),
            patch(
                "mcp_workspace.checks.branch_status.remote_branch_exists",
                return_value=True,
            ),
            patch(
                "mcp_workspace.checks.branch_status.collect_branch_status",
                return_value=report,
            ),
            patch(
                "mcp_workspace.checks.branch_status._wait_for_ci",
                new_callable=AsyncMock,
            ) as mock_wait_ci,
            patch(
                "mcp_workspace.checks.branch_status._wait_for_pr",
                new_callable=AsyncMock,
            ) as mock_wait_pr,
        ):
            await async_poll_branch_status(project_dir, ci_timeout=30)

        mock_wait_ci.assert_awaited_once_with(project_dir, "feature/x", 30)
        mock_wait_pr.assert_awaited_once_with(project_dir, "feature/x", 0)

    @pytest.mark.asyncio
    async def test_pr_timeout_propagates_to_helper(
        self, project_dir: Path
    ) -> None:
        from mcp_workspace.checks.branch_status import async_poll_branch_status

        report = self._make_report()
        with (
            patch(
                "mcp_workspace.checks.branch_status.get_current_branch_name",
                return_value="feature/x",
            ),
            patch(
                "mcp_workspace.checks.branch_status.remote_branch_exists",
                return_value=True,
            ),
            patch(
                "mcp_workspace.checks.branch_status.collect_branch_status",
                return_value=report,
            ),
            patch(
                "mcp_workspace.checks.branch_status._wait_for_ci",
                new_callable=AsyncMock,
            ),
            patch(
                "mcp_workspace.checks.branch_status._wait_for_pr",
                new_callable=AsyncMock,
            ) as mock_wait_pr,
        ):
            await async_poll_branch_status(project_dir, pr_timeout=120)

        mock_wait_pr.assert_awaited_once_with(project_dir, "feature/x", 120)

    @pytest.mark.asyncio
    async def test_wait_for_pr_skipped_when_no_remote_branch(
        self, project_dir: Path
    ) -> None:
        from mcp_workspace.checks.branch_status import async_poll_branch_status

        report = self._make_report()
        with (
            patch(
                "mcp_workspace.checks.branch_status.get_current_branch_name",
                return_value="feature/x",
            ),
            patch(
                "mcp_workspace.checks.branch_status.remote_branch_exists",
                return_value=False,
            ),
            patch(
                "mcp_workspace.checks.branch_status.collect_branch_status",
                return_value=report,
            ),
            patch(
                "mcp_workspace.checks.branch_status._wait_for_ci",
                new_callable=AsyncMock,
            ) as mock_wait_ci,
            patch(
                "mcp_workspace.checks.branch_status._wait_for_pr",
                new_callable=AsyncMock,
            ) as mock_wait_pr,
        ):
            result = await async_poll_branch_status(project_dir, pr_timeout=120)

        mock_wait_pr.assert_not_called()
        mock_wait_ci.assert_not_called()
        assert "Push branch to remote before waiting for PR or CI" in result

    @pytest.mark.asyncio
    async def test_ci_timeout_skipped_when_no_remote_branch(
        self, project_dir: Path
    ) -> None:
        from mcp_workspace.checks.branch_status import async_poll_branch_status

        report = self._make_report()
        with (
            patch(
                "mcp_workspace.checks.branch_status.get_current_branch_name",
                return_value="feature/x",
            ),
            patch(
                "mcp_workspace.checks.branch_status.remote_branch_exists",
                return_value=False,
            ),
            patch(
                "mcp_workspace.checks.branch_status.collect_branch_status",
                return_value=report,
            ),
            patch(
                "mcp_workspace.checks.branch_status._wait_for_ci",
                new_callable=AsyncMock,
            ) as mock_wait_ci,
            patch(
                "mcp_workspace.checks.branch_status._wait_for_pr",
                new_callable=AsyncMock,
            ) as mock_wait_pr,
        ):
            result = await async_poll_branch_status(project_dir, ci_timeout=30)

        mock_wait_ci.assert_not_called()
        mock_wait_pr.assert_not_called()
        assert "Push branch to remote before waiting for PR or CI" in result

    @pytest.mark.asyncio
    async def test_both_flags_no_remote_branch_emits_recommendation_once(
        self, project_dir: Path
    ) -> None:
        from mcp_workspace.checks.branch_status import async_poll_branch_status

        report = self._make_report()
        with (
            patch(
                "mcp_workspace.checks.branch_status.get_current_branch_name",
                return_value="feature/x",
            ),
            patch(
                "mcp_workspace.checks.branch_status.remote_branch_exists",
                return_value=False,
            ),
            patch(
                "mcp_workspace.checks.branch_status.collect_branch_status",
                return_value=report,
            ),
            patch(
                "mcp_workspace.checks.branch_status._wait_for_ci",
                new_callable=AsyncMock,
            ) as mock_wait_ci,
            patch(
                "mcp_workspace.checks.branch_status._wait_for_pr",
                new_callable=AsyncMock,
            ) as mock_wait_pr,
        ):
            result = await async_poll_branch_status(
                project_dir, ci_timeout=30, pr_timeout=120
            )

        mock_wait_ci.assert_not_called()
        mock_wait_pr.assert_not_called()
        msg = "Push branch to remote before waiting for PR or CI"
        assert result.count(msg) == 1

    @pytest.mark.asyncio
    async def test_polls_run_in_parallel(self, project_dir: Path) -> None:
        import asyncio

        from mcp_workspace.checks.branch_status import async_poll_branch_status

        report = self._make_report()
        release = asyncio.Event()
        ci_started = asyncio.Event()
        pr_started = asyncio.Event()

        async def fake_wait_ci(*_a: object, **_kw: object) -> float:
            ci_started.set()
            await release.wait()
            return 0.0

        async def fake_wait_pr(*_a: object, **_kw: object) -> float:
            pr_started.set()
            await release.wait()
            return 0.0

        with (
            patch(
                "mcp_workspace.checks.branch_status.get_current_branch_name",
                return_value="feature/x",
            ),
            patch(
                "mcp_workspace.checks.branch_status.remote_branch_exists",
                return_value=True,
            ),
            patch(
                "mcp_workspace.checks.branch_status.collect_branch_status",
                return_value=report,
            ),
            patch(
                "mcp_workspace.checks.branch_status._wait_for_ci",
                side_effect=fake_wait_ci,
            ),
            patch(
                "mcp_workspace.checks.branch_status._wait_for_pr",
                side_effect=fake_wait_pr,
            ),
        ):
            task = asyncio.create_task(
                async_poll_branch_status(project_dir, ci_timeout=30, pr_timeout=30)
            )
            await asyncio.wait_for(ci_started.wait(), timeout=1)
            await asyncio.wait_for(pr_started.wait(), timeout=1)
            release.set()
            await task

    @pytest.mark.asyncio
    async def test_wait_context_built_from_elapsed_values(
        self, project_dir: Path
    ) -> None:
        from mcp_workspace.checks.branch_status import async_poll_branch_status

        mock_report = MagicMock(spec=BranchStatusReport)
        mock_report.format_for_llm.return_value = "captured"

        with (
            patch(
                "mcp_workspace.checks.branch_status.get_current_branch_name",
                return_value="feature/x",
            ),
            patch(
                "mcp_workspace.checks.branch_status.remote_branch_exists",
                return_value=True,
            ),
            patch(
                "mcp_workspace.checks.branch_status.collect_branch_status",
                return_value=mock_report,
            ),
            patch(
                "mcp_workspace.checks.branch_status._wait_for_ci",
                new_callable=AsyncMock,
                return_value=12.3,
            ),
            patch(
                "mcp_workspace.checks.branch_status._wait_for_pr",
                new_callable=AsyncMock,
                return_value=7.7,
            ),
        ):
            await async_poll_branch_status(
                project_dir, ci_timeout=30, pr_timeout=30
            )

        mock_report.format_for_llm.assert_called_once()
        wait_ctx = mock_report.format_for_llm.call_args.kwargs["wait_context"]
        assert isinstance(wait_ctx, WaitContext)
        assert wait_ctx.ci_elapsed == 12.3
        assert wait_ctx.pr_elapsed == 7.7
        assert wait_ctx.ci_timeout == 30
        assert wait_ctx.pr_timeout == 30

    @pytest.mark.asyncio
    async def test_wait_context_pr_side_none_when_pr_timeout_zero(
        self, project_dir: Path
    ) -> None:
        from mcp_workspace.checks.branch_status import async_poll_branch_status

        mock_report = MagicMock(spec=BranchStatusReport)
        mock_report.format_for_llm.return_value = "captured"

        with (
            patch(
                "mcp_workspace.checks.branch_status.get_current_branch_name",
                return_value="feature/x",
            ),
            patch(
                "mcp_workspace.checks.branch_status.remote_branch_exists",
                return_value=True,
            ),
            patch(
                "mcp_workspace.checks.branch_status.collect_branch_status",
                return_value=mock_report,
            ),
            patch(
                "mcp_workspace.checks.branch_status._wait_for_ci",
                new_callable=AsyncMock,
                return_value=12.3,
            ),
            patch(
                "mcp_workspace.checks.branch_status._wait_for_pr",
                new_callable=AsyncMock,
                return_value=0.0,
            ),
        ):
            await async_poll_branch_status(
                project_dir, ci_timeout=30, pr_timeout=0
            )

        wait_ctx = mock_report.format_for_llm.call_args.kwargs["wait_context"]
        assert isinstance(wait_ctx, WaitContext)
        assert wait_ctx.pr_elapsed is None
        assert wait_ctx.ci_elapsed == 12.3

    @pytest.mark.asyncio
    async def test_no_branch_skips_helpers_and_remote_check(
        self, project_dir: Path
    ) -> None:
        from mcp_workspace.checks.branch_status import async_poll_branch_status

        report = self._make_report()
        with (
            patch(
                "mcp_workspace.checks.branch_status.get_current_branch_name",
                return_value=None,
            ),
            patch(
                "mcp_workspace.checks.branch_status.remote_branch_exists",
            ) as mock_remote,
            patch(
                "mcp_workspace.checks.branch_status.collect_branch_status",
                return_value=report,
            ) as mock_collect,
            patch(
                "mcp_workspace.checks.branch_status._wait_for_ci",
                new_callable=AsyncMock,
            ) as mock_wait_ci,
            patch(
                "mcp_workspace.checks.branch_status._wait_for_pr",
                new_callable=AsyncMock,
            ) as mock_wait_pr,
        ):
            result = await async_poll_branch_status(
                project_dir, ci_timeout=30, pr_timeout=120
            )

        mock_remote.assert_not_called()
        mock_wait_ci.assert_not_called()
        mock_wait_pr.assert_not_called()
        assert mock_collect.call_count == 1
        assert result == report.format_for_llm()


class TestWaitLineRendering:
    """Tests for ``WaitContext`` rendering on both formatters."""

    @staticmethod
    def _make_report(
        *,
        ci_status: CIStatus = CIStatus.PASSED,
        pr_found: Optional[bool] = None,
    ) -> BranchStatusReport:
        return BranchStatusReport(
            branch_name="feature/x",
            base_branch="main",
            ci_status=ci_status,
            ci_details=None,
            rebase_needed=False,
            rebase_reason="up to date",
            tasks_status=TaskTrackerStatus.COMPLETE,
            tasks_reason="all done",
            tasks_is_blocking=False,
            current_github_label="status-ready",
            recommendations=["Ready to merge"],
            pr_found=pr_found,
        )

    def test_wait_line_both_sides_ci_ok_pr_missing(self) -> None:
        report = self._make_report(ci_status=CIStatus.PASSED, pr_found=False)
        ctx = WaitContext(
            ci_elapsed=80.0,
            ci_timeout=300,
            pr_elapsed=300.0,
            pr_timeout=300,
        )
        rendered = report.format_for_llm(wait_context=ctx)
        assert "Wait: ci=80s ok, pr=300s missing" in rendered

    def test_wait_line_ci_fail_pr_ok(self) -> None:
        report = self._make_report(ci_status=CIStatus.FAILED, pr_found=True)
        ctx = WaitContext(
            ci_elapsed=42.0,
            ci_timeout=300,
            pr_elapsed=10.0,
            pr_timeout=300,
        )
        rendered = report.format_for_llm(wait_context=ctx)
        assert "Wait: ci=42s fail, pr=10s ok" in rendered

    def test_wait_line_ci_pending_when_status_not_configured(self) -> None:
        report = self._make_report(ci_status=CIStatus.NOT_CONFIGURED)
        ctx = WaitContext(ci_elapsed=15.0, ci_timeout=60)
        rendered = report.format_for_llm(wait_context=ctx)
        assert "ci=15s pending" in rendered

    def test_wait_line_omits_ci_side_when_ci_timeout_zero(self) -> None:
        report = self._make_report(pr_found=True)
        ctx = WaitContext(
            ci_elapsed=None,
            ci_timeout=0,
            pr_elapsed=10.0,
            pr_timeout=120,
        )
        rendered = report.format_for_llm(wait_context=ctx)
        assert "Wait: pr=10s ok" in rendered
        assert "ci=" not in rendered

    def test_wait_line_omits_pr_side_when_pr_timeout_zero(self) -> None:
        report = self._make_report(ci_status=CIStatus.PASSED)
        ctx = WaitContext(
            ci_elapsed=20.0,
            ci_timeout=120,
            pr_elapsed=None,
            pr_timeout=0,
        )
        rendered = report.format_for_llm(wait_context=ctx)
        assert "Wait: ci=20s ok" in rendered
        assert "pr=" not in rendered

    def test_wait_line_absent_when_both_timeouts_zero(self) -> None:
        report = self._make_report()
        ctx = WaitContext()
        rendered = report.format_for_llm(wait_context=ctx)
        assert "Wait:" not in rendered

    def test_wait_line_absent_when_no_wait_context(self) -> None:
        report = self._make_report()
        with_default = report.format_for_llm()
        with_none = report.format_for_llm(wait_context=None)
        assert "Wait:" not in with_default
        assert with_default == with_none

    def test_format_for_human_unchanged_when_no_wait_context(self) -> None:
        report = self._make_report()
        with_default = report.format_for_human()
        with_none = report.format_for_human(wait_context=None)
        assert "Wait:" not in with_default
        assert with_default == with_none

    def test_format_for_human_renders_same_wait_line(self) -> None:
        report = self._make_report(ci_status=CIStatus.PASSED)
        ctx = WaitContext(ci_elapsed=10.0, ci_timeout=60)
        rendered = report.format_for_human(wait_context=ctx)
        assert "Wait: ci=10s ok" in rendered

        lines = rendered.split("\n")
        base_idx = next(
            i for i, ln in enumerate(lines) if ln.startswith("Base Branch:")
        )
        wait_idx = next(i for i, ln in enumerate(lines) if ln.startswith("Wait:"))
        report_idx = next(
            i for i, ln in enumerate(lines) if ln == "Branch Status Report"
        )
        assert wait_idx == base_idx + 1
        assert lines[wait_idx + 1] == ""
        assert report_idx == wait_idx + 2
