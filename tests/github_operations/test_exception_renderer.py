"""Unit tests for `render_exception_for_display`."""

from typing import Any

import pytest
from github.GithubException import GithubException, UnknownObjectException

from mcp_workspace.github_operations.exception_renderer import (
    render_exception_for_display,
)


class TestGithubException:
    """GithubException rendering."""

    def test_with_message(self) -> None:
        result = render_exception_for_display(
            GithubException(500, {"message": "Server Error"}, None)
        )
        assert result == "GithubException 500 — Server Error"

    def test_empty_data_omits_message_segment(self) -> None:
        result = render_exception_for_display(GithubException(500, {}, None))
        assert result == "GithubException 500"
        assert "—" not in result
        assert "(no message)" not in result

    def test_non_dict_data_omits_message_segment(self) -> None:
        result = render_exception_for_display(GithubException(500, "raw text", None))
        assert result == "GithubException 500"
        assert "—" not in result
        assert "(no message)" not in result

    def test_whitespace_only_message_omits_segment(self) -> None:
        result = render_exception_for_display(
            GithubException(500, {"message": "   "}, None)
        )
        assert result == "GithubException 500"
        assert "—" not in result
        assert "(no message)" not in result

    def test_multi_line_message_collapsed_to_single_spaces(self) -> None:
        result = render_exception_for_display(
            GithubException(500, {"message": "boom\nsecond line"}, None)
        )
        assert result == "GithubException 500 — boom second line"

    def test_truncation_at_200_chars(self) -> None:
        result = render_exception_for_display(
            GithubException(500, {"message": "x" * 500}, None)
        )
        assert result.endswith("...")
        assert len(result) == 203


class TestGenericException:
    """Non-GithubException rendering."""

    def test_with_message(self) -> None:
        result = render_exception_for_display(ConnectionError("getaddrinfo failed"))
        assert result == "ConnectionError — getaddrinfo failed"

    def test_whitespace_message_renders_no_message(self) -> None:
        result = render_exception_for_display(RuntimeError("   "))
        assert result == "RuntimeError — (no message)"

    def test_empty_message_renders_no_message(self) -> None:
        result = render_exception_for_display(RuntimeError(""))
        assert result == "RuntimeError — (no message)"

    def test_multi_line_message_collapsed(self) -> None:
        result = render_exception_for_display(RuntimeError("first\n\nsecond"))
        assert result == "RuntimeError — first second"

    def test_truncation_at_200_chars(self) -> None:
        result = render_exception_for_display(RuntimeError("x" * 500))
        assert result.endswith("...")
        assert len(result) == 203


def _graphql_exc(errors: Any, status: int = 400) -> GithubException:
    """Build a GithubException carrying a realistic GraphQL response body."""
    return GithubException(status, {"data": None, "errors": errors}, None)


class TestGraphqlErrors:
    """GraphQL error body rendering."""

    @pytest.mark.parametrize(
        ("errors", "expected"),
        [
            (
                [{"type": "FORBIDDEN", "message": "Resource not accessible"}],
                "GraphQL FORBIDDEN — Resource not accessible",
            ),
            (
                [{"message": "Field 'x' doesn't exist on type 'Y'"}],
                "GraphQL error — Field 'x' doesn't exist on type 'Y'",
            ),
            (
                [{"type": "A", "message": "a"}, {"message": "b"}],
                "GraphQL A — a; GraphQL error — b",
            ),
            (
                [
                    {"type": "A", "message": "a"},
                    {"type": "B", "message": "b"},
                    {"type": "C", "message": "c"},
                ],
                "GraphQL A — a; GraphQL B — b (+1 more)",
            ),
            (
                [
                    {"type": "A", "message": "a"},
                    {"type": "B", "message": "b"},
                    {"type": "C", "message": "c"},
                    {"type": "D", "message": "d"},
                    {"type": "E", "message": "e"},
                ],
                "GraphQL A — a; GraphQL B — b (+3 more)",
            ),
            (
                [{"type": "FORBIDDEN", "message": "boom\n\nsecond line"}],
                "GraphQL FORBIDDEN — boom second line",
            ),
        ],
    )
    def test_formatting(self, errors: Any, expected: str) -> None:
        result = render_exception_for_display(_graphql_exc(errors))
        assert result == expected
        assert "\n" not in result

    def test_long_first_message_keeps_more_suffix(self) -> None:
        result = render_exception_for_display(
            _graphql_exc(
                [
                    {"type": "A", "message": "x" * 300},
                    {"type": "B", "message": "b"},
                    {"type": "C", "message": "c"},
                ]
            )
        )
        assert result.endswith("(+1 more)")

    def test_unparseable_entries_are_still_counted(self) -> None:
        result = render_exception_for_display(
            _graphql_exc(
                [
                    {"type": "A", "message": "a"},
                    {"type": "B"},
                    "not a dict",
                    {"message": "   "},
                ]
            )
        )
        assert result == "GraphQL A — a (+3 more)"

    def test_more_suffix_counts_total_not_rendered_pairs(self) -> None:
        result = render_exception_for_display(
            _graphql_exc(
                [
                    {"type": "A", "message": "a"},
                    {"type": "B", "message": "b"},
                    {"type": "C"},
                ]
            )
        )
        assert result == "GraphQL A — a; GraphQL B — b (+1 more)"

    def test_unknown_object_exception_uses_graphql_arm(self) -> None:
        exc = UnknownObjectException(
            404,
            {
                "data": None,
                "errors": [
                    {
                        "type": "NOT_FOUND",
                        "message": "Could not resolve to a PullRequest",
                    }
                ],
            },
            None,
            "Could not resolve to a PullRequest",
        )
        result = render_exception_for_display(exc)
        assert result == "GraphQL NOT_FOUND — Could not resolve to a PullRequest"

    def test_non_dict_body_containing_errors_substring(self) -> None:
        result = render_exception_for_display(
            GithubException(500, "raw errors text", None)
        )
        assert result == "GithubException 500"

    def test_status_and_type_name_never_leak(self) -> None:
        result = render_exception_for_display(
            _graphql_exc([{"type": "FORBIDDEN", "message": "Resource not accessible"}])
        )
        assert "400" not in result
        assert "GithubException" not in result

    def test_errors_not_a_list_falls_through_to_rest(self) -> None:
        result = render_exception_for_display(
            GithubException(400, {"message": "boom", "errors": "nope"}, None)
        )
        assert result == "GithubException 400 — boom"

    def test_entries_not_dicts_fall_through_to_rest(self) -> None:
        result = render_exception_for_display(_graphql_exc(["a", "b"]))
        assert result == "GithubException 400"

    def test_empty_errors_list_falls_through_to_rest(self) -> None:
        result = render_exception_for_display(_graphql_exc([]))
        assert result == "GithubException 400"

    def test_rest_422_with_errors_array_is_not_misclassified(self) -> None:
        result = render_exception_for_display(
            GithubException(
                422,
                {
                    "message": "Validation Failed",
                    "errors": [
                        {
                            "resource": "PullRequest",
                            "code": "custom",
                            "message": "No commits between main and topic",
                        }
                    ],
                },
                None,
            )
        )
        assert result == "GithubException 422 — Validation Failed"
        assert "GraphQL" not in result
        assert "422" in result
