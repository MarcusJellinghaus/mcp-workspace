"""Tests for branch_status recommendation and PR merge override logic."""

from mcp_workspace.checks.branch_status import (
    _apply_pr_merge_override,
    _generate_recommendations,
)
from mcp_workspace.checks.branch_status_rendering import CIStatus
from mcp_workspace.workflows.task_tracker import TaskTrackerStatus


class TestGenerateRecommendations:
    """Tests for _generate_recommendations."""

    def test_all_good(self) -> None:
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.PASSED,
                "rebase_needed": False,
                "tasks_status": TaskTrackerStatus.COMPLETE,
                "tasks_reason": "All done",
                "tasks_is_blocking": False,
            }
        )
        assert "Ready to merge" in recs

    def test_all_good_na_tasks(self) -> None:
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.PASSED,
                "rebase_needed": False,
                "tasks_status": TaskTrackerStatus.N_A,
                "tasks_reason": "No tasks",
                "tasks_is_blocking": False,
            }
        )
        assert "Ready to merge" in recs

    def test_ci_failed(self) -> None:
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.FAILED,
                "rebase_needed": False,
                "tasks_status": TaskTrackerStatus.COMPLETE,
                "tasks_reason": "All done",
                "tasks_is_blocking": False,
            }
        )
        assert "Fix CI test failures" in recs

    def test_ci_failed_with_details(self) -> None:
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.FAILED,
                "ci_details": "Some error log",
                "rebase_needed": False,
                "tasks_status": TaskTrackerStatus.COMPLETE,
                "tasks_reason": "All done",
                "tasks_is_blocking": False,
            }
        )
        assert "Check CI error details above" in recs

    def test_not_configured(self) -> None:
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.NOT_CONFIGURED,
                "rebase_needed": False,
                "tasks_status": TaskTrackerStatus.COMPLETE,
                "tasks_reason": "All done",
                "tasks_is_blocking": False,
            }
        )
        assert "Configure CI pipeline" in recs

    def test_rebase_needed(self) -> None:
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.PASSED,
                "rebase_needed": True,
                "tasks_status": TaskTrackerStatus.COMPLETE,
                "tasks_reason": "All done",
                "tasks_is_blocking": False,
            }
        )
        assert "Rebase onto origin/main" in recs

    def test_rebase_needed_on_default_branch_says_pull(self) -> None:
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.PASSED,
                "rebase_needed": True,
                "tasks_status": TaskTrackerStatus.N_A,
                "tasks_reason": "No tasks",
                "tasks_is_blocking": False,
                "is_default_branch": True,
            }
        )
        assert "Pull origin/main" in recs
        assert "Rebase onto origin/main" not in recs

    def test_rebase_needed_but_tasks_blocking(self) -> None:
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.PASSED,
                "rebase_needed": True,
                "tasks_status": TaskTrackerStatus.INCOMPLETE,
                "tasks_reason": "2 of 5",
                "tasks_is_blocking": True,
            }
        )
        assert not any("Rebase" in r for r in recs)
        assert any("remaining tasks" in r.lower() for r in recs)

    def test_tasks_incomplete(self) -> None:
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.PASSED,
                "rebase_needed": False,
                "tasks_status": TaskTrackerStatus.INCOMPLETE,
                "tasks_reason": "3 of 5 tasks complete",
                "tasks_is_blocking": True,
            }
        )
        assert any("remaining tasks" in r.lower() for r in recs)

    def test_ready_to_merge_squash_merge_safe(self) -> None:
        """When pr_mergeable=True and ready, recommend squash-merge safe."""
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.PASSED,
                "rebase_needed": False,
                "tasks_status": TaskTrackerStatus.COMPLETE,
                "tasks_reason": "All done",
                "tasks_is_blocking": False,
                "pr_mergeable": True,
            }
        )
        assert "Ready to merge (squash-merge safe)" in recs

    def test_ready_to_merge_without_mergeable(self) -> None:
        """When pr_mergeable is not True, recommend plain Ready to merge."""
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.PASSED,
                "rebase_needed": False,
                "tasks_status": TaskTrackerStatus.COMPLETE,
                "tasks_reason": "All done",
                "tasks_is_blocking": False,
                "pr_mergeable": None,
            }
        )
        assert "Ready to merge" in recs
        assert "Ready to merge (squash-merge safe)" not in recs

    def test_rebase_suppressed_when_ci_failed(self) -> None:
        """Rebase recommendation is suppressed when CI is failed."""
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.FAILED,
                "rebase_needed": True,
                "tasks_status": TaskTrackerStatus.COMPLETE,
                "tasks_reason": "All done",
                "tasks_is_blocking": False,
            }
        )
        assert "Fix CI test failures" in recs
        assert not any("Rebase" in r for r in recs)

    def test_na_blocking_recommends_fix_tracker(self) -> None:
        """N_A + blocking recommends fixing tracker."""
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.PASSED,
                "rebase_needed": False,
                "tasks_status": TaskTrackerStatus.N_A,
                "tasks_reason": "Task tracker is empty",
                "tasks_is_blocking": True,
            }
        )
        assert any("Fix task tracker" in r for r in recs)
        assert "Task tracker is empty" in recs[0] or any(
            "Task tracker is empty" in r for r in recs
        )

    def test_multiple_issues(self) -> None:
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.FAILED,
                "rebase_needed": True,
                "tasks_status": TaskTrackerStatus.INCOMPLETE,
                "tasks_reason": "3 of 5",
                "tasks_is_blocking": False,
            }
        )
        # CI failed + incomplete tasks; rebase suppressed because CI failed
        assert "Fix CI test failures" in recs
        assert any("remaining tasks" in r.lower() for r in recs)

    def test_failing_job_names_replace_generic_ci_message(self) -> None:
        """ci_failing_job_names populated → specific message replaces generic."""
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.FAILED,
                "rebase_needed": False,
                "tasks_status": TaskTrackerStatus.COMPLETE,
                "tasks_reason": "All done",
                "tasks_is_blocking": False,
                "ci_failing_job_names": ["mssql-integration"],
            }
        )
        assert "Fix failing job(s): mssql-integration" in recs
        assert "Fix CI test failures" not in recs

    def test_no_failing_job_names_keeps_generic_message(self) -> None:
        """No / empty ci_failing_job_names → generic message preserved."""
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.FAILED,
                "rebase_needed": False,
                "tasks_status": TaskTrackerStatus.COMPLETE,
                "tasks_reason": "All done",
                "tasks_is_blocking": False,
                "ci_failing_job_names": [],
            }
        )
        assert "Fix CI test failures" in recs
        assert not any(r.startswith("Fix failing job(s):") for r in recs)


class TestApplyPrMergeOverride:
    """Tests for _apply_pr_merge_override."""

    def test_rebase_not_needed_passthrough(self) -> None:
        """When rebase is not needed, return unchanged (no override needed)."""
        result = _apply_pr_merge_override(
            rebase_needed=False,
            rebase_reason="up-to-date",
            pr_mergeable=True,
        )
        assert result == (False, "up-to-date")

    def test_rebase_needed_and_mergeable_overrides(self) -> None:
        """When rebase needed but PR is mergeable, override to not needed."""
        result = _apply_pr_merge_override(
            rebase_needed=True,
            rebase_reason="3 commits behind",
            pr_mergeable=True,
        )
        assert result == (
            False,
            "Behind base branch but PR is mergeable (squash-merge safe)",
        )

    def test_rebase_needed_and_not_mergeable_unchanged(self) -> None:
        """When rebase needed and PR is not mergeable, keep original."""
        result = _apply_pr_merge_override(
            rebase_needed=True,
            rebase_reason="3 commits behind",
            pr_mergeable=False,
        )
        assert result == (True, "3 commits behind")

    def test_rebase_needed_and_mergeable_none_unchanged(self) -> None:
        """When rebase needed and mergeable is None, keep original."""
        result = _apply_pr_merge_override(
            rebase_needed=True,
            rebase_reason="3 commits behind",
            pr_mergeable=None,
        )
        assert result == (True, "3 commits behind")


class TestPRFeedbackBlockingRecommendations:
    """Tests for `pr_feedback_blocks_merge` gating in `_generate_recommendations`."""

    def test_blocks_ready_to_merge_when_pr_feedback_blocks(self) -> None:
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.PASSED,
                "rebase_needed": False,
                "tasks_status": TaskTrackerStatus.COMPLETE,
                "tasks_reason": "All done",
                "tasks_is_blocking": False,
                "pr_feedback_blocks_merge": True,
            }
        )
        assert "Address review comments" in recs
        assert "Ready to merge" not in recs
        assert "Ready to merge (squash-merge safe)" not in recs

    def test_review_rec_emits_alongside_ci_failure(self) -> None:
        """`Address review comments` emits independently of CI state."""
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.FAILED,
                "rebase_needed": False,
                "tasks_status": TaskTrackerStatus.COMPLETE,
                "tasks_reason": "All done",
                "tasks_is_blocking": False,
                "pr_feedback_blocks_merge": True,
            }
        )
        assert "Fix CI test failures" in recs
        assert "Address review comments" in recs

    def test_review_rec_emits_alongside_blocking_tasks(self) -> None:
        """`Address review comments` emits independently of task state."""
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.PASSED,
                "rebase_needed": False,
                "tasks_status": TaskTrackerStatus.INCOMPLETE,
                "tasks_reason": "2 of 5",
                "tasks_is_blocking": True,
                "pr_feedback_blocks_merge": True,
            }
        )
        assert any("remaining tasks" in r.lower() for r in recs)
        assert "Address review comments" in recs

    def test_ready_to_merge_when_feedback_clean(self) -> None:
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.PASSED,
                "rebase_needed": False,
                "tasks_status": TaskTrackerStatus.COMPLETE,
                "tasks_reason": "All done",
                "tasks_is_blocking": False,
                "pr_feedback_blocks_merge": False,
            }
        )
        assert "Ready to merge" in recs

    def test_feedback_blocks_take_precedence_over_rebase_and_mergeable(self) -> None:
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.PASSED,
                "rebase_needed": True,
                "tasks_status": TaskTrackerStatus.COMPLETE,
                "tasks_reason": "All done",
                "tasks_is_blocking": False,
                "pr_mergeable": True,
                "pr_feedback_blocks_merge": True,
            }
        )
        assert "Address review comments" in recs
        assert "Ready to merge" not in recs
        assert "Ready to merge (squash-merge safe)" not in recs


class TestMergeableStateGuard:
    """Tests for `pr_mergeable_state` blocker in `_generate_recommendations`."""

    def test_unstable_blocks_ready_to_merge(self) -> None:
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.PASSED,
                "rebase_needed": False,
                "tasks_status": TaskTrackerStatus.COMPLETE,
                "tasks_reason": "All done",
                "tasks_is_blocking": False,
                "pr_mergeable": True,
                "pr_mergeable_state": "unstable",
            }
        )
        assert "Not ready to merge (GitHub mergeable_state: unstable)" in recs
        assert "Ready to merge" not in recs
        assert "Ready to merge (squash-merge safe)" not in recs

    def test_blocked_blocks_ready_to_merge(self) -> None:
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.PASSED,
                "rebase_needed": False,
                "tasks_status": TaskTrackerStatus.COMPLETE,
                "tasks_reason": "All done",
                "tasks_is_blocking": False,
                "pr_mergeable": True,
                "pr_mergeable_state": "blocked",
            }
        )
        assert "Not ready to merge (GitHub mergeable_state: blocked)" in recs
        assert "Ready to merge" not in recs
        assert "Ready to merge (squash-merge safe)" not in recs

    def test_dirty_blocks_ready_to_merge(self) -> None:
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.PASSED,
                "rebase_needed": False,
                "tasks_status": TaskTrackerStatus.COMPLETE,
                "tasks_reason": "All done",
                "tasks_is_blocking": False,
                "pr_mergeable": True,
                "pr_mergeable_state": "dirty",
            }
        )
        assert "Not ready to merge (GitHub mergeable_state: dirty)" in recs
        assert "Ready to merge" not in recs
        assert "Ready to merge (squash-merge safe)" not in recs

    def test_behind_does_not_block(self) -> None:
        """`behind` is not in the blocker set — already handled elsewhere."""
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.PASSED,
                "rebase_needed": False,
                "tasks_status": TaskTrackerStatus.COMPLETE,
                "tasks_reason": "All done",
                "tasks_is_blocking": False,
                "pr_mergeable": True,
                "pr_mergeable_state": "behind",
            }
        )
        assert "Ready to merge (squash-merge safe)" in recs
        assert not any(r.startswith("Not ready to merge") for r in recs)

    def test_none_does_not_block(self) -> None:
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.PASSED,
                "rebase_needed": False,
                "tasks_status": TaskTrackerStatus.COMPLETE,
                "tasks_reason": "All done",
                "tasks_is_blocking": False,
                "pr_mergeable_state": None,
            }
        )
        assert "Ready to merge" in recs
        assert not any(r.startswith("Not ready to merge") for r in recs)

    def test_clean_does_not_block(self) -> None:
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.PASSED,
                "rebase_needed": False,
                "tasks_status": TaskTrackerStatus.COMPLETE,
                "tasks_reason": "All done",
                "tasks_is_blocking": False,
                "pr_mergeable_state": "clean",
            }
        )
        assert "Ready to merge" in recs
        assert not any(r.startswith("Not ready to merge") for r in recs)

    def test_co_occurrence_additive(self) -> None:
        """All three blocker lines emit together when all three conditions hold."""
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.FAILED,
                "rebase_needed": False,
                "tasks_status": TaskTrackerStatus.COMPLETE,
                "tasks_reason": "All done",
                "tasks_is_blocking": False,
                "ci_failing_job_names": ["mssql-integration"],
                "pr_feedback_blocks_merge": True,
                "pr_mergeable_state": "unstable",
            }
        )
        assert "Fix failing job(s): mssql-integration" in recs
        assert "Address review comments" in recs
        assert "Not ready to merge (GitHub mergeable_state: unstable)" in recs
        assert "Ready to merge" not in recs
        assert "Ready to merge (squash-merge safe)" not in recs

    def test_unstable_emits_even_when_ci_failed(self) -> None:
        """`Not ready to merge` lifts out of the ci_ok branch."""
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.FAILED,
                "rebase_needed": False,
                "tasks_status": TaskTrackerStatus.COMPLETE,
                "tasks_reason": "All done",
                "tasks_is_blocking": False,
                "pr_mergeable_state": "unstable",
            }
        )
        assert "Not ready to merge (GitHub mergeable_state: unstable)" in recs

    def test_address_review_emits_even_when_ci_failed(self) -> None:
        """Regression: `Address review comments` lifts out of the ci_ok branch."""
        recs = _generate_recommendations(
            {
                "ci_status": CIStatus.FAILED,
                "rebase_needed": False,
                "tasks_status": TaskTrackerStatus.COMPLETE,
                "tasks_reason": "All done",
                "tasks_is_blocking": False,
                "pr_feedback_blocks_merge": True,
            }
        )
        assert "Address review comments" in recs
