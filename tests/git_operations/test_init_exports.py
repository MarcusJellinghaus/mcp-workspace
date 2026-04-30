"""Tests for git_operations package __init__.py exports."""

from mcp_workspace import git_operations


def test_all_expected_symbols_exported() -> None:
    """Verify all symbols from __all__ are importable."""
    for name in git_operations.__all__:
        assert hasattr(git_operations, name), f"Missing export: {name}"


def test_expected_symbol_count() -> None:
    """Verify __all__ has the expected 35 symbols."""
    from mcp_workspace.git_operations import __all__

    assert len(__all__) == 35


def test_verify_git_and_check_result_exported() -> None:
    """Verify verify_git and CheckResult are exported."""
    assert "verify_git" in git_operations.__all__
    assert "CheckResult" in git_operations.__all__


def test_all_remains_alphabetised() -> None:
    """Verify __all__ entries are sorted alphabetically."""
    assert list(git_operations.__all__) == sorted(git_operations.__all__)
