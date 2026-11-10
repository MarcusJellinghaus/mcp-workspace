"""Tests for reference_name support in the GitHub write and label tools."""

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from github import GithubException

from mcp_workspace.github_operations.caching.errors import GitHubRateLimitError
from mcp_workspace.github_operations.issues.types import (
    CommentData,
    IssueData,
    create_empty_issue_data,
)
from mcp_workspace.reference_projects import ReferenceProject
from mcp_workspace.toolset._github_common import api_error
from mcp_workspace.utils.repo_identifier import RepoIdentifier
from tests.conftest import ToolMap
from tests.github_operations.conftest import make_retry_error

# Two reference projects with paths that do not exist: a GitHub call must
# resolve through the configured URL and never touch (or clone) a working tree.
_REFERENCE_PROJECTS = {
    "sibling": ReferenceProject(
        name="sibling",
        path=Path("/does/not/exist"),
        url="https://github.com/owner/sibling",
    ),
    "nourl": ReferenceProject(name="nourl", path=Path("/does/not/exist/2"), url=None),
}


@pytest.fixture
def ref_tools(make_tools: Callable[..., ToolMap]) -> ToolMap:
    """Tools configured with the two reference projects."""
    return make_tools(reference_projects=_REFERENCE_PROJECTS)


def _make_comment(
    comment_id: int = 1, author_association: str | None = "OWNER"
) -> CommentData:
    """Build a CommentData; ``comment_id=0`` is the empty-comment sentinel."""
    return CommentData(
        id=comment_id,
        body="hi",
        user="octocat",
        created_at="2024-01-01T00:00:00",
        updated_at=None,
        url="https://github.com/owner/sibling/issues/42#issuecomment-1",
        author_association=author_association,
    )


def _make_issue() -> IssueData:
    """Build a created-issue IssueData with a non-zero number."""
    return IssueData(
        number=42,
        title="T",
        body="",
        state="open",
        labels=[],
        assignees=[],
        user="octocat",
        created_at="2024-01-01T00:00:00",
        updated_at=None,
        url="https://github.com/owner/sibling/issues/42",
        locked=False,
        author_association="OWNER",
    )


def _make_manager() -> MagicMock:
    """Create a mock IssueManager that satisfies the covered tools."""
    mock_mgr = MagicMock()
    # A real identifier: a MagicMock cache_safe_name is no valid label-cache file name
    mock_mgr.repo_identifier = RepoIdentifier("owner", "repo")
    mock_mgr.get_available_labels.return_value = [
        {
            "name": "bug",
            "color": "d73a4a",
            "description": "Something isn't working",
            "url": "https://api.github.com/repos/owner/sibling/labels/bug",
        }
    ]
    # Real TypedDicts, not MagicMocks: comment["id"] and issue["number"] must be
    # genuinely truthy rather than opaquely truthy.
    mock_mgr.add_comment.return_value = _make_comment()
    mock_mgr.create_issue.return_value = _make_issue()
    mock_mgr.edit_issue.return_value = _make_issue()
    mock_mgr.get_issue.return_value = _make_issue()
    mock_mgr.github_token = "test-token"
    # pylint: disable-next=protected-access
    mock_mgr._github_client.get_user.return_value.login = "octocat"
    return mock_mgr


_TOOL_CASES: list[tuple[str, dict[str, Any]]] = [
    ("github_label_list", {}),
    ("github_issue_comment", {"number": 42, "body": "hi"}),
    ("github_issue_create", {"title": "T"}),
    ("github_issue_edit", {"number": 42, "title": "T"}),
    ("github_issue_set_status", {"number": 42, "status": "status-01:created"}),
    ("github_subissue_add", {"parent_number": 42, "child_number": 43}),
    ("github_subissue_list", {"parent_number": 42}),
    ("github_subissue_remove", {"parent_number": 42, "child_number": 43}),
]
_TOOL_IDS = [
    "label_list",
    "issue_comment",
    "issue_create",
    "issue_edit",
    "issue_set_status",
    "subissue_add",
    "subissue_list",
    "subissue_remove",
]


@pytest.mark.parametrize(("tool", "kwargs"), _TOOL_CASES, ids=_TOOL_IDS)
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_reference_name_uses_repo_url(
    mock_manager_cls: MagicMock,
    tool: str,
    kwargs: dict[str, Any],
    ref_tools: ToolMap,
) -> None:
    """The tools construct IssueManager with the reference project's URL."""
    mock_manager_cls.return_value = _make_manager()

    ref_tools[tool](**kwargs, reference_name="sibling")

    assert mock_manager_cls.call_args.kwargs == {
        "repo_url": "https://github.com/owner/sibling"
    }


@pytest.mark.parametrize(("tool", "kwargs"), _TOOL_CASES, ids=_TOOL_IDS)
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_no_reference_name_uses_project_dir(
    mock_manager_cls: MagicMock,
    tool: str,
    kwargs: dict[str, Any],
    project_dir: Path,
    ref_tools: ToolMap,
) -> None:
    """Without reference_name the workspace project_dir is used, unchanged."""
    mock_manager_cls.return_value = _make_manager()

    ref_tools[tool](**kwargs)

    assert mock_manager_cls.call_args.kwargs == {"project_dir": project_dir}


@pytest.mark.parametrize(("tool", "kwargs"), _TOOL_CASES, ids=_TOOL_IDS)
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_unknown_reference_name_returns_error(
    mock_manager_cls: MagicMock,
    tool: str,
    kwargs: dict[str, Any],
    ref_tools: ToolMap,
) -> None:
    """An unknown reference name is returned as an error string, not raised."""
    result = ref_tools[tool](**kwargs, reference_name="nope")

    assert result == "Error: Reference project 'nope' not found"
    mock_manager_cls.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_reference_project_without_url_returns_error(
    mock_manager_cls: MagicMock,
    ref_tools: ToolMap,
) -> None:
    """A reference project with no configured URL yields an error string."""
    result = ref_tools["github_label_list"](reference_name="nourl")

    assert result == "Error: Reference project 'nourl' has no URL configured"
    mock_manager_cls.assert_not_called()


@patch("mcp_workspace.toolset.reference.ensure_available")
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_reference_access_does_not_clone(
    mock_manager_cls: MagicMock,
    mock_ensure_available: MagicMock,
    ref_tools: ToolMap,
) -> None:
    """Targeting a reference project never clones its working tree."""
    mock_manager_cls.return_value = _make_manager()

    ref_tools["github_label_list"](reference_name="sibling")

    mock_ensure_available.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_no_labels_names_reference_project(
    mock_manager_cls: MagicMock,
    ref_tools: ToolMap,
) -> None:
    """An empty cross-repo label set says which repository was queried."""
    mock_mgr = _make_manager()
    mock_mgr.get_available_labels.return_value = []
    mock_manager_cls.return_value = mock_mgr

    result = ref_tools["github_label_list"](reference_name="sibling")

    body, footer = result.rsplit("\n", 1)
    assert body == "No labels found in reference project 'sibling'."
    assert footer.startswith("Label cache last updated ")


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_label_list_rate_limit_names_bucket(
    mock_manager_cls: MagicMock,
    ref_tools: ToolMap,
) -> None:
    """A rate-limited read tool reply names the exhausted bucket."""
    mock_mgr = _make_manager()
    mock_mgr.get_available_labels.side_effect = GithubException(
        403,
        {"message": "API rate limit exceeded"},
        {
            "x-ratelimit-remaining": "0",
            "x-ratelimit-resource": "core",
            "x-ratelimit-reset": str(int(time.time()) + 600),
        },
    )
    mock_manager_cls.return_value = mock_mgr

    result = ref_tools["github_label_list"](reference_name="sibling")

    assert "`core`" in result
    assert not result.startswith("Error:")


def test_api_error_renders_cache_rate_limit_with_suffix() -> None:
    """A GitHubRateLimitError renders as its bare message plus the suffix."""
    exc = GitHubRateLimitError("GitHub rate limit: `core` exhausted")

    result = api_error(exc, "sibling")

    assert result == (
        "GitHub rate limit: `core` exhausted in reference project 'sibling'"
    )


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_subissue_rate_limit_names_reference_project(
    mock_manager_cls: MagicMock,
    ref_tools: ToolMap,
) -> None:
    """A rate limit through api_error keeps the reference-project suffix."""
    mock_mgr = _make_manager()
    mock_mgr.list_sub_issues.side_effect = make_retry_error(403)
    mock_manager_cls.return_value = mock_mgr

    result = ref_tools["github_subissue_list"](
        parent_number=42, reference_name="sibling"
    )

    assert result == (
        "GitHub rate limit: retries exhausted in reference project 'sibling'"
    )


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_comment_failure_names_reference_project(
    mock_manager_cls: MagicMock,
    ref_tools: ToolMap,
) -> None:
    """A failed cross-repo comment says which reference project it targeted."""
    mock_mgr = _make_manager()
    mock_mgr.add_comment.return_value = _make_comment(comment_id=0)
    mock_manager_cls.return_value = mock_mgr

    result = ref_tools["github_issue_comment"](
        number=42, body="hi", reference_name="sibling"
    )

    assert result == (
        "Error: failed to add comment to issue #42 in reference project 'sibling'"
    )


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_comment_failure_without_reference_is_unchanged(
    mock_manager_cls: MagicMock,
    ref_tools: ToolMap,
) -> None:
    """The workspace failure message stays byte-identical to today's."""
    mock_mgr = _make_manager()
    mock_mgr.add_comment.return_value = _make_comment(comment_id=0)
    mock_manager_cls.return_value = mock_mgr

    result = ref_tools["github_issue_comment"](number=42, body="hi")

    assert result == "Error: failed to add comment to issue #42"


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_status_guard_points_at_set_status_tool(
    mock_manager_cls: MagicMock,
    ref_tools: ToolMap,
) -> None:
    """The status-* guard points at github_issue_set_status and writes nothing."""
    mock_mgr = _make_manager()
    mock_manager_cls.return_value = mock_mgr

    result = ref_tools["github_issue_create"](
        title="T", labels=["status-01:created"], reference_name="sibling"
    )

    assert result == (
        "Error: these tools do not modify status-* labels "
        "(status-01:created). Use github_issue_set_status"
    )
    mock_mgr.get_available_labels.assert_not_called()
    mock_mgr.create_issue.assert_not_called()


@pytest.mark.parametrize(
    ("labels", "expected"),
    [
        (["bugg"], "Error: unknown label(s) in reference project 'sibling': bugg"),
        (
            ["bugg", "bugz"],
            "Error: unknown label(s) in reference project 'sibling': bugg, bugz",
        ),
    ],
    ids=["one", "two"],
)
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_unknown_label_names_reference_project(
    mock_manager_cls: MagicMock,
    labels: list[str],
    expected: str,
    ref_tools: ToolMap,
) -> None:
    """Unknown labels name the reference project before the label list.

    The two-label case is the point: with the suffix ahead of the colon the
    list stays terminal, so 'sibling' cannot be misread as a third label.
    """
    mock_manager_cls.return_value = _make_manager()

    result = ref_tools["github_issue_create"](
        title="T", labels=labels, reference_name="sibling"
    )

    assert result == expected


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_create_failure_names_reference_project(
    mock_manager_cls: MagicMock,
    ref_tools: ToolMap,
) -> None:
    """A swallowed cross-repo creation failure names the target project."""
    mock_mgr = _make_manager()
    mock_mgr.create_issue.return_value = create_empty_issue_data()
    mock_manager_cls.return_value = mock_mgr

    result = ref_tools["github_issue_create"](title="T", reference_name="sibling")

    assert result == (
        "Error: issue creation failed - no issue was created "
        "in reference project 'sibling'"
    )


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_edit_status_guard_points_at_set_status_tool(
    mock_manager_cls: MagicMock,
    ref_tools: ToolMap,
) -> None:
    """The edit-side status-* guard points at github_issue_set_status."""
    mock_mgr = _make_manager()
    mock_manager_cls.return_value = mock_mgr

    result = ref_tools["github_issue_edit"](
        number=42, add_labels=["status-04:in-progress"], reference_name="sibling"
    )

    assert result == (
        "Error: these tools do not modify status-* labels "
        "(status-04:in-progress). Use github_issue_set_status"
    )
    mock_mgr.edit_issue.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_edit_invalid_number_does_not_resolve_reference(
    mock_manager_cls: MagicMock,
    ref_tools: ToolMap,
) -> None:
    """Argument validation runs before the reference project is resolved."""
    result = ref_tools["github_issue_edit"](number=0, reference_name="nope")

    assert result == "Error: invalid issue number: 0"
    mock_manager_cls.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_edit_not_found_names_reference_project(
    mock_manager_cls: MagicMock,
    ref_tools: ToolMap,
) -> None:
    """The nothing-was-written sentinel names the target project.

    It carries no URL, and a wrong-but-valid reference_name pointing at a
    repository without that issue number is its most likely cause.
    """
    mock_mgr = _make_manager()
    mock_mgr.edit_issue.return_value = create_empty_issue_data()
    mock_mgr.get_issue.return_value = create_empty_issue_data()
    mock_manager_cls.return_value = mock_mgr

    result = ref_tools["github_issue_edit"](
        number=42, title="T", reference_name="sibling"
    )

    assert result == (
        "Error: issue #42 not found or not accessible in reference project "
        "'sibling' (swallowed API error) - no changes were made"
    )


def _recording_edit(*_args: Any, **kwargs: Any) -> IssueData:
    """Log one issued write, then return the swallowed-failure sentinel."""
    kwargs["attempted_writes"].append("scalars")
    return create_empty_issue_data()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_edit_indeterminate_names_reference_project(
    mock_manager_cls: MagicMock,
    ref_tools: ToolMap,
) -> None:
    """The may-or-may-not-have-landed sentinel names the target project.

    A write went out and the refetch failed, so this message carries no URL
    either — cross-repo it is the only hint which repository was written to.
    """
    mock_mgr = _make_manager()
    mock_mgr.edit_issue.side_effect = _recording_edit
    mock_mgr.get_issue.return_value = create_empty_issue_data()
    mock_manager_cls.return_value = mock_mgr

    result = ref_tools["github_issue_edit"](
        number=42, title="T", reference_name="sibling"
    )

    assert result == (
        "Error: edit of issue #42 failed in reference project 'sibling' "
        "(swallowed API error) and the issue could not be re-read - these "
        "changes may or may not have been applied: scalars"
    )


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_edit_indeterminate_without_reference_is_unchanged(
    mock_manager_cls: MagicMock,
    ref_tools: ToolMap,
) -> None:
    """The workspace variant of that sentinel stays byte-identical to today's."""
    mock_mgr = _make_manager()
    mock_mgr.edit_issue.side_effect = _recording_edit
    mock_mgr.get_issue.return_value = create_empty_issue_data()
    mock_manager_cls.return_value = mock_mgr

    result = ref_tools["github_issue_edit"](number=42, title="T")

    assert result == (
        "Error: edit of issue #42 failed (swallowed API error) and the issue "
        "could not be re-read - these changes may or may not have been "
        "applied: scalars"
    )


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_edit_not_found_without_reference_is_unchanged(
    mock_manager_cls: MagicMock,
    ref_tools: ToolMap,
) -> None:
    """The workspace sentinel stays byte-identical to today's."""
    mock_mgr = _make_manager()
    mock_mgr.edit_issue.return_value = create_empty_issue_data()
    mock_mgr.get_issue.return_value = create_empty_issue_data()
    mock_manager_cls.return_value = mock_mgr

    result = ref_tools["github_issue_edit"](number=42, title="T")

    assert result == (
        "Error: issue #42 not found or not accessible "
        "(swallowed API error) - no changes were made"
    )
