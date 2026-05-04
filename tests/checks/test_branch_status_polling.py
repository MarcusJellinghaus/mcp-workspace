"""Unit tests for async polling primitives in branch_status.

Tests `_wait_for_ci` and `_wait_for_pr` private helpers. `asyncio.sleep`
is patched with `AsyncMock` so tests run instantly.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_workspace.checks.branch_status import (
    BranchStatusReport,
    _wait_for_ci,
    _wait_for_pr,
)


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
        mock_wait_pr.assert_not_called()

    @pytest.mark.asyncio
    async def test_wait_for_pr_uses_default_pr_timeout(self, project_dir: Path) -> None:
        from mcp_workspace.checks.branch_status import (
            _DEFAULT_PR_TIMEOUT,
            async_poll_branch_status,
        )

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
            result = await async_poll_branch_status(project_dir, wait_for_pr=True)

        mock_wait_pr.assert_awaited_once_with(
            project_dir, "feature/x", _DEFAULT_PR_TIMEOUT
        )
        mock_wait_ci.assert_not_called()
        assert "Push branch to remote" not in result

    @pytest.mark.asyncio
    async def test_wait_for_pr_uses_explicit_pr_timeout(
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
            await async_poll_branch_status(
                project_dir, wait_for_pr=True, pr_timeout=120
            )

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
            result = await async_poll_branch_status(project_dir, wait_for_pr=True)

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
                project_dir, ci_timeout=30, wait_for_pr=True
            )

        mock_wait_ci.assert_not_called()
        mock_wait_pr.assert_not_called()
        msg = "Push branch to remote before waiting for PR or CI"
        assert result.count(msg) == 1

    @pytest.mark.asyncio
    async def test_pr_wait_runs_before_ci_wait_then_collect(
        self, project_dir: Path
    ) -> None:
        from mcp_workspace.checks.branch_status import async_poll_branch_status

        report = self._make_report()
        order: list[str] = []

        async def fake_wait_pr(*_args: object, **_kwargs: object) -> None:
            order.append("pr")

        async def fake_wait_ci(*_args: object, **_kwargs: object) -> None:
            order.append("ci")

        def fake_collect(*_args: object, **_kwargs: object) -> BranchStatusReport:
            order.append("collect")
            return report

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
                side_effect=fake_collect,
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
            await async_poll_branch_status(project_dir, ci_timeout=30, wait_for_pr=True)

        assert order == ["pr", "ci", "collect"]

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
                project_dir, ci_timeout=30, wait_for_pr=True
            )

        mock_remote.assert_not_called()
        mock_wait_ci.assert_not_called()
        mock_wait_pr.assert_not_called()
        assert mock_collect.call_count == 1
        assert result == report.format_for_llm()
