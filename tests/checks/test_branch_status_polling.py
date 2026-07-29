"""Unit tests for async polling primitives in branch_status_polling.

Tests `_wait_for_ci` and `_wait_for_pr`. The `async_poll_branch_status`
orchestrator is covered in test_branch_status_polling_orchestrator.
`asyncio.sleep` is patched with `AsyncMock` so tests run instantly.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_workspace.checks.branch_status_polling import _wait_for_ci, _wait_for_pr


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
                "mcp_workspace.checks.branch_status_polling.CIResultsManager",
                return_value=ci_manager,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.asyncio.sleep",
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
                "mcp_workspace.checks.branch_status_polling.CIResultsManager",
                return_value=ci_manager,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.asyncio.sleep",
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
                "mcp_workspace.checks.branch_status_polling.CIResultsManager",
                return_value=ci_manager,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.time.monotonic",
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
                "mcp_workspace.checks.branch_status_polling.CIResultsManager",
                return_value=ci_manager,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.asyncio.sleep",
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
                "mcp_workspace.checks.branch_status_polling.CIResultsManager",
                return_value=ci_manager,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.asyncio.sleep",
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
                "mcp_workspace.checks.branch_status_polling.CIResultsManager",
                return_value=ci_manager,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.asyncio.sleep",
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
                "mcp_workspace.checks.branch_status_polling.CIResultsManager",
                return_value=ci_manager,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.asyncio.sleep",
                new_callable=AsyncMock,
            ) as mock_sleep,
            patch(
                "mcp_workspace.checks.branch_status_polling.time.monotonic",
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
                "mcp_workspace.checks.branch_status_polling.PullRequestManager",
                return_value=pr_manager,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.asyncio.sleep",
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
                "mcp_workspace.checks.branch_status_polling.PullRequestManager",
                return_value=pr_manager,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.time.monotonic",
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
                "mcp_workspace.checks.branch_status_polling.PullRequestManager",
                return_value=pr_manager,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.asyncio.sleep",
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
                "mcp_workspace.checks.branch_status_polling.PullRequestManager",
                return_value=pr_manager,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.asyncio.sleep",
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
                "mcp_workspace.checks.branch_status_polling.PullRequestManager",
                return_value=pr_manager,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.asyncio.sleep",
                new_callable=AsyncMock,
            ) as mock_sleep,
            patch(
                "mcp_workspace.checks.branch_status_polling.time.monotonic",
                side_effect=fake_monotonic,
            ),
        ):
            await _wait_for_pr(project_dir, "feature/x", timeout=5)
        assert mock_sleep.call_count >= 1
        for call in mock_sleep.call_args_list:
            assert call.args[0] <= 5.0
