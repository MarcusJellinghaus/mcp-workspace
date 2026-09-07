"""Tests for the delete_directory file operation."""

from pathlib import Path

import pytest

from mcp_workspace.file_tools.file_operations import delete_directory
from tests.conftest import TEST_DIR


def test_delete_directory_empty(project_dir: Path) -> None:
    """Empty directory is removed with recursive=False; returns [rel]."""
    rel = TEST_DIR / "empty_dir"
    abs_dir = project_dir / rel
    abs_dir.mkdir(parents=True)

    result = delete_directory(str(rel), project_dir, recursive=False)

    assert result == [str(rel)]
    assert not abs_dir.exists()


def test_delete_directory_non_empty_without_recursive_raises(
    project_dir: Path,
) -> None:
    """Non-empty directory without recursive raises ValueError; dir survives."""
    rel = TEST_DIR / "non_empty_dir"
    abs_dir = project_dir / rel
    abs_dir.mkdir(parents=True)
    (abs_dir / "file.txt").write_text("content", encoding="utf-8")

    with pytest.raises(ValueError, match="recursive=True"):
        delete_directory(str(rel), project_dir, recursive=False)

    assert abs_dir.exists()


def test_delete_directory_recursive(project_dir: Path) -> None:
    """Recursive delete removes a nested tree and lists its contents."""
    rel = TEST_DIR / "tree"
    abs_dir = project_dir / rel
    sub = abs_dir / "sub"
    sub.mkdir(parents=True)
    (abs_dir / "top.txt").write_text("top", encoding="utf-8")
    (sub / "nested.txt").write_text("nested", encoding="utf-8")

    result = delete_directory(str(rel), project_dir, recursive=True)

    assert not abs_dir.exists()
    assert str(rel) in result
    assert str(rel / "sub") in result
    assert str(rel / "top.txt") in result
    assert str(rel / "sub" / "nested.txt") in result


def test_delete_directory_path_is_file_raises(project_dir: Path) -> None:
    """Passing a file path raises ValueError referencing delete_this_file."""
    rel = TEST_DIR / "a_file.txt"
    abs_file = project_dir / rel
    abs_file.write_text("content", encoding="utf-8")

    with pytest.raises(ValueError, match="delete_this_file"):
        delete_directory(str(rel), project_dir, recursive=True)

    assert abs_file.exists()


def test_delete_directory_project_root_refused(project_dir: Path) -> None:
    """Targeting the project root is refused; the root still exists."""
    with pytest.raises(ValueError):
        delete_directory(".", project_dir, recursive=True)

    assert project_dir.exists()


def test_delete_directory_not_found_idempotent(project_dir: Path) -> None:
    """A missing directory is idempotent — returns a message, no exception."""
    rel = TEST_DIR / "does_not_exist"

    result = delete_directory(str(rel), project_dir, recursive=True)

    assert len(result) == 1
    assert "does not exist" in result[0]


def test_delete_directory_outside_project_raises(project_dir: Path) -> None:
    """A path outside the project directory raises a security ValueError."""
    with pytest.raises(ValueError, match="Security error"):
        delete_directory("../evil", project_dir, recursive=True)


def test_delete_directory_truncation_summary(project_dir: Path) -> None:
    """25 files in a dir truncate the list to 20 + a summary entry."""
    rel = TEST_DIR / "many"
    abs_dir = project_dir / rel
    abs_dir.mkdir(parents=True)
    for i in range(25):
        (abs_dir / f"f{i:02d}.txt").write_text("x", encoding="utf-8")

    result = delete_directory(str(rel), project_dir, recursive=True)

    assert len(result) == 21
    assert result[20].startswith("... and 6 more")
    assert "dirs deleted total" in result[20]
    assert not abs_dir.exists()
