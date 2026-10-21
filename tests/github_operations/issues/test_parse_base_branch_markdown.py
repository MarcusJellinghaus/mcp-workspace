"""Markdown-structure tests for parse_base_branch.

Only top-level ATX headings start or end a Base Branch section; headings inside
fences, blockquotes, list items or HTML comments are ignored.
"""

import pytest

from mcp_workspace.github_operations.issues.base import (
    MalformedBaseBranchError,
    parse_base_branch,
)


class TestIgnoredHeadings:
    """Headings that are not top-level ATX headings never start a section."""

    def test_backtick_fenced_heading_ignored(self) -> None:
        body = "### Description\n\n```\n### Base Branch\n\nfeature/x\n```\n"
        assert parse_base_branch(body) is None

    def test_tilde_fenced_heading_ignored(self) -> None:
        body = "### Description\n\n~~~\n### Base Branch\n\nfeature/x\n~~~\n"
        assert parse_base_branch(body) is None

    def test_fenced_quote_plus_real_section(self) -> None:
        body = (
            "### Description\n\n"
            "```\n### Base Branch\n\nquoted/branch\n```\n\n"
            "### Base Branch\n\nreal/branch\n\n"
            "### Notes\n\nmore\n"
        )
        assert parse_base_branch(body) == "real/branch"

    def test_unclosed_fence_swallows_heading(self) -> None:
        body = "### Description\n\n```\ncode\n\n### Base Branch\n\nfeature/x\n"
        assert parse_base_branch(body) is None

    def test_html_comment_heading_ignored(self) -> None:
        body = "<!--\n### Base Branch\n\nfeature/x\n-->\n\n### Description\n\ntext\n"
        assert parse_base_branch(body) is None

    def test_blockquoted_heading_ignored(self) -> None:
        body = "> ### Base Branch\n>\n> feature/x\n"
        assert parse_base_branch(body) is None

    def test_list_item_heading_ignored(self) -> None:
        body = "- ### Base Branch\n\n  feature/x\n"
        assert parse_base_branch(body) is None


class TestSectionBoundaries:
    """Section content is read from raw lines between top-level ATX headings."""

    def test_setext_underline_does_not_end_section(self) -> None:
        body = "### Base Branch\n\nepic/x\n---\n"
        with pytest.raises(MalformedBaseBranchError):
            parse_base_branch(body)

    def test_crlf_single_line(self) -> None:
        body = "### Base Branch\r\n\r\nfeature/v2\r\n\r\n### Next"
        assert parse_base_branch(body) == "feature/v2"

    def test_crlf_two_lines_raises(self) -> None:
        body = "### Base Branch\r\n\r\nfeature/v2\r\nextra\r\n\r\n### Next"
        with pytest.raises(MalformedBaseBranchError):
            parse_base_branch(body)

    def test_real_section_containing_fence_raises(self) -> None:
        body = "### Base Branch\n\n```\nfeature/x\n```\n\n### Next\n"
        with pytest.raises(MalformedBaseBranchError):
            parse_base_branch(body)

    @pytest.mark.parametrize("next_heading", ["# Top", "## Mid", "###### Deep"])
    def test_section_ends_at_any_level_atx_heading(self, next_heading: str) -> None:
        body = f"### Base Branch\n\nfeature/x\n\n{next_heading}\n\nmore text\n"
        assert parse_base_branch(body) == "feature/x"
