"""Unit tests for the `async_poll_branch_status` orchestrator.

Covers helper dispatch, remote-branch gating, wait-context assembly, and
the ``fail_on_reviews`` pass-through. `asyncio.sleep` is patched with
`AsyncMock` so tests run instantly.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_workspace.checks.branch_status import BranchStatusReport
from mcp_workspace.checks.branch_status_rendering import WaitContext


@pytest.fixture
def project_dir() -> Path:
    """Dummy project directory path."""
    return Path("/tmp/fake-project")


class TestAsyncPollBranchStatus:
    """Tests for `async_poll_branch_status` orchestrator."""

    @staticmethod
    def _make_report() -> BranchStatusReport:
        from mcp_workspace.checks.branch_status_rendering import CIStatus
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
        from mcp_workspace.checks.branch_status_polling import async_poll_branch_status

        report = self._make_report()
        with (
            patch(
                "mcp_workspace.checks.branch_status_polling.get_current_branch_name",
                return_value="feature/x",
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.remote_branch_exists",
            ) as mock_remote,
            patch(
                "mcp_workspace.checks.branch_status_polling.collect_branch_status",
                return_value=report,
            ) as mock_collect,
            patch(
                "mcp_workspace.checks.branch_status_polling._wait_for_ci",
                new_callable=AsyncMock,
            ) as mock_wait_ci,
            patch(
                "mcp_workspace.checks.branch_status_polling._wait_for_pr",
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
        from mcp_workspace.checks.branch_status_polling import async_poll_branch_status

        report = self._make_report()
        with (
            patch(
                "mcp_workspace.checks.branch_status_polling.get_current_branch_name",
                return_value="feature/x",
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.remote_branch_exists",
                return_value=True,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.collect_branch_status",
                return_value=report,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling._wait_for_ci",
                new_callable=AsyncMock,
            ) as mock_wait_ci,
            patch(
                "mcp_workspace.checks.branch_status_polling._wait_for_pr",
                new_callable=AsyncMock,
            ) as mock_wait_pr,
        ):
            await async_poll_branch_status(project_dir, ci_timeout=30)

        mock_wait_ci.assert_awaited_once_with(project_dir, "feature/x", 30)
        mock_wait_pr.assert_awaited_once_with(project_dir, "feature/x", 0)

    @pytest.mark.asyncio
    async def test_pr_timeout_propagates_to_helper(self, project_dir: Path) -> None:
        from mcp_workspace.checks.branch_status_polling import async_poll_branch_status

        report = self._make_report()
        with (
            patch(
                "mcp_workspace.checks.branch_status_polling.get_current_branch_name",
                return_value="feature/x",
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.remote_branch_exists",
                return_value=True,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.collect_branch_status",
                return_value=report,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling._wait_for_ci",
                new_callable=AsyncMock,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling._wait_for_pr",
                new_callable=AsyncMock,
            ) as mock_wait_pr,
        ):
            await async_poll_branch_status(project_dir, pr_timeout=120)

        mock_wait_pr.assert_awaited_once_with(project_dir, "feature/x", 120)

    @pytest.mark.asyncio
    async def test_wait_for_pr_skipped_when_no_remote_branch(
        self, project_dir: Path
    ) -> None:
        from mcp_workspace.checks.branch_status_polling import async_poll_branch_status

        report = self._make_report()
        with (
            patch(
                "mcp_workspace.checks.branch_status_polling.get_current_branch_name",
                return_value="feature/x",
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.remote_branch_exists",
                return_value=False,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.collect_branch_status",
                return_value=report,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling._wait_for_ci",
                new_callable=AsyncMock,
            ) as mock_wait_ci,
            patch(
                "mcp_workspace.checks.branch_status_polling._wait_for_pr",
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
        from mcp_workspace.checks.branch_status_polling import async_poll_branch_status

        report = self._make_report()
        with (
            patch(
                "mcp_workspace.checks.branch_status_polling.get_current_branch_name",
                return_value="feature/x",
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.remote_branch_exists",
                return_value=False,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.collect_branch_status",
                return_value=report,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling._wait_for_ci",
                new_callable=AsyncMock,
            ) as mock_wait_ci,
            patch(
                "mcp_workspace.checks.branch_status_polling._wait_for_pr",
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
        from mcp_workspace.checks.branch_status_polling import async_poll_branch_status

        report = self._make_report()
        with (
            patch(
                "mcp_workspace.checks.branch_status_polling.get_current_branch_name",
                return_value="feature/x",
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.remote_branch_exists",
                return_value=False,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.collect_branch_status",
                return_value=report,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling._wait_for_ci",
                new_callable=AsyncMock,
            ) as mock_wait_ci,
            patch(
                "mcp_workspace.checks.branch_status_polling._wait_for_pr",
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

        from mcp_workspace.checks.branch_status_polling import async_poll_branch_status

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
                "mcp_workspace.checks.branch_status_polling.get_current_branch_name",
                return_value="feature/x",
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.remote_branch_exists",
                return_value=True,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.collect_branch_status",
                return_value=report,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling._wait_for_ci",
                side_effect=fake_wait_ci,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling._wait_for_pr",
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
        from mcp_workspace.checks.branch_status_polling import async_poll_branch_status

        mock_report = MagicMock(spec=BranchStatusReport)
        mock_report.format_for_llm.return_value = "captured"

        with (
            patch(
                "mcp_workspace.checks.branch_status_polling.get_current_branch_name",
                return_value="feature/x",
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.remote_branch_exists",
                return_value=True,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.collect_branch_status",
                return_value=mock_report,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling._wait_for_ci",
                new_callable=AsyncMock,
                return_value=12.3,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling._wait_for_pr",
                new_callable=AsyncMock,
                return_value=7.7,
            ),
        ):
            await async_poll_branch_status(project_dir, ci_timeout=30, pr_timeout=30)

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
        from mcp_workspace.checks.branch_status_polling import async_poll_branch_status

        mock_report = MagicMock(spec=BranchStatusReport)
        mock_report.format_for_llm.return_value = "captured"

        with (
            patch(
                "mcp_workspace.checks.branch_status_polling.get_current_branch_name",
                return_value="feature/x",
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.remote_branch_exists",
                return_value=True,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.collect_branch_status",
                return_value=mock_report,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling._wait_for_ci",
                new_callable=AsyncMock,
                return_value=12.3,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling._wait_for_pr",
                new_callable=AsyncMock,
                return_value=0.0,
            ),
        ):
            await async_poll_branch_status(project_dir, ci_timeout=30, pr_timeout=0)

        wait_ctx = mock_report.format_for_llm.call_args.kwargs["wait_context"]
        assert isinstance(wait_ctx, WaitContext)
        assert wait_ctx.pr_elapsed is None
        assert wait_ctx.ci_elapsed == 12.3

    @pytest.mark.asyncio
    async def test_async_poll_passes_fail_on_reviews_to_format(
        self, project_dir: Path
    ) -> None:
        from mcp_workspace.checks.branch_status_polling import async_poll_branch_status

        mock_report = MagicMock(spec=BranchStatusReport)
        mock_report.format_for_llm.return_value = "captured"

        with (
            patch(
                "mcp_workspace.checks.branch_status_polling.get_current_branch_name",
                return_value="feature/x",
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.remote_branch_exists",
                return_value=True,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.collect_branch_status",
                return_value=mock_report,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling._wait_for_ci",
                new_callable=AsyncMock,
                return_value=1.0,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling._wait_for_pr",
                new_callable=AsyncMock,
                return_value=1.0,
            ),
        ):
            await async_poll_branch_status(
                project_dir, ci_timeout=30, pr_timeout=30, fail_on_reviews=True
            )

        assert mock_report.format_for_llm.call_args.kwargs["fail_on_reviews"] is True

    @pytest.mark.asyncio
    async def test_async_poll_fail_on_reviews_defaults_false(
        self, project_dir: Path
    ) -> None:
        from mcp_workspace.checks.branch_status_polling import async_poll_branch_status

        mock_report = MagicMock(spec=BranchStatusReport)
        mock_report.format_for_llm.return_value = "captured"

        with (
            patch(
                "mcp_workspace.checks.branch_status_polling.get_current_branch_name",
                return_value="feature/x",
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.remote_branch_exists",
                return_value=True,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.collect_branch_status",
                return_value=mock_report,
            ),
        ):
            await async_poll_branch_status(project_dir)

        assert mock_report.format_for_llm.call_args.kwargs["fail_on_reviews"] is False

    @pytest.mark.asyncio
    async def test_no_branch_skips_helpers_and_remote_check(
        self, project_dir: Path
    ) -> None:
        from mcp_workspace.checks.branch_status_polling import async_poll_branch_status

        report = self._make_report()
        with (
            patch(
                "mcp_workspace.checks.branch_status_polling.get_current_branch_name",
                return_value=None,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.remote_branch_exists",
            ) as mock_remote,
            patch(
                "mcp_workspace.checks.branch_status_polling.collect_branch_status",
                return_value=report,
            ) as mock_collect,
            patch(
                "mcp_workspace.checks.branch_status_polling._wait_for_ci",
                new_callable=AsyncMock,
            ) as mock_wait_ci,
            patch(
                "mcp_workspace.checks.branch_status_polling._wait_for_pr",
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

    @pytest.mark.asyncio
    async def test_max_log_lines_reaches_the_render_cap(
        self, project_dir: Path
    ) -> None:
        """`max_log_lines` is forwarded to `format_for_llm`, not just to collection."""
        from mcp_workspace.checks.branch_status_polling import async_poll_branch_status

        mock_report = MagicMock(spec=BranchStatusReport)
        mock_report.format_for_llm.return_value = "captured"

        with (
            patch(
                "mcp_workspace.checks.branch_status_polling.get_current_branch_name",
                return_value="feature/x",
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.collect_branch_status",
                return_value=mock_report,
            ),
        ):
            await async_poll_branch_status(project_dir, max_log_lines=500)

        assert mock_report.format_for_llm.call_args.kwargs["max_lines"] == 500

    @pytest.mark.asyncio
    async def test_max_log_lines_reaches_the_render_cap_without_a_branch(
        self, project_dir: Path
    ) -> None:
        """The detached-HEAD early return forwards `max_log_lines` too."""
        from mcp_workspace.checks.branch_status_polling import async_poll_branch_status

        mock_report = MagicMock(spec=BranchStatusReport)
        mock_report.format_for_llm.return_value = "captured"

        with (
            patch(
                "mcp_workspace.checks.branch_status_polling.get_current_branch_name",
                return_value=None,
            ),
            patch(
                "mcp_workspace.checks.branch_status_polling.collect_branch_status",
                return_value=mock_report,
            ),
        ):
            result = await async_poll_branch_status(project_dir, max_log_lines=500)

        assert result == "captured"
        assert mock_report.format_for_llm.call_args.kwargs["max_lines"] == 500
