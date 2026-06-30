"""CI Results Manager for GitHub API operations.

This module provides data structures and the CIResultsManager class for managing
GitHub CI pipeline results through the PyGithub library.
"""

import io
import logging
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TypedDict, cast

import requests
from mcp_coder_utils.log_utils import log_function_call
from typing_extensions import NotRequired

from mcp_workspace.git_operations.branch_queries import validate_branch_name

from .base_manager import BaseGitHubManager, _handle_github_errors

logger = logging.getLogger(__name__)

__all__ = [
    "StepData",
    "JobData",
    "RunData",
    "CIStatusData",
    "CIResultsManager",
    "filter_runs_by_head_sha",
    "aggregate_conclusion",
]


class StepData(TypedDict):
    """TypedDict for workflow job step data."""

    number: int
    name: str
    conclusion: Optional[str]  # "success", "failure", "skipped", None


class JobData(TypedDict):
    """TypedDict for workflow job data."""

    id: int
    run_id: int
    name: str
    status: str
    conclusion: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]
    steps: List[StepData]


class RunData(TypedDict):
    """TypedDict for workflow run data."""

    run_ids: List[int]
    status: str
    conclusion: Optional[str]
    workflow_name: str
    event: str
    workflow_path: str
    branch: str
    commit_sha: str
    created_at: str
    url: str
    jobs_fetch_warning: NotRequired[str]


class CIStatusData(TypedDict):
    """TypedDict for CI status data structure.

    Represents a GitHub workflow run with its associated jobs.
    """

    run: RunData
    jobs: List[JobData]


def filter_runs_by_head_sha(runs: List[Any], max_runs: int = 25) -> List[Any]:
    """Filter workflow runs to only those matching the latest commit SHA.

    Args:
        runs: List of PyGithub WorkflowRun objects (or duck-typed equivalents).
        max_runs: Maximum number of runs to return.

    Returns:
        Filtered list of runs matching the first run's head_sha, capped at max_runs.
    """
    if not runs:
        return []
    target_sha = runs[0].head_sha
    filtered = [r for r in runs if r.head_sha == target_sha]
    return filtered[:max_runs]


def aggregate_conclusion(
    runs: List[Any],
) -> Tuple[Optional[str], str]:
    """Aggregate conclusion and status across multiple workflow runs.

    Priority: failure/cancelled/timed_out > in_progress > success.

    Args:
        runs: List of objects with .conclusion and .status attributes.

    Returns:
        Tuple of (conclusion, status).
    """
    if not runs:
        return (None, "not_configured")
    conclusions = [r.conclusion for r in runs]
    statuses = [r.status for r in runs]
    if any(c in ("failure", "cancelled", "timed_out") for c in conclusions):
        return ("failure", "completed")
    if any(s in ("in_progress", "queued", "pending") for s in statuses):
        return (None, "in_progress")
    if all(c == "success" for c in conclusions):
        return ("success", "completed")
    return (None, "in_progress")


class CIResultsManager(BaseGitHubManager):
    """Manages GitHub CI pipeline results using the GitHub API.

    This class provides methods for retrieving CI status, failed job logs,
    and artifacts from GitHub workflow runs.

    Configuration:
        Requires GitHub token in config file (~/.mcp_coder/config.toml):

        [github]
        token = "ghp_your_personal_access_token_here"

        Token needs 'repo' scope for private repositories, 'public_repo' for public.
    """

    DEFAULT_REQUEST_TIMEOUT: int = 60  # seconds
    DEFAULT_CONNECT_TIMEOUT: int = 10  # seconds

    def __init__(
        self,
        project_dir: Optional[Path] = None,
        repo_url: Optional[str] = None,
        github_token: Optional[str] = None,
    ) -> None:
        """Initialize the CIResultsManager.

        Args:
            project_dir: Path to the project directory containing git repository
            repo_url: GitHub repository URL (e.g., "https://github.com/user/repo.git")
            github_token: Optional explicit token — overrides config lookup when provided.

        """
        super().__init__(
            project_dir=project_dir,
            repo_url=repo_url,
            github_token=github_token,
        )

    def _validate_branch_name(self, branch: str) -> bool:
        """Validate branch name using git naming rules.

        Args:
            branch: Branch name to validate

        Returns:
            True if valid, False otherwise
        """
        if not validate_branch_name(branch):
            logger.error(f"Invalid branch name: '{branch}'")
            return False
        return True

    def _validate_run_id(self, run_id: int) -> bool:
        """Validate workflow run ID.

        Args:
            run_id: Workflow run ID to validate

        Returns:
            True if valid, False otherwise
        """
        if not isinstance(run_id, int) or run_id <= 0:
            logger.error(f"Invalid run ID: {run_id}. Must be a positive integer.")
            return False
        return True

    @log_function_call
    @_handle_github_errors(default_return=CIStatusData(run={}, jobs=[]))  # type: ignore[typeddict-item]
    def get_latest_ci_status(self, branch: str) -> CIStatusData:
        """Get latest CI run status and job results for a branch.

        Args:
            branch: Branch name (required, e.g., 'feature/xyz', 'main')

        Returns:
            CIStatusData with run info and all job statuses

        Raises:
            ValueError: For invalid branch names
        """
        # Validate branch parameter
        if not branch or not branch.strip():
            raise ValueError("Invalid branch name: branch name cannot be empty")

        if not self._validate_branch_name(branch.strip()):
            raise ValueError(f"Invalid branch name: '{branch}'")

        branch = branch.strip()

        # Get repository
        repo = self._get_repository()
        if not repo:
            logger.error("Could not access GitHub repository")
            return CIStatusData(run={}, jobs=[])  # type: ignore[typeddict-item]

        # Get workflow runs for the branch
        try:
            # Get workflow runs filtered by branch (server-side for performance)
            # Note: PyGithub accepts string branch names despite type stubs expecting Branch
            runs_paged = repo.get_workflow_runs(branch=branch)  # type: ignore[arg-type]

            # Get the first run (latest)
            try:
                first_run = runs_paged[0]
            except IndexError:
                logger.info(f"No workflow runs found for branch: {branch}")
                return CIStatusData(run={}, jobs=[])  # type: ignore[typeddict-item]

            # Filter to latest commit SHA
            all_runs: List[Any] = list(runs_paged[:25])  # cap iteration
            same_sha_runs = filter_runs_by_head_sha(all_runs)

            # Aggregate conclusion across all runs
            agg_conclusion, agg_status = aggregate_conclusion(same_sha_runs)

            # Fetch and merge jobs from all runs (Decision 7: partial results)
            all_jobs: List[JobData] = []
            failed_to_fetch_runs: List[int] = []
            for run in same_sha_runs:
                try:
                    for job in run.jobs():
                        job_data: JobData = {
                            "id": job.id,
                            "run_id": run.id,
                            "name": job.name,
                            "status": job.status,
                            "conclusion": job.conclusion,
                            "started_at": (
                                job.started_at.isoformat() if job.started_at else None
                            ),
                            "completed_at": (
                                job.completed_at.isoformat()
                                if job.completed_at
                                else None
                            ),
                            "steps": cast(
                                List[StepData],
                                [
                                    {
                                        "number": step.number,
                                        "name": step.name,
                                        "conclusion": step.conclusion,
                                    }
                                    for step in job.steps
                                ],
                            ),
                        }
                        all_jobs.append(job_data)
                except (
                    Exception
                ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow exception type
                    logger.warning(f"Failed to fetch jobs for run {run.id}: {e}")
                    failed_to_fetch_runs.append(run.id)

            # Build aggregate run_data dict
            run_data: RunData = {
                "run_ids": [r.id for r in same_sha_runs],
                "status": agg_status,
                "conclusion": agg_conclusion,
                "workflow_name": first_run.name,
                "event": first_run.event,
                "workflow_path": first_run.path,
                "branch": branch,
                "commit_sha": first_run.head_sha,
                "created_at": (
                    first_run.created_at.isoformat() if first_run.created_at else ""
                ),
                "url": first_run.html_url,
            }

            # If any runs failed to fetch jobs, add warning (Decision 7)
            if failed_to_fetch_runs:
                run_data["jobs_fetch_warning"] = (
                    f"Could not fetch jobs for run(s): {failed_to_fetch_runs}"
                )

            return CIStatusData(run=run_data, jobs=all_jobs)

        except (
            Exception
        ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow exception type
            logger.error(f"Error retrieving CI status for branch {branch}: {e}")
            # Re-raise to let the decorator handle it
            raise

    def _download_and_extract_zip(self, url: str) -> Dict[str, str]:
        """Download ZIP from URL and extract contents.

        Args:
            url: URL to download ZIP from

        Returns:
            Dictionary mapping filenames to their contents as strings.
            Binary files are skipped with a log warning (Decision 19).
        """
        try:
            # Make authenticated HTTP request
            headers = {
                "Authorization": f"Bearer {self.github_token}",
                "Accept": "application/vnd.github.v3+json",
            }

            response = requests.get(
                url,
                headers=headers,
                allow_redirects=True,
                timeout=(self.DEFAULT_CONNECT_TIMEOUT, self.DEFAULT_REQUEST_TIMEOUT),
            )
            response.raise_for_status()

            # Extract ZIP contents
            zip_buffer = io.BytesIO(response.content)
            extracted_files = {}

            with zipfile.ZipFile(zip_buffer, "r") as zip_file:
                for file_name in zip_file.namelist():
                    try:
                        # Try to decode as UTF-8 text
                        file_content = zip_file.read(file_name).decode("utf-8")
                        extracted_files[file_name] = file_content
                    except UnicodeDecodeError:
                        # Skip binary files with log warning (Decision 19)
                        logger.warning(
                            f"Skipping binary file '{file_name}' - only text files are supported"
                        )
                        continue
                    except (
                        Exception
                    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow exception type
                        logger.warning(f"Failed to extract file {file_name}: {e}")
                        continue

            return extracted_files

        except (
            Exception
        ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow exception type
            logger.error(f"Failed to download and extract ZIP from {url}: {e}")
            return {}

    @log_function_call
    @_handle_github_errors(default_return={})
    def get_run_logs(self, run_id: int) -> Dict[str, str]:
        """Get all console logs from a workflow run.

        Args:
            run_id: Workflow run ID to get logs from

        Returns:
            Dictionary mapping log filenames to their contents.
            Log filenames typically include job name (e.g., "test/1_Setup.txt").
            Consumer can filter by job name using info from get_latest_ci_status().

        Raises:
            ValueError: For invalid run IDs
        """
        # Validate run_id parameter
        if not self._validate_run_id(run_id):
            raise ValueError(
                f"Invalid workflow run ID: {run_id}. Must be a positive integer."
            )

        try:
            # Get repository and workflow run
            repo = self._get_repository()
            if not repo:
                logger.error("Could not access GitHub repository")
                return {}

            workflow_run = repo.get_workflow_run(run_id)

            # Get logs URL and download
            logs_url = workflow_run.logs_url
            return self._download_and_extract_zip(logs_url)

        except (
            Exception
        ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow exception type
            logger.error(f"Error retrieving logs for run ID {run_id}: {e}")
            # Re-raise to let the decorator handle it
            raise

    @log_function_call
    @_handle_github_errors(default_return={})
    def get_artifacts(
        self, run_id: int, name_filter: Optional[str] = None
    ) -> Dict[str, str]:
        """Download and return artifact contents from a workflow run.

        Args:
            run_id: Workflow run ID to get artifacts from
            name_filter: Optional filter - only return artifacts containing this string
                         in their name (case-insensitive). If None, returns all artifacts.

        Returns:
            Dictionary mapping artifact file names to their contents as strings.
            Binary files are skipped with a log warning (Decision 19).
            Artifacts are ZIP files - contents are extracted and returned.
            Example: {"test-results.xml": "<xml content...>", "coverage.json": "{...}"}

            Note: No size limit - consumer should use name_filter for large runs (Decision 18).

        Raises:
            ValueError: For invalid run IDs
        """
        # Validate run_id parameter
        if not self._validate_run_id(run_id):
            raise ValueError(
                f"Invalid workflow run ID: {run_id}. Must be a positive integer."
            )

        try:
            # Get repository and workflow run
            repo = self._get_repository()
            if not repo:
                logger.error("Could not access GitHub repository")
                return {}

            workflow_run = repo.get_workflow_run(run_id)

            # Get artifacts from the workflow run
            artifacts = list(workflow_run.get_artifacts())

            # Apply name filter if provided (case-insensitive)
            if name_filter:
                filtered_artifacts = [
                    artifact
                    for artifact in artifacts
                    if name_filter.lower() in artifact.name.lower()
                ]
                artifacts = filtered_artifacts

            if not artifacts:
                filter_msg = f" with filter '{name_filter}'" if name_filter else ""
                logger.info(f"No artifacts found for run ID {run_id}{filter_msg}")
                return {}

            # Download and extract each artifact
            all_artifact_contents = {}

            for artifact in artifacts:
                try:
                    # Download and extract artifact ZIP
                    artifact_contents = self._download_and_extract_zip(
                        artifact.archive_download_url
                    )

                    # Merge contents from this artifact
                    all_artifact_contents.update(artifact_contents)

                except (
                    Exception
                ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow exception type
                    logger.error(f"Failed to download artifact '{artifact.name}': {e}")
                    # Continue with other artifacts
                    continue

            return all_artifact_contents

        except (
            Exception
        ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow exception type
            logger.error(f"Error retrieving artifacts for run ID {run_id}: {e}")
            # Re-raise to let the decorator handle it
            raise
