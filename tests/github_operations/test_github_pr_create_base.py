"""Tests for how ``github_pr_create`` resolves an omitted ``base``.

An omitted base is resolved for ``head`` via ``_resolve_base_branch`` and
verified on origin; every failure is an ``Error:`` string and no PR is created.
"""

from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from git.exc import GitCommandError

from mcp_workspace.server import github_pr_create, set_project_dir

RESOLVE = "mcp_workspace.server._resolve_base_branch"
ORIGIN_HAS_BRANCH = "mcp_workspace.git_operations.base_branch.origin_has_branch"
CURRENT_BRANCH = "mcp_workspace.git_operations.get_current_branch_name"
PR_MANAGER = "mcp_workspace.github_operations.pr_manager.PullRequestManager"


@pytest.fixture(autouse=True)
def setup_server(project_dir: Path) -> Generator[None, None, None]:
    """Setup the server with the project directory."""
    set_project_dir(project_dir)
    yield


@pytest.fixture(name="manager")
def fixture_manager() -> Generator[MagicMock, None, None]:
    """Patch PullRequestManager; branch names pass and creation succeeds."""
    with patch(PR_MANAGER) as mock_cls:
        manager: MagicMock = mock_cls.return_value
        # pylint: disable-next=protected-access
        manager._validate_branch_name.return_value = True
        manager.create_pull_request.return_value = {
            "number": 7,
            "url": "https://github.com/test/repo/pull/7",
        }
        yield manager


@pytest.fixture(name="current")
def fixture_current() -> Generator[MagicMock, None, None]:
    """Patch the current-branch lookup to ``feature/x``."""
    with patch(CURRENT_BRANCH, return_value="feature/x") as mock_current:
        yield mock_current


class TestGithubPrCreateBase:
    """Default-base resolution in ``github_pr_create``."""

    def test_explicit_head_is_resolved(
        self, manager: MagicMock, current: MagicMock
    ) -> None:
        """An explicit head, not the current branch, is what gets resolved."""
        with (
            patch(RESOLVE, return_value=("epic/x", None)) as mock_resolve,
            patch(ORIGIN_HAS_BRANCH, return_value=True),
        ):
            github_pr_create(title="T", head="feature/y")

        current.assert_not_called()
        mock_resolve.assert_called_once()
        assert mock_resolve.call_args.args[1] == "feature/y"
        assert mock_resolve.call_args.args[2] is manager

    def test_malformed_issue_returns_error(
        self, manager: MagicMock, current: MagicMock
    ) -> None:
        """A malformed Base Branch section is returned as-is; nothing created."""
        error = "Error: issue #42: Base Branch section has more than one branch name."
        with (
            patch(RESOLVE, return_value=(None, error)),
            patch(ORIGIN_HAS_BRANCH) as mock_origin,
        ):
            result = github_pr_create(title="T")

        assert result == error
        mock_origin.assert_not_called()
        manager.create_pull_request.assert_not_called()

    def test_undetermined_base_returns_error(
        self, manager: MagicMock, current: MagicMock
    ) -> None:
        """No detected base errors instead of guessing; nothing created."""
        with (
            patch(RESOLVE, return_value=(None, None)),
            patch(ORIGIN_HAS_BRANCH) as mock_origin,
        ):
            result = github_pr_create(title="T")

        assert result == "Error: could not determine base branch for feature/x"
        mock_origin.assert_not_called()
        manager.create_pull_request.assert_not_called()

    def test_base_missing_on_origin_returns_error(
        self, manager: MagicMock, current: MagicMock, project_dir: Path
    ) -> None:
        """A resolved base absent from origin errors; nothing created."""
        with (
            patch(RESOLVE, return_value=("epic/x", None)),
            patch(ORIGIN_HAS_BRANCH, return_value=False) as mock_origin,
        ):
            result = github_pr_create(title="T")

        assert result == "Error: base branch 'epic/x' not found on origin"
        mock_origin.assert_called_once_with(project_dir, "epic/x")
        manager.create_pull_request.assert_not_called()

    @pytest.mark.parametrize(
        "exc",
        [
            GitCommandError("ls-remote", 128, stderr="boom"),
            RuntimeError("boom"),
        ],
    )
    def test_origin_check_failure_returns_error(
        self, manager: MagicMock, current: MagicMock, exc: Exception
    ) -> None:
        """A failed origin check errors with the cause; nothing created."""
        with (
            patch(RESOLVE, return_value=("epic/x", None)),
            patch(ORIGIN_HAS_BRANCH, side_effect=exc),
        ):
            result = github_pr_create(title="T")

        assert result.startswith(
            "Error: could not verify base branch 'epic/x' on origin: "
        )
        assert "boom" in result
        manager.create_pull_request.assert_not_called()

    def test_resolved_base_on_origin_creates_pr(
        self, manager: MagicMock, current: MagicMock
    ) -> None:
        """A resolved base present on origin is used for the PR."""
        with (
            patch(RESOLVE, return_value=("epic/x", None)),
            patch(ORIGIN_HAS_BRANCH, return_value=True),
        ):
            result = github_pr_create(title="T")

        assert result == "Created PR #7 — https://github.com/test/repo/pull/7"
        manager.create_pull_request.assert_called_once_with(
            title="T", head_branch="feature/x", base_branch="epic/x", body=""
        )

    def test_explicit_base_skips_resolution_and_origin_check(
        self, manager: MagicMock, current: MagicMock
    ) -> None:
        """An explicit base is used unchanged, with no lookup at all."""
        with (
            patch(RESOLVE) as mock_resolve,
            patch(ORIGIN_HAS_BRANCH) as mock_origin,
        ):
            result = github_pr_create(title="T", base="develop")

        assert result.startswith("Created PR #7")
        mock_resolve.assert_not_called()
        mock_origin.assert_not_called()
        assert manager.create_pull_request.call_args.kwargs["base_branch"] == "develop"
