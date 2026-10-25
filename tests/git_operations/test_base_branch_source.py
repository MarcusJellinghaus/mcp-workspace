"""Tests for detect_base_branch_with_source and BaseBranchSource."""

from pathlib import Path
from typing import Iterator, Optional
from unittest.mock import MagicMock, patch

import pytest

from mcp_workspace.git_operations.base_branch import (
    BaseBranchSource,
    _fetch_issue_data,
    detect_base_branch,
    detect_base_branch_with_source,
)
from mcp_workspace.github_operations.issues.types import IssueData

_MODULE = "mcp_workspace.git_operations.base_branch"


def _issue(
    number: int = 123,
    base_branch: Optional[str] = None,
    base_branch_error: Optional[str] = None,
) -> IssueData:
    """Build IssueData with optional base branch fields."""
    data = IssueData(
        number=number,
        title="test",
        body="",
        state="open",
        labels=[],
        assignees=[],
        user=None,
        created_at=None,
        updated_at=None,
        url="",
        locked=False,
        author_association="OWNER",
    )
    if base_branch is not None:
        data["base_branch"] = base_branch
    if base_branch_error is not None:
        data["base_branch_error"] = base_branch_error
    return data


def _pr_manager(base: Optional[str]) -> MagicMock:
    """Build a PR manager mock returning one PR with ``base`` (or none)."""
    manager = MagicMock()
    manager.find_pull_request_by_head.return_value = (
        [{"base_branch": base, "number": 7}] if base else []
    )
    return manager


@pytest.fixture(name="git_mocks")
def _git_mocks() -> Iterator[dict[str, MagicMock]]:
    """Patch git queries used by detection; merge-base and default fail by default."""
    with (
        patch(f"{_MODULE}.get_current_branch_name") as current,
        patch(f"{_MODULE}.detect_parent_branch_via_merge_base") as merge_base,
        patch(f"{_MODULE}.get_default_branch_name") as default,
        patch(f"{_MODULE}.remote_branch_exists") as remote_exists,
    ):
        current.return_value = "123-feature"
        merge_base.return_value = None
        default.return_value = None
        remote_exists.return_value = False
        yield {
            "current": current,
            "merge_base": merge_base,
            "default": default,
        }


class TestDetectBaseBranchWithSource:
    """Each detection source is tagged correctly."""

    def test_issue_source(self, git_mocks: dict[str, MagicMock]) -> None:
        """Issue data with base_branch → ISSUE."""
        result = detect_base_branch_with_source(
            Path("/repo"), issue_data=_issue(base_branch="develop")
        )
        assert result == ("develop", BaseBranchSource.ISSUE)
        git_mocks["merge_base"].assert_not_called()

    def test_pr_source(self, git_mocks: dict[str, MagicMock]) -> None:
        """Open PR base → PR."""
        result = detect_base_branch_with_source(
            Path("/repo"), pr_manager=_pr_manager("from-pr")
        )
        assert result == ("from-pr", BaseBranchSource.PR)
        git_mocks["merge_base"].assert_not_called()

    def test_merge_base_source(self, git_mocks: dict[str, MagicMock]) -> None:
        """Merge-base winner → MERGE_BASE."""
        git_mocks["merge_base"].return_value = "develop"
        result = detect_base_branch_with_source(Path("/repo"))
        assert result == ("develop", BaseBranchSource.MERGE_BASE)

    def test_default_source(self, git_mocks: dict[str, MagicMock]) -> None:
        """Default branch fallback → DEFAULT."""
        git_mocks["default"].return_value = "main"
        result = detect_base_branch_with_source(Path("/repo"))
        assert result == ("main", BaseBranchSource.DEFAULT)

    def test_all_fail_returns_none(self, git_mocks: dict[str, MagicMock]) -> None:
        """Nothing detected → None."""
        assert detect_base_branch_with_source(Path("/repo")) is None

    def test_detached_head_returns_none(self, git_mocks: dict[str, MagicMock]) -> None:
        """No current branch → None."""
        git_mocks["current"].return_value = None
        git_mocks["default"].return_value = "main"
        assert detect_base_branch_with_source(Path("/repo")) is None

    def test_enum_values(self) -> None:
        """Enum values match the documented strings."""
        assert [s.value for s in BaseBranchSource] == [
            "issue",
            "pr",
            "merge_base",
            "default",
        ]


class TestIssueManager:
    """Fetching issue data through an issue_manager."""

    def test_fetches_issue_from_branch_number(
        self, git_mocks: dict[str, MagicMock]
    ) -> None:
        """Branch 123-x → get_issue(123) → ISSUE."""
        manager = MagicMock()
        manager.get_issue.return_value = _issue(base_branch="develop")
        result = detect_base_branch_with_source(
            Path("/repo"), current_branch="123-x", issue_manager=manager
        )
        assert result == ("develop", BaseBranchSource.ISSUE)
        manager.get_issue.assert_called_once_with(123)

    def test_base_branch_error_falls_through(
        self, git_mocks: dict[str, MagicMock]
    ) -> None:
        """Issue with base_branch_error is not trusted → next source."""
        manager = MagicMock()
        manager.get_issue.return_value = _issue(
            base_branch="develop", base_branch_error="malformed"
        )
        result = detect_base_branch_with_source(
            Path("/repo"),
            current_branch="123-x",
            pr_manager=_pr_manager("from-pr"),
            issue_manager=manager,
        )
        assert result == ("from-pr", BaseBranchSource.PR)

    def test_branch_without_number_skips_fetch(
        self, git_mocks: dict[str, MagicMock]
    ) -> None:
        """No issue number in branch → get_issue not called."""
        manager = MagicMock()
        result = detect_base_branch_with_source(
            Path("/repo"),
            current_branch="feature-x",
            pr_manager=_pr_manager("from-pr"),
            issue_manager=manager,
        )
        assert result == ("from-pr", BaseBranchSource.PR)
        manager.get_issue.assert_not_called()

    def test_get_issue_raises_falls_through(
        self, git_mocks: dict[str, MagicMock]
    ) -> None:
        """get_issue raising → next source."""
        manager = MagicMock()
        manager.get_issue.side_effect = RuntimeError("boom")
        result = detect_base_branch_with_source(
            Path("/repo"),
            current_branch="123-x",
            pr_manager=_pr_manager("from-pr"),
            issue_manager=manager,
        )
        assert result == ("from-pr", BaseBranchSource.PR)

    def test_empty_issue_falls_through(self, git_mocks: dict[str, MagicMock]) -> None:
        """get_issue returning number=0 (manager's empty value) → next source."""
        manager = MagicMock()
        manager.get_issue.return_value = _issue(number=0, base_branch="develop")
        result = detect_base_branch_with_source(
            Path("/repo"),
            current_branch="123-x",
            pr_manager=_pr_manager("from-pr"),
            issue_manager=manager,
        )
        assert result == ("from-pr", BaseBranchSource.PR)

    def test_issue_data_given_skips_fetch(
        self, git_mocks: dict[str, MagicMock]
    ) -> None:
        """issue_data without base_branch plus issue_manager → no fetch."""
        manager = MagicMock()
        result = detect_base_branch_with_source(
            Path("/repo"),
            current_branch="123-x",
            issue_data=_issue(),
            pr_manager=_pr_manager("from-pr"),
            issue_manager=manager,
        )
        assert result == ("from-pr", BaseBranchSource.PR)
        manager.get_issue.assert_not_called()

    def test_fetch_issue_data_returns_issue(self) -> None:
        """_fetch_issue_data returns the trusted issue."""
        manager = MagicMock()
        issue = _issue(base_branch="develop")
        manager.get_issue.return_value = issue
        assert _fetch_issue_data(manager, "123-x") is issue


class TestDetectBaseBranchWrapper:
    """detect_base_branch returns only the name."""

    def test_returns_name_only(self, git_mocks: dict[str, MagicMock]) -> None:
        """Wrapper strips the source."""
        git_mocks["default"].return_value = "main"
        assert detect_base_branch(Path("/repo")) == "main"

    def test_returns_none_when_all_fail(self, git_mocks: dict[str, MagicMock]) -> None:
        """Wrapper passes through None."""
        assert detect_base_branch(Path("/repo")) is None

    def test_wrapper_uses_issue_manager(self, git_mocks: dict[str, MagicMock]) -> None:
        """Wrapper forwards issue_manager."""
        manager = MagicMock()
        manager.get_issue.return_value = _issue(base_branch="develop")
        assert (
            detect_base_branch(
                Path("/repo"), current_branch="123-x", issue_manager=manager
            )
            == "develop"
        )
