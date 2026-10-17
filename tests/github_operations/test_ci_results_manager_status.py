"""Tests for CIResultsManager get_latest_ci_status method."""

from unittest.mock import Mock, patch

import pytest
from github import GithubException

from mcp_workspace.github_operations import CIResultsManager


class TestGetLatestCIStatus:
    """Test the get_latest_ci_status method."""

    def test_successful_status_retrieval(
        self, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """Test successful CI status retrieval with jobs."""
        # Mock workflow run
        mock_run = Mock()
        mock_run.id = 123456789
        mock_run.status = "completed"
        mock_run.conclusion = "failure"
        mock_run.name = "CI"
        mock_run.event = "push"
        mock_run.path = ".github/workflows/ci.yml"
        mock_run.head_sha = "abc123def456"
        mock_run.created_at = Mock()
        mock_run.created_at.isoformat.return_value = "2024-01-15T10:30:00Z"
        mock_run.html_url = "https://github.com/test/repo/actions/runs/123456789"

        # Mock jobs
        mock_job1 = Mock()
        mock_job1.id = 987654321
        mock_job1.name = "test"
        mock_job1.status = "completed"
        mock_job1.conclusion = "failure"
        mock_job1.started_at = Mock()
        mock_job1.started_at.isoformat.return_value = "2024-01-15T10:31:00Z"
        mock_job1.completed_at = Mock()
        mock_job1.completed_at.isoformat.return_value = "2024-01-15T10:35:00Z"
        mock_job1.steps = []

        mock_job2 = Mock()
        mock_job2.id = 987654322
        mock_job2.name = "build"
        mock_job2.status = "completed"
        mock_job2.conclusion = "success"
        mock_job2.started_at = Mock()
        mock_job2.started_at.isoformat.return_value = "2024-01-15T10:31:00Z"
        mock_job2.completed_at = Mock()
        mock_job2.completed_at.isoformat.return_value = "2024-01-15T10:33:00Z"
        mock_job2.steps = []

        # Set head_branch for filtering
        mock_run.head_branch = "feature/xyz"

        mock_run.jobs.return_value = [mock_job1, mock_job2]
        mock_repo.get_workflow_runs.return_value = [mock_run]

        # Test the method
        result = ci_manager.get_latest_ci_status("feature/xyz")

        # Verify the result structure
        assert "run" in result
        assert "jobs" in result

        # Verify run data
        run_data = result["run"]
        assert run_data["run_ids"] == [123456789]
        assert run_data["status"] == "completed"
        assert run_data["conclusion"] == "failure"
        assert run_data["workflow_name"] == "CI"
        assert run_data["event"] == "push"
        assert run_data["workflow_path"] == ".github/workflows/ci.yml"
        assert run_data["branch"] == "feature/xyz"
        assert run_data["commit_sha"] == "abc123def456"
        assert run_data["created_at"] == "2024-01-15T10:30:00Z"
        assert run_data["url"] == "https://github.com/test/repo/actions/runs/123456789"

        # Verify jobs data
        jobs_data = result["jobs"]
        assert len(jobs_data) == 2

        job1_data = jobs_data[0]
        assert job1_data["id"] == 987654321
        assert job1_data["run_id"] == 123456789
        assert job1_data["name"] == "test"
        assert job1_data["status"] == "completed"
        assert job1_data["conclusion"] == "failure"
        assert job1_data["started_at"] == "2024-01-15T10:31:00Z"
        assert job1_data["completed_at"] == "2024-01-15T10:35:00Z"

        job2_data = jobs_data[1]
        assert job2_data["id"] == 987654322
        assert job2_data["run_id"] == 123456789
        assert job2_data["name"] == "build"
        assert job2_data["status"] == "completed"
        assert job2_data["conclusion"] == "success"

        # Verify API was called correctly
        mock_repo.get_workflow_runs.assert_called_once()
        mock_run.jobs.assert_called_once()


class TestGetLatestCIStatusSteps:
    """Tests for step-level data in get_latest_ci_status."""

    def test_jobs_include_steps_data(
        self, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """Job info should include steps array with number, name, conclusion."""
        # Setup mock workflow run
        mock_run = Mock()
        mock_run.id = 123456789
        mock_run.status = "completed"
        mock_run.conclusion = "success"
        mock_run.name = "CI"
        mock_run.event = "push"
        mock_run.path = ".github/workflows/ci.yml"
        mock_run.head_sha = "abc123def456"
        mock_run.head_branch = "main"
        mock_run.created_at = Mock()
        mock_run.created_at.isoformat.return_value = "2024-01-15T10:30:00Z"
        mock_run.html_url = "https://github.com/test/repo/actions/runs/123456789"

        # Setup mock job with steps
        mock_job = Mock()
        mock_job.id = 987654321
        mock_job.name = "test"
        mock_job.status = "completed"
        mock_job.conclusion = "success"
        mock_job.started_at = Mock()
        mock_job.started_at.isoformat.return_value = "2024-01-15T10:31:00Z"
        mock_job.completed_at = Mock()
        mock_job.completed_at.isoformat.return_value = "2024-01-15T10:35:00Z"

        # Setup mock steps
        mock_step1 = Mock()
        mock_step1.number = 1
        mock_step1.name = "Set up job"
        mock_step1.conclusion = "success"

        mock_step2 = Mock()
        mock_step2.number = 2
        mock_step2.name = "Run tests"
        mock_step2.conclusion = "success"

        mock_step3 = Mock()
        mock_step3.number = 3
        mock_step3.name = "Post Set up job"
        mock_step3.conclusion = "success"

        mock_job.steps = [mock_step1, mock_step2, mock_step3]
        mock_run.jobs.return_value = [mock_job]
        mock_repo.get_workflow_runs.return_value = [mock_run]

        # Test the method
        result = ci_manager.get_latest_ci_status("main")

        # Verify steps data is included in job
        assert len(result["jobs"]) == 1
        job_data = result["jobs"][0]
        assert "steps" in job_data
        assert len(job_data["steps"]) == 3

        # Verify step data structure
        step1 = job_data["steps"][0]
        assert step1["number"] == 1
        assert step1["name"] == "Set up job"
        assert step1["conclusion"] == "success"

        step2 = job_data["steps"][1]
        assert step2["number"] == 2
        assert step2["name"] == "Run tests"
        assert step2["conclusion"] == "success"

    def test_steps_contain_required_fields(
        self, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """Each step should have number, name, and conclusion fields."""
        # Setup mock workflow run
        mock_run = Mock()
        mock_run.id = 123456789
        mock_run.status = "completed"
        mock_run.conclusion = "failure"
        mock_run.name = "CI"
        mock_run.event = "push"
        mock_run.path = ".github/workflows/ci.yml"
        mock_run.head_sha = "abc123def456"
        mock_run.head_branch = "feature/test"
        mock_run.created_at = Mock()
        mock_run.created_at.isoformat.return_value = "2024-01-15T10:30:00Z"
        mock_run.html_url = "https://github.com/test/repo/actions/runs/123456789"

        # Setup mock job with steps having different conclusions
        mock_job = Mock()
        mock_job.id = 987654321
        mock_job.name = "build"
        mock_job.status = "completed"
        mock_job.conclusion = "failure"
        mock_job.started_at = Mock()
        mock_job.started_at.isoformat.return_value = "2024-01-15T10:31:00Z"
        mock_job.completed_at = Mock()
        mock_job.completed_at.isoformat.return_value = "2024-01-15T10:35:00Z"

        # Steps with various conclusions
        mock_step1 = Mock()
        mock_step1.number = 1
        mock_step1.name = "Checkout"
        mock_step1.conclusion = "success"

        mock_step2 = Mock()
        mock_step2.number = 2
        mock_step2.name = "Build"
        mock_step2.conclusion = "failure"

        mock_step3 = Mock()
        mock_step3.number = 3
        mock_step3.name = "Deploy"
        mock_step3.conclusion = "skipped"

        mock_step4 = Mock()
        mock_step4.number = 4
        mock_step4.name = "Cleanup"
        mock_step4.conclusion = None  # Still running or not started

        mock_job.steps = [mock_step1, mock_step2, mock_step3, mock_step4]
        mock_run.jobs.return_value = [mock_job]
        mock_repo.get_workflow_runs.return_value = [mock_run]

        # Test the method
        result = ci_manager.get_latest_ci_status("feature/test")

        # Verify all steps have required fields
        job_data = result["jobs"][0]
        for step in job_data["steps"]:
            assert "number" in step
            assert "name" in step
            assert "conclusion" in step
            assert isinstance(step["number"], int)
            assert isinstance(step["name"], str)

        # Verify specific conclusions
        assert job_data["steps"][0]["conclusion"] == "success"
        assert job_data["steps"][1]["conclusion"] == "failure"
        assert job_data["steps"][2]["conclusion"] == "skipped"
        assert job_data["steps"][3]["conclusion"] is None

    def test_empty_steps_when_job_has_no_steps(
        self, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """Jobs with no steps should have empty steps array."""
        # Setup mock workflow run
        mock_run = Mock()
        mock_run.id = 123456789
        mock_run.status = "completed"
        mock_run.conclusion = "success"
        mock_run.name = "CI"
        mock_run.event = "push"
        mock_run.path = ".github/workflows/ci.yml"
        mock_run.head_sha = "abc123def456"
        mock_run.head_branch = "main"
        mock_run.created_at = Mock()
        mock_run.created_at.isoformat.return_value = "2024-01-15T10:30:00Z"
        mock_run.html_url = "https://github.com/test/repo/actions/runs/123456789"

        # Setup mock job with no steps
        mock_job = Mock()
        mock_job.id = 987654321
        mock_job.name = "simple-job"
        mock_job.status = "completed"
        mock_job.conclusion = "success"
        mock_job.started_at = Mock()
        mock_job.started_at.isoformat.return_value = "2024-01-15T10:31:00Z"
        mock_job.completed_at = Mock()
        mock_job.completed_at.isoformat.return_value = "2024-01-15T10:35:00Z"
        mock_job.steps = []  # No steps

        mock_run.jobs.return_value = [mock_job]
        mock_repo.get_workflow_runs.return_value = [mock_run]

        # Test the method
        result = ci_manager.get_latest_ci_status("main")

        # Verify empty steps array
        assert len(result["jobs"]) == 1
        job_data = result["jobs"][0]
        assert "steps" in job_data
        assert job_data["steps"] == []

    def test_multiple_jobs_with_steps(
        self, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """Multiple jobs should each have their own steps array."""
        # Setup mock workflow run
        mock_run = Mock()
        mock_run.id = 123456789
        mock_run.status = "completed"
        mock_run.conclusion = "success"
        mock_run.name = "CI"
        mock_run.event = "push"
        mock_run.path = ".github/workflows/ci.yml"
        mock_run.head_sha = "abc123def456"
        mock_run.head_branch = "main"
        mock_run.created_at = Mock()
        mock_run.created_at.isoformat.return_value = "2024-01-15T10:30:00Z"
        mock_run.html_url = "https://github.com/test/repo/actions/runs/123456789"

        # Setup first job with steps
        mock_job1 = Mock()
        mock_job1.id = 111
        mock_job1.name = "lint"
        mock_job1.status = "completed"
        mock_job1.conclusion = "success"
        mock_job1.started_at = Mock()
        mock_job1.started_at.isoformat.return_value = "2024-01-15T10:31:00Z"
        mock_job1.completed_at = Mock()
        mock_job1.completed_at.isoformat.return_value = "2024-01-15T10:32:00Z"

        mock_step1_1 = Mock()
        mock_step1_1.number = 1
        mock_step1_1.name = "Run linter"
        mock_step1_1.conclusion = "success"
        mock_job1.steps = [mock_step1_1]

        # Setup second job with different steps
        mock_job2 = Mock()
        mock_job2.id = 222
        mock_job2.name = "test"
        mock_job2.status = "completed"
        mock_job2.conclusion = "success"
        mock_job2.started_at = Mock()
        mock_job2.started_at.isoformat.return_value = "2024-01-15T10:31:00Z"
        mock_job2.completed_at = Mock()
        mock_job2.completed_at.isoformat.return_value = "2024-01-15T10:35:00Z"

        mock_step2_1 = Mock()
        mock_step2_1.number = 1
        mock_step2_1.name = "Setup Python"
        mock_step2_1.conclusion = "success"

        mock_step2_2 = Mock()
        mock_step2_2.number = 2
        mock_step2_2.name = "Run pytest"
        mock_step2_2.conclusion = "success"
        mock_job2.steps = [mock_step2_1, mock_step2_2]

        mock_run.jobs.return_value = [mock_job1, mock_job2]
        mock_repo.get_workflow_runs.return_value = [mock_run]

        # Test the method
        result = ci_manager.get_latest_ci_status("main")

        # Verify both jobs have their own steps
        assert len(result["jobs"]) == 2

        lint_job = next(j for j in result["jobs"] if j["name"] == "lint")
        assert len(lint_job["steps"]) == 1
        assert lint_job["steps"][0]["name"] == "Run linter"

        test_job = next(j for j in result["jobs"] if j["name"] == "test")
        assert len(test_job["steps"]) == 2
        assert test_job["steps"][0]["name"] == "Setup Python"
        assert test_job["steps"][1]["name"] == "Run pytest"

    def test_no_workflow_runs_for_branch(
        self, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """Test when no workflow runs exist for the branch."""
        mock_repo.get_workflow_runs.return_value = []

        result = ci_manager.get_latest_ci_status("feature/no-runs")

        # Should return empty data
        assert result["run"] == {}  # type: ignore[comparison-overlap]
        assert result["jobs"] == []

        mock_repo.get_workflow_runs.assert_called_once()

    def test_invalid_branch_name(self, ci_manager: CIResultsManager) -> None:
        """Test with invalid branch name raises ValueError."""
        # Empty branch name - raises ValueError
        with pytest.raises(
            ValueError, match="Invalid branch name: branch name cannot be empty"
        ):
            ci_manager.get_latest_ci_status("")

        # Invalid character ~ - raises ValueError
        with pytest.raises(ValueError, match="Invalid branch name"):
            ci_manager.get_latest_ci_status("branch~1")

        # Invalid character ^ - raises ValueError
        with pytest.raises(ValueError, match="Invalid branch name"):
            ci_manager.get_latest_ci_status("branch^2")

    def test_run_with_multiple_jobs(
        self, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """Test CI run with multiple jobs of different statuses."""
        mock_run = Mock()
        mock_run.id = 999888777
        mock_run.status = "in_progress"
        mock_run.conclusion = None
        mock_run.name = "Build and Test"
        mock_run.event = "pull_request"
        mock_run.path = ".github/workflows/build.yml"
        mock_run.head_sha = "xyz789abc123"
        mock_run.created_at = Mock()
        mock_run.created_at.isoformat.return_value = "2024-01-15T11:00:00Z"
        mock_run.html_url = "https://github.com/test/repo/actions/runs/999888777"

        # Multiple jobs with different statuses
        jobs = []
        job_configs = [
            {"id": 111, "name": "lint", "status": "completed", "conclusion": "success"},
            {"id": 222, "name": "test", "status": "in_progress", "conclusion": None},
            {"id": 333, "name": "build", "status": "queued", "conclusion": None},
        ]

        for config in job_configs:
            job = Mock()
            job.id = config["id"]
            job.name = config["name"]
            job.status = config["status"]
            job.conclusion = config["conclusion"]
            job.started_at = Mock() if config["status"] != "queued" else None
            if job.started_at:
                job.started_at.isoformat.return_value = "2024-01-15T11:01:00Z"
            job.completed_at = Mock() if config["status"] == "completed" else None
            if job.completed_at:
                job.completed_at.isoformat.return_value = "2024-01-15T11:05:00Z"
            job.steps = []
            jobs.append(job)

        # Set head_branch for filtering
        mock_run.head_branch = "main"

        mock_run.jobs.return_value = jobs
        mock_repo.get_workflow_runs.return_value = [mock_run]

        result = ci_manager.get_latest_ci_status("main")

        # Verify run data
        run_data = result["run"]
        assert run_data["run_ids"] == [999888777]
        assert run_data["status"] == "in_progress"
        assert run_data["conclusion"] is None
        assert run_data["workflow_name"] == "Build and Test"
        assert run_data["event"] == "pull_request"

        # Verify all jobs are included
        jobs_data = result["jobs"]
        assert len(jobs_data) == 3

        # Check specific job statuses
        job_names = [job["name"] for job in jobs_data]
        assert "lint" in job_names
        assert "test" in job_names
        assert "build" in job_names

        # Find and check specific jobs
        lint_job = next(job for job in jobs_data if job["name"] == "lint")
        assert lint_job["run_id"] == 999888777
        assert lint_job["status"] == "completed"
        assert lint_job["conclusion"] == "success"
        assert lint_job["completed_at"] == "2024-01-15T11:05:00Z"

        test_job = next(job for job in jobs_data if job["name"] == "test")
        assert test_job["run_id"] == 999888777
        assert test_job["status"] == "in_progress"
        assert test_job["conclusion"] is None
        assert test_job["completed_at"] is None

        build_job = next(job for job in jobs_data if job["name"] == "build")
        assert build_job["run_id"] == 999888777
        assert build_job["status"] == "queued"
        assert build_job["conclusion"] is None
        assert build_job["started_at"] is None

    def test_github_api_error_handling(
        self, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """Test handling of GitHub API errors."""
        # Test authentication error
        mock_repo.get_workflow_runs.side_effect = GithubException(
            401, "Bad credentials", {}
        )

        with pytest.raises(GithubException):
            ci_manager.get_latest_ci_status("main")

        # Test rate limit error
        mock_repo.get_workflow_runs.side_effect = GithubException(
            403, "API rate limit exceeded", {}
        )

        with pytest.raises(GithubException):
            ci_manager.get_latest_ci_status("main")

    def test_run_without_jobs(
        self, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """Test CI run that has no jobs."""
        mock_run = Mock()
        mock_run.id = 555444333
        mock_run.status = "completed"
        mock_run.conclusion = "cancelled"
        mock_run.name = "CI"
        mock_run.event = "push"
        mock_run.path = ".github/workflows/ci.yml"
        mock_run.head_sha = "cancelled123"
        mock_run.created_at = Mock()
        mock_run.created_at.isoformat.return_value = "2024-01-15T12:00:00Z"
        mock_run.html_url = "https://github.com/test/repo/actions/runs/555444333"

        # Set head_branch for filtering
        mock_run.head_branch = "feature/empty-jobs"

        # No jobs for this run
        mock_run.jobs.return_value = []
        mock_repo.get_workflow_runs.return_value = [mock_run]

        result = ci_manager.get_latest_ci_status("feature/empty-jobs")

        # Should have run data but no jobs
        assert result["run"]["run_ids"] == [555444333]
        # "cancelled" is aggregated as "failure" by aggregate_conclusion()
        assert result["run"]["conclusion"] == "failure"
        assert result["jobs"] == []

        mock_run.jobs.assert_called_once()


class TestLookupFailedFlag:
    """Tests for the lookup_failed flag on CIStatusData."""

    def test_lookup_failed_set_on_non_auth_github_exception(
        self, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """A non-auth GithubException sets lookup_failed True on the default return."""
        mock_repo.get_workflow_runs.side_effect = GithubException(500, "boom", {})

        result = ci_manager.get_latest_ci_status("main")

        assert result["run"] == {}  # type: ignore[comparison-overlap]
        assert result.get("lookup_failed") is True

    def test_lookup_failed_set_on_generic_exception(
        self, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """A generic exception sets lookup_failed True on the default return."""
        mock_repo.get_workflow_runs.side_effect = RuntimeError("boom")

        result = ci_manager.get_latest_ci_status("main")

        assert result["run"] == {}  # type: ignore[comparison-overlap]
        assert result.get("lookup_failed") is True

    def test_lookup_failed_set_when_repository_inaccessible(
        self, ci_manager: CIResultsManager
    ) -> None:
        """An inaccessible repository sets lookup_failed True."""
        with patch.object(ci_manager, "_get_repository", return_value=None):
            result = ci_manager.get_latest_ci_status("main")

        assert result["run"] == {}  # type: ignore[comparison-overlap]
        assert result.get("lookup_failed") is True

    def test_lookup_failed_absent_on_success(
        self, mock_repo: Mock, ci_manager: CIResultsManager
    ) -> None:
        """A successful lookup does not set lookup_failed at all."""
        mock_run = Mock()
        mock_run.id = 123456789
        mock_run.status = "completed"
        mock_run.conclusion = "success"
        mock_run.name = "CI"
        mock_run.event = "push"
        mock_run.path = ".github/workflows/ci.yml"
        mock_run.head_sha = "abc123def456"
        mock_run.head_branch = "main"
        mock_run.created_at = Mock()
        mock_run.created_at.isoformat.return_value = "2024-01-15T10:30:00Z"
        mock_run.html_url = "https://github.com/test/repo/actions/runs/123456789"
        mock_run.jobs.return_value = []
        mock_repo.get_workflow_runs.return_value = [mock_run]

        result = ci_manager.get_latest_ci_status("main")

        assert "lookup_failed" not in result
