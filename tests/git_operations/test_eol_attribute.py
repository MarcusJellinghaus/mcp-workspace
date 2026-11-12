"""Tests for get_eol_attribute."""

from pathlib import Path

import pytest
from git import Repo
from git.exc import InvalidGitRepositoryError

from mcp_workspace.git_operations import get_eol_attribute


def _write_gitattributes(project_dir: Path) -> None:
    (project_dir / ".gitattributes").write_bytes(b"*.sh eol=lf\n*.bat eol=crlf\n")


def test_eol_lf_for_missing_path(git_repo: tuple[Repo, Path]) -> None:
    """A rule applies to a path that does not exist yet."""
    _, project_dir = git_repo
    _write_gitattributes(project_dir)

    assert not (project_dir / "run.sh").exists()
    assert get_eol_attribute("run.sh", project_dir) == "lf"


def test_eol_crlf(git_repo: tuple[Repo, Path]) -> None:
    """An eol=crlf rule returns crlf."""
    _, project_dir = git_repo
    _write_gitattributes(project_dir)

    assert get_eol_attribute("build.bat", project_dir) == "crlf"


def test_eol_unspecified_without_rule(git_repo: tuple[Repo, Path]) -> None:
    """A path no rule matches returns unspecified."""
    _, project_dir = git_repo
    _write_gitattributes(project_dir)

    assert get_eol_attribute("notes.md", project_dir) == "unspecified"


def test_eol_nested_path_with_either_separator(git_repo: tuple[Repo, Path]) -> None:
    """Nested paths match with forward slashes and with backslashes."""
    _, project_dir = git_repo
    _write_gitattributes(project_dir)

    assert get_eol_attribute("sub/dir/x.sh", project_dir) == "lf"
    assert get_eol_attribute("sub\\dir\\x.sh", project_dir) == "lf"


def test_eol_raises_outside_repository(tmp_path: Path) -> None:
    """A folder that is not a repository raises."""
    with pytest.raises(InvalidGitRepositoryError):
        get_eol_attribute("run.sh", tmp_path)
