"""Tests for the github_search read-only MCP tool in server.py.

Covers query construction and validation. The result-capping and
truncation-notice tests live in ``test_github_read_tools_pr_search``; the two
modules stay separate because merged they would exceed the file-size limit.
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
def test_github_search_multiple_labels(mock_manager_cls: MagicMock) -> None:
    """Each label emits its own label: qualifier, never a comma-joined labels:."""
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo
    mock_mgr._github_client.search_issues.return_value = FakeSearchResults([])

    github_search(query="bug", labels=["bug", "urgent"])

    call_kwargs = mock_mgr._github_client.search_issues.call_args[1]
    assert (
        call_kwargs["query"]
        == 'repo:owner/repo is:issue bug label:"bug" label:"urgent"'
    )
    # Regression marker for #254: the old comma-joined form must never return.
    assert "labels:bug,urgent" not in call_kwargs["query"]


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_label_with_special_characters(
    mock_manager_cls: MagicMock,
) -> None:
    """Labels are always quoted, so colons in a label name survive intact."""
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo
    mock_mgr._github_client.search_issues.return_value = FakeSearchResults([])

    github_search(query="x", labels=["status-01:created"])

    call_kwargs = mock_mgr._github_client.search_issues.call_args[1]
    assert (
        call_kwargs["query"] == 'repo:owner/repo is:issue x label:"status-01:created"'
    )


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_label_with_embedded_quote(mock_manager_cls: MagicMock) -> None:
    """A quote inside a label is rejected - GitHub has no escape for it."""
    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr

    result = github_search(query="x", labels=["bug", 'needs "review"'])

    assert result == (
        "Error: Invalid label 'needs \"review\"': "
        "a label containing a double quote cannot be searched"
    )
    mock_mgr._github_client.search_issues.assert_not_called()
    mock_mgr._get_repository.assert_not_called()


@pytest.mark.parametrize("label", ["", "   ", "\t"])
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_label_empty_or_blank(
    mock_manager_cls: MagicMock, label: str
) -> None:
    """A blank label would go out as label:"" and match nothing silently."""
    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr

    result = github_search(query="x", labels=["bug", label])

    assert result == (
        f"Error: Invalid label {label!r}: a label cannot be empty or whitespace-only"
    )
    mock_mgr._github_client.search_issues.assert_not_called()
    mock_mgr._get_repository.assert_not_called()


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_state_emits_is_qualifier(mock_manager_cls: MagicMock) -> None:
    """state="closed" emits is:closed; an omitted state adds nothing."""
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo
    mock_mgr._github_client.search_issues.return_value = FakeSearchResults([])

    github_search(query="bug", state="closed")

    call_kwargs = mock_mgr._github_client.search_issues.call_args[1]
    assert call_kwargs["query"] == "repo:owner/repo is:issue bug is:closed"
    assert "state:" not in call_kwargs["query"]

    mock_mgr._github_client.search_issues.reset_mock()

    github_search(query="bug")

    call_kwargs = mock_mgr._github_client.search_issues.call_args[1]
    assert call_kwargs["query"] == "repo:owner/repo is:issue bug"


@pytest.mark.parametrize(
    "query",
    ["bug is:closed", "bug state:closed", "bug IS:CLOSED", "is:open bug"],
)
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_inline_state_suppresses_state_param(
    mock_manager_cls: MagicMock, query: str
) -> None:
    """An inline state qualifier wins - two state tokens would match nothing."""
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo
    mock_mgr._github_client.search_issues.return_value = FakeSearchResults([])

    github_search(query=query, state="open")

    call_kwargs = mock_mgr._github_client.search_issues.call_args[1]
    assert call_kwargs["query"] == f"repo:owner/repo is:issue {query}"


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_qualifiers_only(mock_manager_cls: MagicMock) -> None:
    """An empty query yields qualifiers only - no double or trailing space."""
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo
    mock_mgr._github_client.search_issues.return_value = FakeSearchResults([])

    github_search(query="", state="open", labels=["bug"])

    call_kwargs = mock_mgr._github_client.search_issues.call_args[1]
    assert call_kwargs["query"] == 'repo:owner/repo is:issue is:open label:"bug"'


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_state_all_emits_no_token(mock_manager_cls: MagicMock) -> None:
    """state="all" is accepted and adds no state token to the query."""
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo
    mock_mgr._github_client.search_issues.return_value = FakeSearchResults([])

    github_search(query="bug", state="all")

    mock_mgr._github_client.search_issues.assert_called_once()
    call_kwargs = mock_mgr._github_client.search_issues.call_args[1]
    assert call_kwargs["query"] == "repo:owner/repo is:issue bug"
    assert "is:all" not in call_kwargs["query"]


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


@pytest.mark.parametrize("state", ["Open", "CLOSED", "All"])
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_state_is_case_insensitive(
    mock_manager_cls: MagicMock, state: str
) -> None:
    """State matching is case-insensitive, like every inline qualifier check."""
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo
    mock_mgr._github_client.search_issues.return_value = FakeSearchResults([])

    github_search(query="bug", state=state)

    call_kwargs = mock_mgr._github_client.search_issues.call_args[1]
    token = "" if state.lower() == "all" else f" is:{state.lower()}"
    assert call_kwargs["query"] == f"repo:owner/repo is:issue bug{token}"


@pytest.mark.parametrize("assignee", ["john doe", " alice", "alice\tb"])
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_rejects_assignee_with_whitespace(
    mock_manager_cls: MagicMock, assignee: str
) -> None:
    """Whitespace would split the qualifier and silently narrow the search."""
    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr

    result = github_search(query="bug", assignee=assignee)

    assert result == (
        f"Error: Invalid assignee {assignee!r}: "
        "a GitHub username cannot contain whitespace"
    )
    mock_mgr._github_client.search_issues.assert_not_called()
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


@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_sends_query_unmodified(mock_manager_cls: MagicMock) -> None:
    """An explicit is:issue suppresses the default; the query is sent verbatim."""
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    item = MagicMock()
    item.number = 1
    item.title = "Result"
    item.state = "open"
    item.labels = []
    item.pull_request = None

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo
    mock_mgr._github_client.search_issues.return_value = FakeSearchResults([item])

    result = github_search(query="Jenkins is:issue")

    call_kwargs = mock_mgr._github_client.search_issues.call_args[1]
    assert call_kwargs["query"] == "repo:owner/repo Jenkins is:issue"
    assert "auto-added" not in result


@pytest.mark.parametrize(
    "query",
    [
        "Jenkins is:pull-request",
        "Jenkins is:pr",
        "Jenkins IS:PULL-REQUEST",
        "is:pull-request",
        "Jenkins type:pr",
        "Jenkins type:issue",
        "Jenkins TYPE:PR",
        "type:pr",
    ],
)
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_explicit_type_suppresses_default(
    mock_manager_cls: MagicMock, query: str
) -> None:
    """Any is:/type: result-type token stops is:issue being added."""
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo
    mock_mgr._github_client.search_issues.return_value = FakeSearchResults([])

    github_search(query=query)

    call_kwargs = mock_mgr._github_client.search_issues.call_args[1]
    assert call_kwargs["query"] == f"repo:owner/repo {query}"


@pytest.mark.parametrize(
    "query",
    [
        "bug",
        "",
        "is:issuebug",
        "is:pull-requests",
        "release:issue",
        "this:pr",
    ],
)
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_defaults_to_is_issue(
    mock_manager_cls: MagicMock, query: str
) -> None:
    """Without a result-type token GitHub 422s, so is:issue is added."""
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo
    mock_mgr._github_client.search_issues.return_value = FakeSearchResults([])

    github_search(query=query)

    call_kwargs = mock_mgr._github_client.search_issues.call_args[1]
    expected = " ".join(p for p in ("repo:owner/repo", "is:issue", query) if p)
    assert call_kwargs["query"] == expected


@pytest.mark.parametrize(
    "query", ["type:pull-request", "fix type:pull-request", "TYPE:PULL-REQUEST"]
)
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_rejects_type_pull_request(
    mock_manager_cls: MagicMock, query: str
) -> None:
    """Not GitHub syntax - reject it instead of returning a silent empty result."""
    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr

    result = github_search(query=query)

    assert result == (
        "Error: Invalid qualifier 'type:pull-request': "
        "use 'is:pull-request' or 'is:pr'"
    )
    mock_mgr._github_client.search_issues.assert_not_called()
    mock_mgr._get_repository.assert_not_called()


@pytest.mark.parametrize("query", ["type:pull-requests", "release:type:pull-request"])
@patch("mcp_workspace.github_operations.issues.IssueManager")
def test_github_search_type_pull_request_rejection_boundaries(
    mock_manager_cls: MagicMock, query: str
) -> None:
    """Near misses are free text, not the rejected qualifier."""
    mock_repo = MagicMock()
    mock_repo.full_name = "owner/repo"

    mock_mgr = MagicMock()
    mock_manager_cls.return_value = mock_mgr
    mock_mgr._get_repository.return_value = mock_repo
    mock_mgr._github_client.search_issues.return_value = FakeSearchResults([])

    github_search(query=query)

    call_kwargs = mock_mgr._github_client.search_issues.call_args[1]
    assert call_kwargs["query"] == f"repo:owner/repo is:issue {query}"


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
