"""Tests for SearchSpec - GitHub issue-search query construction.

Pure unit tests: no mocks, no server fixture. Handler-level wiring, result
rendering and the validation-ordering guard live in ``test_github_search_tool``.
"""

from typing import Any

import pytest

from mcp_workspace.github_operations.search import SearchSpec


def test_multiple_labels_each_emit_own_qualifier() -> None:
    """Each label emits its own label: qualifier, never a comma-joined labels:."""
    spec = SearchSpec.from_arguments(query="bug", labels=["bug", "urgent"])

    result = spec.to_query("owner/repo")

    assert result == 'repo:owner/repo is:issue bug label:"bug" label:"urgent"'
    # Regression marker for #254: the old comma-joined form must never return.
    assert "labels:bug,urgent" not in result


def test_label_with_colon_is_quoted() -> None:
    """Labels are always quoted, so colons in a label name survive intact."""
    spec = SearchSpec.from_arguments(query="x", labels=["status-01:created"])

    assert spec.to_query("owner/repo") == (
        'repo:owner/repo is:issue x label:"status-01:created"'
    )


def test_state_emits_is_qualifier() -> None:
    """state="closed" emits is:closed; an omitted state adds nothing."""
    result = SearchSpec.from_arguments(query="bug", state="closed").to_query(
        "owner/repo"
    )

    assert result == "repo:owner/repo is:issue bug is:closed"
    assert "state:" not in result

    assert (
        SearchSpec.from_arguments(query="bug").to_query("owner/repo")
        == "repo:owner/repo is:issue bug"
    )


@pytest.mark.parametrize(
    "query",
    ["bug is:closed", "bug state:closed", "bug IS:CLOSED", "is:open bug"],
)
def test_inline_state_suppresses_state_param(query: str) -> None:
    """An inline state qualifier wins - two state tokens would match nothing."""
    spec = SearchSpec.from_arguments(query=query, state="open")

    assert spec.to_query("owner/repo") == f"repo:owner/repo is:issue {query}"


def test_empty_query_yields_qualifiers_only() -> None:
    """An empty query yields qualifiers only - no double or trailing space."""
    spec = SearchSpec.from_arguments(query="", state="open", labels=["bug"])

    assert spec.to_query("owner/repo") == (
        'repo:owner/repo is:issue is:open label:"bug"'
    )


def test_state_all_emits_no_token() -> None:
    """state="all" is accepted and adds no state token to the query."""
    result = SearchSpec.from_arguments(query="bug", state="all").to_query("owner/repo")

    assert result == "repo:owner/repo is:issue bug"
    assert "is:all" not in result


@pytest.mark.parametrize("state", ["Open", "CLOSED", "All"])
def test_state_is_case_insensitive(state: str) -> None:
    """State matching is case-insensitive, like every inline qualifier check."""
    spec = SearchSpec.from_arguments(query="bug", state=state)

    token = "" if state.lower() == "all" else f" is:{state.lower()}"
    assert spec.to_query("owner/repo") == f"repo:owner/repo is:issue bug{token}"


def test_explicit_is_issue_sent_unmodified() -> None:
    """An explicit is:issue suppresses the default; the query is sent verbatim."""
    spec = SearchSpec.from_arguments(query="Jenkins is:issue")

    assert spec.to_query("owner/repo") == "repo:owner/repo Jenkins is:issue"


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
def test_explicit_type_suppresses_default(query: str) -> None:
    """Any is:/type: result-type token stops is:issue being added."""
    spec = SearchSpec.from_arguments(query=query)

    assert spec.to_query("owner/repo") == f"repo:owner/repo {query}"


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
def test_defaults_to_is_issue(query: str) -> None:
    """Without a result-type token GitHub 422s, so is:issue is added."""
    spec = SearchSpec.from_arguments(query=query)

    expected = " ".join(p for p in ("repo:owner/repo", "is:issue", query) if p)
    assert spec.to_query("owner/repo") == expected


@pytest.mark.parametrize("query", ["type:pull-requests", "release:type:pull-request"])
def test_type_pull_request_near_misses_are_free_text(query: str) -> None:
    """Near misses are free text, not the rejected qualifier."""
    spec = SearchSpec.from_arguments(query=query)

    assert spec.to_query("owner/repo") == f"repo:owner/repo is:issue {query}"


@pytest.mark.parametrize(
    "kwargs, message",
    [
        (
            {"query": "x", "labels": ["bug", 'needs "review"']},
            "Invalid label 'needs \"review\"': "
            "a label containing a double quote cannot be searched",
        ),
        (
            {"query": "x", "labels": [""]},
            "Invalid label '': a label cannot be empty or whitespace-only",
        ),
        (
            {"query": "x", "labels": ["   "]},
            "Invalid label '   ': a label cannot be empty or whitespace-only",
        ),
        (
            {"query": "x", "labels": ["\t"]},
            "Invalid label '\\t': a label cannot be empty or whitespace-only",
        ),
        (
            {"query": "bug", "assignee": "john doe"},
            "Invalid assignee 'john doe': a GitHub username cannot contain whitespace",
        ),
        (
            {"query": "bug", "assignee": " alice"},
            "Invalid assignee ' alice': a GitHub username cannot contain whitespace",
        ),
        (
            {"query": "bug", "assignee": "alice\tb"},
            "Invalid assignee 'alice\\tb': a GitHub username cannot contain whitespace",
        ),
        (
            {"query": "type:pull-request"},
            "Invalid qualifier 'type:pull-request': use 'is:pull-request' or 'is:pr'",
        ),
        (
            {"query": "fix type:pull-request"},
            "Invalid qualifier 'type:pull-request': use 'is:pull-request' or 'is:pr'",
        ),
        (
            {"query": "TYPE:PULL-REQUEST"},
            "Invalid qualifier 'type:pull-request': use 'is:pull-request' or 'is:pr'",
        ),
        (
            {"query": "bug", "state": "Bogus"},
            "Invalid state: Bogus. Expected 'open', 'closed' or 'all'.",
        ),
    ],
)
def test_from_arguments_rejects_invalid_input(
    kwargs: dict[str, Any], message: str
) -> None:
    """Every rejection carries its exact message, prefix-free."""
    with pytest.raises(ValueError) as excinfo:
        SearchSpec.from_arguments(**kwargs)
    assert str(excinfo.value) == message


@pytest.mark.parametrize(
    "query, needs_type_default, has_inline_state",
    [
        ("bug", True, False),
        ("bug is:pr", False, False),
        ("bug IS:CLOSED", True, True),
        ("bug state:open", True, True),
    ],
)
def test_flags_are_precomputed(
    query: str, needs_type_default: bool, has_inline_state: bool
) -> None:
    """from_arguments computes both flags; to_query only reads them."""
    spec = SearchSpec.from_arguments(query)
    assert spec.needs_type_default is needs_type_default
    assert spec.has_inline_state is has_inline_state
