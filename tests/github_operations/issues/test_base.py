"""Unit tests for issues/base.py validation and parsing helpers."""

import logging

import pytest

from mcp_workspace.github_operations.issues.base import (
    InvalidBaseBranchRefError,
    MalformedBaseBranchError,
    format_malformed_base_branch,
    is_valid_ref_name,
    parse_base_branch,
    validate_comment_id,
    validate_issue_number,
    validate_issue_number_or_log,
)


def test_validate_issue_number() -> None:
    """Test issue number validation."""
    # Test invalid numbers
    with pytest.raises(ValueError, match="Issue number must be a positive integer"):
        validate_issue_number(0)

    with pytest.raises(ValueError, match="Issue number must be a positive integer"):
        validate_issue_number(-1)

    # Test valid number doesn't raise
    try:
        validate_issue_number(1)
        validate_issue_number(999)
    except ValueError:
        pytest.fail("Valid issue numbers should not raise ValueError")


def test_validate_issue_number_or_log_valid() -> None:
    """Test that valid issue numbers return True without logging an error."""
    assert validate_issue_number_or_log(1) is True
    assert validate_issue_number_or_log(999) is True


def test_validate_issue_number_or_log_invalid(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that invalid issue numbers return False and log instead of raising."""
    with caplog.at_level(logging.ERROR):
        assert validate_issue_number_or_log(0) is False
        assert validate_issue_number_or_log(-1) is False

    assert "Invalid issue number: 0" in caplog.text
    assert "Invalid issue number: -1" in caplog.text


def test_validate_comment_id() -> None:
    """Test comment ID validation."""
    # Test invalid IDs
    with pytest.raises(ValueError, match="Comment ID must be a positive integer"):
        validate_comment_id(0)

    with pytest.raises(ValueError, match="Comment ID must be a positive integer"):
        validate_comment_id(-1)

    # Test valid ID doesn't raise
    try:
        validate_comment_id(1)
        validate_comment_id(999)
    except ValueError:
        pytest.fail("Valid comment IDs should not raise ValueError")


def test_parse_base_branch_happy_path() -> None:
    """Test parsing a well-formed base branch section."""
    body = "### Base Branch\n\nfeature/v2\n\n### Description"
    assert parse_base_branch(body) == "feature/v2"


def test_parse_base_branch_empty_body() -> None:
    """Test that an empty body returns None."""
    assert parse_base_branch("") is None


def test_parse_base_branch_any_heading_level() -> None:
    """Test that any markdown heading level is accepted."""
    assert parse_base_branch("# Base Branch\n\nx") == "x"
    assert parse_base_branch("###### Base Branch\n\nx") == "x"


def test_parse_base_branch_case_insensitive() -> None:
    """Test that the heading match is case-insensitive."""
    assert parse_base_branch("### base branch\n\nx") == "x"


def test_parse_base_branch_no_match() -> None:
    """Test that a body without a base branch heading returns None."""
    assert parse_base_branch("### Description\n\nno base branch here") is None


def test_parse_base_branch_empty_content() -> None:
    """Test that an empty base branch section returns None."""
    assert parse_base_branch("### Base Branch\n\n### Next") is None


def test_parse_base_branch_multiline_raises() -> None:
    """Test that multi-line content raises ValueError."""
    with pytest.raises(ValueError):
        parse_base_branch("### Base Branch\n\nline1\nline2\n")


def test_parse_base_branch_multiline_raises_malformed_base_branch_error() -> None:
    """Test that multi-line content raises MalformedBaseBranchError specifically."""
    with pytest.raises(MalformedBaseBranchError):
        parse_base_branch("### Base Branch\n\nline1\nline2\n")


def test_malformed_base_branch_error_is_a_value_error() -> None:
    """Test that MalformedBaseBranchError is a ValueError subclass."""
    assert issubclass(MalformedBaseBranchError, ValueError)


def test_malformed_base_branch_error_carries_content() -> None:
    """Test that MalformedBaseBranchError carries the raw section content."""
    with pytest.raises(MalformedBaseBranchError) as exc_info:
        parse_base_branch("### Base Branch\n\nline1\nline2\n")
    assert exc_info.value.content == "line1\nline2"


def test_format_malformed_base_branch_sentence() -> None:
    """Test that the helper returns the bare sentence naming the first line."""
    error = MalformedBaseBranchError("epic/multi-language\nmore")
    assert format_malformed_base_branch(error) == (
        "`### Base Branch` must contain only the branch name on one line; "
        "move other text to another section. First line: 'epic/multi-language'"
    )


@pytest.mark.parametrize("name", ["main", "feature/v2", "release-1.2", "x"])
def test_is_valid_ref_name_accepts(name: str) -> None:
    """Test that ordinary branch names are valid ref names."""
    assert is_valid_ref_name(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "",
        "main branch",
        "a..b",
        "a~1",
        "a^",
        "a:b",
        "a?",
        "a*",
        "a[b",
        "a\\b",
        "-x",
        ".x",
        "x.",
        "x/",
        "x.lock",
        "a@{b",
        "a//b",
        "a\tb",
        "a\x7fb",
    ],
)
def test_is_valid_ref_name_rejects(name: str) -> None:
    """Test that names git refuses as refs are rejected."""
    assert is_valid_ref_name(name) is False


def test_parse_base_branch_invalid_ref_raises() -> None:
    """Test that a single-line but invalid ref raises InvalidBaseBranchRefError."""
    with pytest.raises(InvalidBaseBranchRefError) as exc_info:
        parse_base_branch("### Base Branch\n\nmain branch\n")
    assert isinstance(exc_info.value, MalformedBaseBranchError)
    assert exc_info.value.content == "main branch"


def test_format_malformed_base_branch_invalid_ref() -> None:
    """Test that the invalid-ref message names the ref problem and the value."""
    message = format_malformed_base_branch(InvalidBaseBranchRefError("main branch"))
    assert "valid git branch name" in message
    assert "'main branch'" in message
    assert "on one line" not in message
