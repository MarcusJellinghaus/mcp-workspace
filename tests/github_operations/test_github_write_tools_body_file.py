"""Tests for the ``body_file`` parameter of the GitHub write MCP tools."""

from pathlib import Path
from typing import Callable, Generator
from unittest.mock import MagicMock, patch

import pytest

from mcp_workspace.github_operations import GithubException
from mcp_workspace.github_operations.issues.types import CommentData, IssueData
from mcp_workspace.server import (
    github_issue_comment,
    github_issue_create,
    github_issue_edit,
    github_pr_create,
    set_project_dir,
)

PR_MANAGER = "mcp_workspace.github_operations.pr_manager.PullRequestManager"
CURRENT_BRANCH = "mcp_workspace.git_operations.get_current_branch_name"


@pytest.fixture(autouse=True)
def setup_server(project_dir: Path) -> Generator[None, None, None]:
    """Setup the server with the project directory."""
    set_project_dir(project_dir)
    yield


def _make_issue(number: int = 42) -> IssueData:
    """Create an IssueData for testing."""
    return IssueData(
        number=number,
        title="Test issue",
        body="",
        state="open",
        labels=[],
        assignees=[],
        user="alice",
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-02T00:00:00",
        url="https://github.com/test/repo/issues/42",
        locked=False,
        author_association="OWNER",
    )


@pytest.fixture
def mock_issue_manager() -> Generator[MagicMock, None, None]:
    """Patch _issue_manager to return a mocked IssueManager."""
    mock_mgr = MagicMock()
    mock_mgr.create_issue.return_value = _make_issue()
    mock_mgr.get_available_labels.return_value = []
    with patch(
        "mcp_workspace.server._issue_manager", return_value=mock_mgr
    ) as mock_factory:
        yield mock_factory


def _sent_body(mock_factory: MagicMock) -> str:
    """Return the body passed to create_issue."""
    body: str = mock_factory.return_value.create_issue.call_args.kwargs["body"]
    return body


def test_create_body_file_sent_verbatim(
    project_dir: Path, mock_issue_manager: MagicMock
) -> None:
    """A large non-ASCII CRLF file is sent byte for byte."""
    line = "äöü → ✓ `code` ``more``\r\n"
    content = (line * (20_000 // len(line.encode("utf-8")) + 1)).encode("utf-8")
    assert len(content) >= 20_000
    (project_dir / "body.md").write_bytes(content)

    result = github_issue_create(title="Test issue", body_file="body.md")

    assert result.startswith("Created issue #42")
    sent = _sent_body(mock_issue_manager)
    assert sent == content.decode("utf-8")
    assert "\r\n" in sent


def test_create_body_file_drops_bom(
    project_dir: Path, mock_issue_manager: MagicMock
) -> None:
    """A leading UTF-8 BOM is not sent."""
    (project_dir / "body.md").write_bytes(b"\xef\xbb\xbfHello\r\n")

    result = github_issue_create(title="Test issue", body_file="body.md")

    assert result.startswith("Created issue #42")
    assert _sent_body(mock_issue_manager) == "Hello\r\n"


def test_create_body_and_body_file_conflict(
    project_dir: Path, mock_issue_manager: MagicMock
) -> None:
    """Passing both body and body_file is an error before any manager call."""
    (project_dir / "body.md").write_bytes(b"Hello")

    result = github_issue_create(title="Test issue", body="x", body_file="body.md")

    assert result.startswith("Error:")
    assert "body" in result and "body_file" in result
    mock_issue_manager.assert_not_called()


def _missing(project_dir: Path) -> str:
    return "missing.md"


def _outside(project_dir: Path) -> str:
    (project_dir.parent / "outside.md").write_bytes(b"outside")
    return "../outside.md"


def _gitignored(project_dir: Path) -> str:
    (project_dir / ".gitignore").write_bytes(b"*.log\n")
    (project_dir / "draft.log").write_bytes(b"draft")
    return "draft.log"


def _not_utf8(project_dir: Path) -> str:
    (project_dir / "bad.md").write_bytes(b"\xff\xfe\x00bad")
    return "bad.md"


def _directory(project_dir: Path) -> str:
    (project_dir / "subdir").mkdir()
    return "subdir"


@pytest.mark.parametrize(
    "make_path",
    [_missing, _outside, _gitignored, _not_utf8, _directory],
    ids=["missing", "outside", "gitignored", "not_utf8", "directory"],
)
def test_create_body_file_bad_path(
    project_dir: Path,
    mock_issue_manager: MagicMock,
    make_path: Callable[[Path], str],
) -> None:
    """An unusable body_file is an error before any manager call."""
    body_file = make_path(project_dir)

    result = github_issue_create(title="Test issue", body_file=body_file)

    assert result.startswith("Error:")
    mock_issue_manager.assert_not_called()


def test_create_body_file_malformed_base_branch(
    project_dir: Path, mock_issue_manager: MagicMock
) -> None:
    """The Base Branch check applies to the file text."""
    (project_dir / "body.md").write_bytes(b"### Base Branch\n\nline1\nline2\n")

    result = github_issue_create(title="Test issue", body_file="body.md")

    assert result.startswith("Error:")
    assert "line1" in result
    mock_issue_manager.return_value.create_issue.assert_not_called()


def test_create_inline_body_unchanged(mock_issue_manager: MagicMock) -> None:
    """Without body_file, the inline body is passed through unchanged."""
    result = github_issue_create(title="Test issue", body="Inline\r\nbody ")

    assert result.startswith("Created issue #42")
    assert _sent_body(mock_issue_manager) == "Inline\r\nbody "


@pytest.fixture
def mock_edit_manager(
    mock_issue_manager: MagicMock,
) -> Generator[MagicMock, None, None]:
    """Extend the mocked IssueManager so edit_issue succeeds."""
    mock_issue_manager.return_value.edit_issue.return_value = _make_issue()
    yield mock_issue_manager


def _edited_body(mock_factory: MagicMock) -> str:
    """Return the body passed to edit_issue."""
    body: str = mock_factory.return_value.edit_issue.call_args.kwargs["body"]
    return body


def test_edit_body_file_sent_verbatim(
    project_dir: Path, mock_edit_manager: MagicMock
) -> None:
    """A CRLF file is sent byte for byte and the edit reports success."""
    (project_dir / "body.md").write_bytes(b"Line one\r\nLine two\r\n")

    result = github_issue_edit(number=42, body_file="body.md")

    assert result.startswith("Updated issue #")
    assert "Error" not in result and "Warning" not in result
    assert _edited_body(mock_edit_manager) == "Line one\r\nLine two\r\n"


def test_edit_empty_body_and_body_file_conflict(
    project_dir: Path, mock_edit_manager: MagicMock
) -> None:
    """Even body="" conflicts with body_file on edit."""
    (project_dir / "body.md").write_bytes(b"Hello")

    result = github_issue_edit(number=42, body="", body_file="body.md")

    assert result.startswith("Error:")
    assert "body" in result and "body_file" in result
    mock_edit_manager.assert_not_called()


def test_edit_body_file_malformed_base_branch(
    project_dir: Path, mock_edit_manager: MagicMock
) -> None:
    """The Base Branch check applies to the file text."""
    (project_dir / "body.md").write_bytes(b"### Base Branch\n\nline1\nline2\n")

    result = github_issue_edit(number=42, body_file="body.md")

    assert result.startswith("Error:")
    assert "line1" in result
    mock_edit_manager.return_value.edit_issue.assert_not_called()


def test_edit_body_file_partial_failure_reports_body(
    project_dir: Path, mock_edit_manager: MagicMock
) -> None:
    """On partial failure, the file body is reported as applied."""
    text = "Line one\r\nLine two\r\n"
    (project_dir / "body.md").write_bytes(text.encode("utf-8"))

    def fail_after_body(*_args: object, **kwargs: object) -> IssueData:
        attempted = kwargs["attempted_writes"]
        assert isinstance(attempted, list)
        attempted.append("body")
        raise GithubException(500, {"message": "boom"}, None)

    mgr = mock_edit_manager.return_value
    mgr.edit_issue.side_effect = fail_after_body
    refetched = _make_issue()
    refetched["body"] = text
    mgr.get_issue.return_value = refetched

    result = github_issue_edit(number=42, body_file="body.md")

    assert "Applied: body" in result


def test_edit_empty_inline_body_unchanged(mock_edit_manager: MagicMock) -> None:
    """Without body_file, body="" still reaches edit_issue as ""."""
    result = github_issue_edit(number=42, body="")

    assert result.startswith("Updated issue #")
    assert _edited_body(mock_edit_manager) == ""


@pytest.fixture
def mock_comment_manager(
    mock_issue_manager: MagicMock,
) -> Generator[MagicMock, None, None]:
    """Extend the mocked IssueManager so add_comment succeeds."""
    mock_issue_manager.return_value.add_comment.return_value = CommentData(
        id=1,
        body="",
        user="alice",
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:00:00",
        url="https://github.com/test/repo/issues/42#issuecomment-1",
        author_association="OWNER",
    )
    yield mock_issue_manager


def test_comment_body_file_sent_verbatim(
    project_dir: Path, mock_comment_manager: MagicMock
) -> None:
    """A non-ASCII CRLF file reaches add_comment as its text."""
    text = "äöü → ✓\r\nzweite Zeile\r\n"
    (project_dir / "body.md").write_bytes(text.encode("utf-8"))

    result = github_issue_comment(number=42, body_file="body.md")

    assert result.startswith("Added comment to issue #42")
    mock_comment_manager.return_value.add_comment.assert_called_once_with(42, text)


def test_comment_body_and_body_file_conflict(
    project_dir: Path, mock_comment_manager: MagicMock
) -> None:
    """Passing both body and body_file is an error before any manager call."""
    (project_dir / "body.md").write_bytes(b"Hello")

    result = github_issue_comment(number=42, body="x", body_file="body.md")

    assert result.startswith("Error:")
    assert "body" in result and "body_file" in result
    mock_comment_manager.assert_not_called()


def test_comment_neither_body_nor_body_file(
    mock_comment_manager: MagicMock,
) -> None:
    """With no body source, the error wins over an invalid reference_name."""
    result = github_issue_comment(number=42, reference_name="no-such-ref")

    assert result == "Error: pass body or body_file"
    mock_comment_manager.assert_not_called()


@pytest.fixture
def mock_pr_manager() -> Generator[MagicMock, None, None]:
    """Patch PullRequestManager and the current-branch lookup."""
    with patch(PR_MANAGER) as mock_cls, patch(CURRENT_BRANCH, return_value="feature/x"):
        manager: MagicMock = mock_cls.return_value
        # pylint: disable-next=protected-access
        manager._validate_branch_name.return_value = True
        manager.create_pull_request.return_value = {
            "number": 7,
            "url": "https://github.com/test/repo/pull/7",
        }
        yield mock_cls


def test_pr_create_body_file_sent_verbatim(
    project_dir: Path, mock_pr_manager: MagicMock
) -> None:
    """A CRLF file reaches create_pull_request as its exact text."""
    text = "Summary\r\n\r\n- äöü → ✓\r\n"
    (project_dir / "body.md").write_bytes(text.encode("utf-8"))

    result = github_pr_create(
        title="T", head="feature/x", base="main", body_file="body.md"
    )

    assert result.startswith("Created PR #7")
    create = mock_pr_manager.return_value.create_pull_request
    assert create.call_args.kwargs["body"] == text


def test_pr_create_body_and_body_file_conflict(
    project_dir: Path, mock_pr_manager: MagicMock
) -> None:
    """Passing both body and body_file is an error before any manager call."""
    (project_dir / "body.md").write_bytes(b"Hello")

    result = github_pr_create(
        title="T", body="x", head="feature/x", base="main", body_file="body.md"
    )

    assert result.startswith("Error:")
    assert "body" in result and "body_file" in result
    mock_pr_manager.assert_not_called()


def test_pr_create_body_file_missing(mock_pr_manager: MagicMock) -> None:
    """A missing body_file is an error before any manager call."""
    result = github_pr_create(
        title="T", head="feature/x", base="main", body_file="missing.md"
    )

    assert result.startswith("Error:")
    mock_pr_manager.assert_not_called()
