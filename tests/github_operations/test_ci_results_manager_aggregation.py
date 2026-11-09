"""Tests for multi-workflow aggregation and pure functions in CIResultsManager."""

from types import SimpleNamespace
from unittest.mock import Mock

from mcp_workspace.github_operations import CIResultsManager
from mcp_workspace.github_operations.ci_results_manager import (
    aggregate_conclusion,
    filter_runs_by_head_sha,
)


def _make_mock_run(
    run_id: int,
    head_sha: str = "abc123",
    status: str = "completed",
    conclusion: str | None = "success",
    name: str = "CI",
    event: str = "push",
    path: str = ".github/workflows/ci.yml",
    branch: str = "feature/xyz",
) -> Mock:
    """Helper to create a mock workflow run."""
    mock_run = Mock()
    mock_run.id = run_id
    mock_run.status = status
    mock_run.conclusion = conclusion
    mock_run.name = name
    mock_run.event = event
    mock_run.path = path
    mock_run.head_sha = head_sha
    mock_run.head_branch = branch
    mock_run.created_at = Mock()
    mock_run.created_at.isoformat.return_value = "2024-01-15T10:30:00Z"
    mock_run.html_url = f"https://github.com/test/repo/actions/runs/{run_id}"
    return mock_run


def _make_mock_job(
    job_id: int,
    name: str = "test",
    status: str = "completed",
    conclusion: str | None = "success",
) -> Mock:
    """Helper to create a mock job."""
    mock_job = Mock()
    mock_job.id = job_id
    mock_job.name = name
    mock_job.status = status
    mock_job.conclusion = conclusion
    mock_job.started_at = Mock()
    mock_job.started_at.isoformat.return_value = "2024-01-15T10:31:00Z"
    mock_job.completed_at = Mock()
    mock_job.completed_at.isoformat.return_value = "2024-01-15T10:35:00Z"
    mock_job.steps = []
    mock_job.html_url = f"https://github.com/test/repo/actions/runs/0/job/{job_id}"
    return mock_job


class TestFilterRunsByHeadSha:
    """Tests for filter_runs_by_head_sha pure function."""

    def test_empty_input_returns_empty_list(self) -> None:
        result = filter_runs_by_head_sha([])
        assert result == []

    def test_all_runs_same_sha_returns_all(self) -> None:
        runs = [
            SimpleNamespace(head_sha="abc123"),
            SimpleNamespace(head_sha="abc123"),
            SimpleNamespace(head_sha="abc123"),
        ]
        result = filter_runs_by_head_sha(runs)
        assert len(result) == 3

    def test_mixed_shas_returns_only_latest(self) -> None:
        runs = [
            SimpleNamespace(head_sha="abc123"),
            SimpleNamespace(head_sha="abc123"),
            SimpleNamespace(head_sha="old_sha"),
            SimpleNamespace(head_sha="abc123"),
        ]
        result = filter_runs_by_head_sha(runs)
        assert len(result) == 3
        assert all(r.head_sha == "abc123" for r in result)

    def test_caps_at_max_runs(self) -> None:
        runs = [SimpleNamespace(head_sha="abc123") for _ in range(30)]
        result = filter_runs_by_head_sha(runs, max_runs=5)
        assert len(result) == 5


class TestAggregateConclusion:
    """Tests for aggregate_conclusion pure function."""

    def test_empty_input_returns_not_configured(self) -> None:
        result = aggregate_conclusion([])
        assert result == (None, "not_configured")

    def test_all_success_returns_success(self) -> None:
        runs = [
            SimpleNamespace(conclusion="success", status="completed"),
            SimpleNamespace(conclusion="success", status="completed"),
        ]
        result = aggregate_conclusion(runs)
        assert result == ("success", "completed")

    def test_one_failure_among_successes_returns_failure(self) -> None:
        runs = [
            SimpleNamespace(conclusion="success", status="completed"),
            SimpleNamespace(conclusion="failure", status="completed"),
            SimpleNamespace(conclusion="success", status="completed"),
        ]
        result = aggregate_conclusion(runs)
        assert result == ("failure", "completed")

    def test_no_failures_one_in_progress_returns_pending(self) -> None:
        runs = [
            SimpleNamespace(conclusion="success", status="completed"),
            SimpleNamespace(conclusion=None, status="in_progress"),
        ]
        result = aggregate_conclusion(runs)
        assert result == (None, "in_progress")

    def test_cancelled_treated_as_failure(self) -> None:
        runs = [
            SimpleNamespace(conclusion="cancelled", status="completed"),
            SimpleNamespace(conclusion="success", status="completed"),
        ]
        result = aggregate_conclusion(runs)
        assert result == ("failure", "completed")

    def test_timed_out_treated_as_failure(self) -> None:
        runs = [
            SimpleNamespace(conclusion="timed_out", status="completed"),
            SimpleNamespace(conclusion="success", status="completed"),
        ]
        result = aggregate_conclusion(runs)
        assert result == ("failure", "completed")


class TestGetLatestCIStatusMultiWorkflow:
    """Tests for multi-workflow aggregation in get_latest_ci_status."""

    def test_two_workflows_one_fails_one_passes(
        self, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """Aggregate conclusion should be 'failure'."""
        run1 = _make_mock_run(100, conclusion="failure")
        run1.jobs.return_value = [
            _make_mock_job(1001, name="test", conclusion="failure")
        ]

        run2 = _make_mock_run(200, conclusion="success")
        run2.jobs.return_value = [
            _make_mock_job(2001, name="lint", conclusion="success")
        ]

        mock_repo.get_workflow_runs.return_value = [run1, run2]

        result = ci_manager.get_latest_ci_status("feature/xyz")

        assert result["run"]["run_ids"] == [100, 200]
        assert result["run"]["conclusion"] == "failure"
        assert result["run"]["status"] == "completed"

    def test_two_workflows_one_pending_one_passes(
        self, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """Aggregate status should be 'in_progress', conclusion None."""
        run1 = _make_mock_run(100, status="in_progress", conclusion=None)
        run1.jobs.return_value = [
            _make_mock_job(1001, name="test", status="in_progress", conclusion=None)
        ]

        run2 = _make_mock_run(200, conclusion="success")
        run2.jobs.return_value = [
            _make_mock_job(2001, name="lint", conclusion="success")
        ]

        mock_repo.get_workflow_runs.return_value = [run1, run2]

        result = ci_manager.get_latest_ci_status("feature/xyz")

        assert result["run"]["run_ids"] == [100, 200]
        assert result["run"]["conclusion"] is None
        assert result["run"]["status"] == "in_progress"

    def test_two_workflows_both_pass(
        self, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """Aggregate conclusion should be 'success'."""
        run1 = _make_mock_run(100, conclusion="success")
        run1.jobs.return_value = [_make_mock_job(1001, name="test")]

        run2 = _make_mock_run(200, conclusion="success")
        run2.jobs.return_value = [_make_mock_job(2001, name="lint")]

        mock_repo.get_workflow_runs.return_value = [run1, run2]

        result = ci_manager.get_latest_ci_status("feature/xyz")

        assert result["run"]["run_ids"] == [100, 200]
        assert result["run"]["conclusion"] == "success"
        assert result["run"]["status"] == "completed"

    def test_mixed_head_sha_only_latest_counted(
        self, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """Runs with different head_sha should be excluded."""
        run1 = _make_mock_run(100, head_sha="latest_sha", conclusion="success")
        run1.jobs.return_value = [_make_mock_job(1001, name="test")]

        run2 = _make_mock_run(200, head_sha="old_sha", conclusion="failure")
        run2.jobs.return_value = [
            _make_mock_job(2001, name="lint", conclusion="failure")
        ]

        run3 = _make_mock_run(300, head_sha="latest_sha", conclusion="success")
        run3.jobs.return_value = [_make_mock_job(3001, name="build")]

        mock_repo.get_workflow_runs.return_value = [run1, run2, run3]

        result = ci_manager.get_latest_ci_status("feature/xyz")

        # Only runs with latest_sha (run1, run3) should be included
        assert result["run"]["run_ids"] == [100, 300]
        assert result["run"]["conclusion"] == "success"
        # Jobs from old_sha run should not appear
        job_names = [j["name"] for j in result["jobs"]]
        assert "lint" not in job_names
        assert "test" in job_names
        assert "build" in job_names

    def test_jobs_merged_across_workflows(
        self, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """Jobs from both runs should appear in result['jobs']."""
        run1 = _make_mock_run(100)
        run1.jobs.return_value = [
            _make_mock_job(1001, name="test"),
            _make_mock_job(1002, name="build"),
        ]

        run2 = _make_mock_run(200)
        run2.jobs.return_value = [
            _make_mock_job(2001, name="lint"),
        ]

        mock_repo.get_workflow_runs.return_value = [run1, run2]

        result = ci_manager.get_latest_ci_status("feature/xyz")

        assert len(result["jobs"]) == 3
        job_names = [j["name"] for j in result["jobs"]]
        assert "test" in job_names
        assert "build" in job_names
        assert "lint" in job_names

    def test_jobs_carry_run_id(
        self, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """Each job's run_id should match its parent workflow run."""
        run1 = _make_mock_run(100)
        run1.jobs.return_value = [_make_mock_job(1001, name="test")]

        run2 = _make_mock_run(200, event="pull_request")
        run2.jobs.return_value = [_make_mock_job(2001, name="lint")]

        mock_repo.get_workflow_runs.return_value = [run1, run2]

        result = ci_manager.get_latest_ci_status("feature/xyz")

        test_job = next(j for j in result["jobs"] if j["name"] == "test")
        assert test_job["run_id"] == 100
        assert test_job["run_html_url"] == run1.html_url
        assert test_job["run_event"] == "push"

        lint_job = next(j for j in result["jobs"] if j["name"] == "lint")
        assert lint_job["run_id"] == 200
        assert lint_job["run_html_url"] == run2.html_url
        assert lint_job["run_event"] == "pull_request"

    def test_jobs_call_failure_partial_results(
        self, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """If .jobs() raises on one run, return partial results from other runs + warning."""
        run1 = _make_mock_run(100)
        run1.jobs.side_effect = Exception("API error")

        run2 = _make_mock_run(200)
        run2.jobs.return_value = [_make_mock_job(2001, name="lint")]

        mock_repo.get_workflow_runs.return_value = [run1, run2]

        result = ci_manager.get_latest_ci_status("feature/xyz")

        # Should have partial jobs from run2
        assert len(result["jobs"]) == 1
        assert result["jobs"][0]["name"] == "lint"
        assert result["jobs"][0]["run_id"] == 200

        # Should have warning about failed jobs fetch
        assert "jobs_fetch_warning" in result["run"]
        assert "100" in result["run"]["jobs_fetch_warning"]
