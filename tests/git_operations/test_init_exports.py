"""Tests for git_operations package __init__.py exports."""

from mcp_workspace import git_operations


def test_all_expected_symbols_exported() -> None:
    """Verify all symbols from __all__ are importable."""
    for name in git_operations.__all__:
        assert hasattr(git_operations, name), f"Missing export: {name}"


def test_expected_symbol_count() -> None:
    """Verify __all__ has the expected 71 symbols."""
    from mcp_workspace.git_operations import __all__

    assert len(__all__) == 71


def test_verify_git_and_check_result_exported() -> None:
    """Verify verify_git and CheckResult are exported."""
    assert "verify_git" in git_operations.__all__
    assert "CheckResult" in git_operations.__all__


def test_renormalize_paths_exported() -> None:
    """Verify renormalize_paths is exported from the staging module."""
    from mcp_workspace.git_operations import staging

    assert "renormalize_paths" in git_operations.__all__
    assert git_operations.renormalize_paths is staging.renormalize_paths


def test_is_staged_diff_cr_only_exported() -> None:
    """Verify is_staged_diff_cr_only is exported from the repository_status module."""
    from mcp_workspace.git_operations import repository_status

    assert "is_staged_diff_cr_only" in git_operations.__all__
    assert (
        git_operations.is_staged_diff_cr_only
        is repository_status.is_staged_diff_cr_only
    )


def test_all_remains_alphabetised() -> None:
    """Verify __all__ entries are sorted alphabetically."""
    assert list(git_operations.__all__) == sorted(git_operations.__all__)
