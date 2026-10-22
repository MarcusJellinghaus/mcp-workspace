"""Tests for mcp_workspace.github_operations.trust module."""

from typing import Optional
from unittest.mock import MagicMock

import pytest

from mcp_workspace.github_operations.trust import (
    TRUSTED_ASSOCIATIONS,
    is_trusted_author,
    normalize_author_association,
)


class TestIsTrustedAuthor:
    """Tests for is_trusted_author()."""

    @pytest.mark.parametrize("association", ["OWNER", "MEMBER", "COLLABORATOR"])
    def test_trusted_associations(self, association: str) -> None:
        assert association in TRUSTED_ASSOCIATIONS
        assert is_trusted_author("stranger", association, frozenset()) is True

    @pytest.mark.parametrize(
        "association",
        [
            "CONTRIBUTOR",
            "FIRST_TIME_CONTRIBUTOR",
            "FIRST_TIMER",
            "NONE",
            "MANNEQUIN",
            None,
        ],
    )
    def test_untrusted_associations(self, association: Optional[str]) -> None:
        assert is_trusted_author("stranger", association, frozenset({"alice"})) is False

    def test_allowlisted_login_case_insensitive(self) -> None:
        trusted = frozenset({"dependabot[bot]"})
        assert is_trusted_author("Dependabot[bot]", "NONE", trusted) is True

    def test_bot_suffix_required(self) -> None:
        trusted = frozenset({"dependabot[bot]"})
        assert is_trusted_author("dependabot", "NONE", trusted) is False

    @pytest.mark.parametrize("login", ["", None])
    def test_empty_login_untrusted_even_if_empty_allowlisted(
        self, login: Optional[str]
    ) -> None:
        assert is_trusted_author(login, None, frozenset({""})) is False


class TestNormalizeAuthorAssociation:
    """Tests for normalize_author_association()."""

    def test_string_passes_through(self) -> None:
        assert normalize_author_association("OWNER") == "OWNER"

    @pytest.mark.parametrize("value", [MagicMock(), None, 1])
    def test_non_string_becomes_none(self, value: object) -> None:
        assert normalize_author_association(value) is None


def test_reexported_from_github_operations() -> None:
    # pylint: disable=import-outside-toplevel
    from mcp_workspace.github_operations import (
        get_trusted_commenters,
    )
    from mcp_workspace.github_operations import is_trusted_author as reexported

    assert reexported is is_trusted_author
    assert callable(get_trusted_commenters)
