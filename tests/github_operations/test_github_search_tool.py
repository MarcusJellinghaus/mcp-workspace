"""Tests for the github_search read-only MCP tool in server.py.

Covers handler wiring, result rendering and live searches. Query construction
and the validation messages live in ``test_search``, where SearchSpec is tested
without mocks; one validation case stays here as the ordering guard. The
result-capping and truncation-notice tests live in
``test_github_read_tools_pr_search``; the two modules stay separate because
merged they would exceed the file-size limit.
"""

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mcp_workspace.server import github_search, set_project_dir

from .search_helpers import FakeSearchResults

# setup_server lives in conftest.py; it is not autouse, so opt in here.
pytestmark = pytest.mark.usefixtures("setup_server")


@pytest.fixture
def live_repo_root() -> Path:
    """Point the server at this repository's own checkout for live searches.

    Re-points the server after `setup_server`, which sets a tmp_path with no
    git remote. Skips when no GitHub token is configured.
    """
    from mcp_workspace.config import get_github_token

    if not get_github_token():
        pytest.skip("GitHub token not configured (set GITHUB_TOKEN or config file)")

    repo_root = Path(__file__).parents[2]
    set_project_dir(repo_root)
    return repo_root


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_basic(mock_manager_cls: MagicMock) -> None:
    """Returns compact summary lines with auto-scoped repo."""
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    item1 = MagicMock()
    item1.number = 1
    item1.title = "Bug fix"
    item1.state = "open"
    item1.labels = []
    item1.pull_request = None

    item2 = MagicMock()
    item2.number = 2
    item2.title = "Feature PR"
    item2.state = "open"
    item2.labels = []
    item2.pull_request = MagicMock()  # truthy = is a PR

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo
    mock_mgr._github_client.search_issues.return_value = FakeSearchResults(
        [item1, item2]
    )

    result = github_search(query="fix")

    assert "#1" in result
    assert "Bug fix" in result
    assert "#2" in result
    assert "Feature PR" in result
    mock_mgr._github_client.search_issues.assert_called_once()
    call_args = mock_mgr._github_client.search_issues.call_args
    assert call_args[1]["query"] == "repo:owner/repo is:issue fix"


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_empty(mock_manager_cls: MagicMock) -> None:
    """Returns 'No results found.' for empty results."""
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo
    mock_mgr._github_client.search_issues.return_value = FakeSearchResults([])

    result = github_search(query="nonexistent")

    assert "No results found." in result


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_with_qualifiers(mock_manager_cls: MagicMock) -> None:
    """state/labels/assignee become query text; sort/order stay kwargs."""
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo
    mock_mgr._github_client.search_issues.return_value = FakeSearchResults([])

    github_search(
        query="bug",
        state="open",
        labels=["bug", "urgent"],
        assignee="alice",
        sort="created",
        order="desc",
    )

    call_kwargs = mock_mgr._github_client.search_issues.call_args[1]
    assert call_kwargs["query"] == (
        'repo:owner/repo is:issue bug is:open label:"bug" label:"urgent" '
        "assignee:alice"
    )
    assert "state" not in call_kwargs
    assert "labels" not in call_kwargs
    assert "assignee" not in call_kwargs
    assert call_kwargs.get("sort") == "created"
    assert call_kwargs.get("order") == "desc"


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_invalid_state(mock_manager_cls: MagicMock) -> None:
    """An unrecognised state fails loudly before any API call."""
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo

    result = github_search(query="bug", state="bogus")

    assert result == "Error: Invalid state: bogus. Expected 'open', 'closed' or 'all'."
    mock_mgr._github_client.search_issues.assert_not_called()
    # Validated before the repository lookup, so no network round-trip happens
    mock_mgr._get_repository.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_issue_vs_pr_indicator(mock_manager_cls: MagicMock) -> None:
    """Correct Issue/PR indicator in results."""
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    issue_item = MagicMock()
    issue_item.number = 1
    issue_item.title = "A bug"
    issue_item.state = "open"
    issue_item.labels = []
    issue_item.pull_request = None

    pr_item = MagicMock()
    pr_item.number = 2
    pr_item.title = "A PR"
    pr_item.state = "open"
    pr_item.labels = []
    pr_item.pull_request = MagicMock()

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo
    mock_mgr._github_client.search_issues.return_value = FakeSearchResults(
        [issue_item, pr_item]
    )

    result = github_search(query="test")

    result_lines = result.strip().split("\n")
    assert "[Issue]" in result_lines[0]
    assert "[PR]" in result_lines[1]


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_error(mock_manager_cls: MagicMock) -> None:
    """Returns 'Error: ...' on exception."""
    mock_manager_cls.side_effect = RuntimeError("API down")

    result = github_search(query="test")

    assert result == "Error: API down"


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_no_repo(mock_manager_cls: MagicMock) -> None:
    """Returns error when repository not accessible."""
    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = None
    mock_mgr._repo_identifier.api_base_url = "https://gitlab.com/api/v3"

    result = github_search(query="test")

    assert (
        result == "Error: Could not access repository (tried https://gitlab.com/api/v3)"
    )


@pytest.mark.github_integration
def test_github_search_live_label_and_state_filters(live_repo_root: Path) -> None:
    """Live: GitHub accepts and honors label: and is:open qualifiers."""
    from mcp_workspace.github_operations.issues import IssueManager

    repo_root = live_repo_root

    try:
        manager = IssueManager(project_dir=repo_root)
    except ValueError as exc:
        pytest.skip(f"Checkout is not a git repo with a GitHub origin: {exc}")

    # No max_results: we need the oldest issue, not the newest.
    issues = manager.list_issues(state="open")
    if not issues:
        # list_issues swallows API errors and returns [], so distinguish an
        # empty repository from an auth/permission failure.
        if manager._get_repository() is None:  # pylint: disable=protected-access
            pytest.fail("GitHub API unreachable or token lacks access to this repo")
        pytest.skip("Repository has no open issues")

    # Anchor on the oldest open issue carrying a non-"status-" label: those
    # labels are promoted by this repo's automation and GitHub's search index
    # lags label mutations. Sort explicitly rather than trusting list_issues'
    # ordering, so the anchor is the same issue on every run.
    anchor = None
    anchor_label = ""
    for issue in sorted(issues, key=lambda i: int(i["number"])):
        stable = [label for label in issue["labels"] if not label.startswith("status-")]
        if stable:
            anchor = issue
            anchor_label = stable[0]
            break

    if anchor is None:
        pytest.skip("No open issue carries a non-status label")

    # sort/order are URL parameters, not query text: oldest match first, so the
    # anchor cannot be pushed past the max_results cap.
    result = github_search(
        query="",
        state="open",
        labels=[anchor_label],
        sort="created",
        order="asc",
        max_results=100,
    )

    assert not result.startswith("Error:"), result
    assert result != "No results found."

    result_lines = [line for line in result.strip().split("\n") if line.startswith("#")]
    # startswith, not substring: anchor #12 would also match a line for #123.
    assert any(
        line.startswith(f"#{anchor['number']} ") for line in result_lines
    ), result
    for line in result_lines:
        assert "[open]" in line, line
        assert anchor_label in line, line

    # Second live call: free text plus qualifiers (the issue's repro 3 shape).
    # Split on non-letters, not whitespace: identifier-style titles such as
    # "read_py_file_just_headers" are one whitespace token but several words.
    anchor_word = max(
        re.findall(r"[A-Za-z]{4,}", anchor["title"]),
        key=len,
        default="",
    )
    if not anchor_word:
        pytest.skip("Anchor issue title has no distinctive word for a free-text search")

    text_result = github_search(
        query=anchor_word,
        state="open",
        labels=[anchor_label],
        sort="created",
        order="asc",
        max_results=100,
    )

    assert not text_result.startswith("Error:"), text_result

    text_lines = [
        line for line in text_result.strip().split("\n") if line.startswith("#")
    ]
    assert any(
        line.startswith(f"#{anchor['number']} ") for line in text_lines
    ), text_result


@pytest.mark.github_integration
@pytest.mark.parametrize(
    ("type_token", "indicator"),
    [
        ("is:pull-request", "[PR]"),
        ("is:pr", "[PR]"),
        ("type:pr", "[PR]"),
        ("type:issue", "[Issue]"),
    ],
)
def test_github_search_live_explicit_type_accepted(
    live_repo_root: Path, type_token: str, indicator: str
) -> None:
    """Live: every spelling that suppresses the default is accepted by GitHub.

    The suppression regex trusts these tokens without adding is:issue, so a
    spelling GitHub rejects would 422 at runtime rather than in a test - which
    is the failure mode issue #254 is about. GitHub's own gate message names
    only the is: forms, so the type: forms need live proof, not an assumption.
    """
    result = github_search(query=type_token, sort="created", order="desc")

    assert not result.startswith("Error:"), result
    assert result != "No results found.", f"{type_token} matched nothing"

    result_lines = [line for line in result.strip().split("\n") if line.startswith("#")]
    assert result_lines, result
    for line in result_lines:
        assert indicator in line, line


@pytest.mark.github_integration
@pytest.mark.parametrize(
    ("state_token", "indicator"),
    [
        ("is:open", "[open]"),
        ("is:closed", "[closed]"),
        ("state:open", "[open]"),
        ("state:closed", "[closed]"),
    ],
)
def test_github_search_live_state_spelling_honored(
    live_repo_root: Path, state_token: str, indicator: str
) -> None:
    """Live: every spelling the suppression regex trusts really filters state.

    An inline state token suppresses the `state` parameter's own `is:` token,
    so a spelling GitHub silently ignores would drop state filtering entirely -
    the failure mode issue #254 is about. A mocked test can only prove we sent
    the token, never that GitHub honored it.
    """
    result = github_search(
        query=f"is:issue {state_token}", sort="created", order="desc"
    )

    assert not result.startswith("Error:"), result
    assert result != "No results found.", f"{state_token} matched nothing"

    result_lines = [line for line in result.strip().split("\n") if line.startswith("#")]
    assert result_lines, result
    for line in result_lines:
        assert indicator in line, line
