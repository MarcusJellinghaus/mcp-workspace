"""Unit tests for issues/base.py validation and parsing helpers."""

import pytest

from mcp_workspace.github_operations.issues.base import (
    parse_base_branch,
    validate_comment_id,
    validate_issue_number,
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
