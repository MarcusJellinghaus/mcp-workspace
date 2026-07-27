"""Tests for file operations functionality."""

import os
import shutil
from pathlib import Path

import pytest

# Import functions directly from the module
from mcp_workspace.file_tools.file_operations import (
    append_file,
    delete_directory,
    delete_file,
    read_file,
    save_file,
)
from tests.conftest import TEST_CONTENT, TEST_DIR, TEST_FILE


def test_save_file(project_dir: Path) -> None:
    """Test writing to a file."""
    # Test writing to a file
    result = save_file(str(TEST_FILE), TEST_CONTENT, project_dir=project_dir)

    # Create path for verification
    abs_file_path = project_dir / TEST_FILE

    # Verify the file was written
    assert result is True
    assert abs_file_path.exists()

    # Verify the file content
    with open(abs_file_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert content == TEST_CONTENT


def test_save_file_atomic_overwrite(project_dir: Path) -> None:
    """Test atomically overwriting an existing file."""
    # Create absolute path for test file
    abs_file_path = project_dir / TEST_FILE

    # Create initial content
    initial_content = "This is the initial content."
    with open(abs_file_path, "w", encoding="utf-8") as f:
        f.write(initial_content)

    # Verify initial content
    with open(abs_file_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert content == initial_content

    # Overwrite with new content
    new_content = "This is the new content that replaces the old content."
    result = save_file(str(TEST_FILE), new_content, project_dir=project_dir)

    # Verify the file was written
    assert result is True
    assert abs_file_path.exists()

    # Verify the new content
    with open(abs_file_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert content == new_content

    # Verify no temporary files were left behind
    parent_dir = abs_file_path.parent
    temp_files = [
        f
        for f in parent_dir.iterdir()
        if f.name.startswith("tmp") and f != abs_file_path
    ]
    assert len(temp_files) == 0


def test_save_file_security(project_dir: Path) -> None:
    """Test security checks in save_file."""
    # Try to write a file outside the project directory
    with pytest.raises(ValueError) as excinfo:
        save_file(
            "../outside_project.txt",
            "This should not be written",
            project_dir=project_dir,
        )

    # Verify the security error message
    assert "Security error" in str(excinfo.value)
    assert "outside the project directory" in str(excinfo.value)


def test_read_file(project_dir: Path) -> None:
    """Test reading from a file."""
    # Create an absolute path for test file creation
    abs_file_path = project_dir / TEST_FILE

    # Create a test file
    with open(abs_file_path, "w", encoding="utf-8") as f:
        f.write(TEST_CONTENT)

    # Test reading the file
    content = read_file(str(TEST_FILE), project_dir=project_dir)

    # Verify the content
    assert content == TEST_CONTENT


def test_read_file_not_found(project_dir: Path) -> None:
    """Test reading a file that doesn't exist."""
    non_existent_file = TEST_DIR / "non_existent.txt"

    # Ensure the file doesn't exist
    abs_non_existent = project_dir / non_existent_file
    if abs_non_existent.exists():
        abs_non_existent.unlink()

    # Test reading a non-existent file
    with pytest.raises(FileNotFoundError):
        read_file(str(non_existent_file), project_dir=project_dir)


def test_read_file_security(project_dir: Path) -> None:
    """Test security checks in read_file."""
    # Try to read a file outside the project directory
    with pytest.raises(ValueError) as excinfo:
        read_file("../outside_project.txt", project_dir=project_dir)

    # Verify the security error message
    assert "Security error" in str(excinfo.value)
    assert "outside the project directory" in str(excinfo.value)


def test_delete_file(project_dir: Path) -> None:
    """Test deleting a file."""
    # Create a file to delete
    file_to_delete = TEST_DIR / "file_to_delete.txt"
    abs_file_path = project_dir / file_to_delete

    # Ensure the file exists
    with open(abs_file_path, "w", encoding="utf-8") as f:
        f.write("This file will be deleted.")

    # Verify the file exists
    assert abs_file_path.exists()

    # Test deleting the file
    result = delete_file(str(file_to_delete), project_dir=project_dir)

    # Verify the file was deleted
    assert result is True
    assert not abs_file_path.exists()


def test_delete_file_not_found(project_dir: Path) -> None:
    """Test deleting a file that doesn't exist."""
    non_existent_file = TEST_DIR / "non_existent_file.txt"

    # Ensure the file doesn't exist
    abs_non_existent = project_dir / non_existent_file
    if abs_non_existent.exists():
        abs_non_existent.unlink()

    # Test deleting a non-existent file
    with pytest.raises(FileNotFoundError):
        delete_file(str(non_existent_file), project_dir=project_dir)


def test_delete_file_is_directory(project_dir: Path) -> None:
    """Test attempting to delete a directory."""
    # Create a directory
    dir_path = TEST_DIR / "test_directory"
    abs_dir_path = project_dir / dir_path

    # Ensure the directory exists
    abs_dir_path.mkdir(exist_ok=True)

    # Verify the directory exists
    assert abs_dir_path.exists()
    assert abs_dir_path.is_dir()

    # Test attempting to delete a directory
    with pytest.raises(IsADirectoryError):
        delete_file(str(dir_path), project_dir=project_dir)

    # Verify the directory still exists
    assert abs_dir_path.exists()

    # Clean up
    shutil.rmtree(abs_dir_path)


def test_delete_file_security(project_dir: Path) -> None:
    """Test security checks in delete_file."""
    # Try to delete a file outside the project directory
    with pytest.raises(ValueError) as excinfo:
        delete_file("../outside_project.txt", project_dir=project_dir)

    # Verify the security error message
    assert "Security error" in str(excinfo.value)
    assert "outside the project directory" in str(excinfo.value)


def test_append_file(project_dir: Path) -> None:
    """Test appending content to a file."""
    # Create absolute path for test file
    abs_file_path = project_dir / TEST_FILE

    # Create initial content
    initial_content = "Initial content.\n"
    with open(abs_file_path, "w", encoding="utf-8") as f:
        f.write(initial_content)

    # Append content to the file
    append_content = "Appended content."
    result = append_file(str(TEST_FILE), append_content, project_dir=project_dir)

    # Verify the file was updated
    assert result is True
    assert abs_file_path.exists()

    # Verify the combined content
    expected_content = initial_content + append_content
    with open(abs_file_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert content == expected_content


def test_append_file_empty(project_dir: Path) -> None:
    """Test appending to an empty file."""
    # Create the empty file
    empty_file = TEST_DIR / "empty_file.txt"
    abs_file_path = project_dir / empty_file
    with open(abs_file_path, "w", encoding="utf-8") as f:
        pass  # Create an empty file

    # Append content to the empty file
    append_content = "Content added to empty file."
    result = append_file(str(empty_file), append_content, project_dir=project_dir)

    # Verify the file was updated
    assert result is True
    assert abs_file_path.exists()

    # Verify the content
    with open(abs_file_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert content == append_content


def test_append_file_not_found(project_dir: Path) -> None:
    """Test appending to a file that doesn't exist."""
    non_existent_file = TEST_DIR / "non_existent_append.txt"

    # Ensure the file doesn't exist
    abs_non_existent = project_dir / non_existent_file
    if abs_non_existent.exists():
        abs_non_existent.unlink()

    # Test appending to a non-existent file
    with pytest.raises(FileNotFoundError):
        append_file(str(non_existent_file), "This should fail", project_dir=project_dir)


def test_append_file_is_directory(project_dir: Path) -> None:
    """Test attempting to append to a directory."""
    # Create a directory
    dir_path = TEST_DIR / "test_append_directory"
    abs_dir_path = project_dir / dir_path

    # Ensure the directory exists
    abs_dir_path.mkdir(exist_ok=True)

    # Verify the directory exists
    assert abs_dir_path.exists()
    assert abs_dir_path.is_dir()

    # Test attempting to append to a directory
    with pytest.raises(IsADirectoryError):
        append_file(str(dir_path), "This should fail", project_dir=project_dir)

    # Clean up
    shutil.rmtree(abs_dir_path)


def test_append_file_security(project_dir: Path) -> None:
    """Test security checks in append_file."""
    # Try to append to a file outside the project directory
    with pytest.raises(ValueError) as excinfo:
        append_file(
            "../outside_project.txt", "This should fail", project_dir=project_dir
        )

    # Verify the security error message
    assert "Security error" in str(excinfo.value)
    assert "outside the project directory" in str(excinfo.value)


# --- Step 1: read_file parameter validation tests ---


def test_read_file_rejects_one_sided_range_start_only(project_dir: Path) -> None:
    """start_line without end_line must raise ValueError."""
    abs_file_path = project_dir / TEST_FILE
    abs_file_path.write_text("line1\nline2\nline3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="both be provided or both omitted"):
        read_file(str(TEST_FILE), project_dir, start_line=1, end_line=None)


def test_read_file_rejects_one_sided_range_end_only(project_dir: Path) -> None:
    """end_line without start_line must raise ValueError."""
    abs_file_path = project_dir / TEST_FILE
    abs_file_path.write_text("line1\nline2\nline3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="both be provided or both omitted"):
        read_file(str(TEST_FILE), project_dir, start_line=None, end_line=5)


def test_read_file_rejects_zero_start_line(project_dir: Path) -> None:
    """start_line=0 must raise ValueError (lines are 1-based)."""
    abs_file_path = project_dir / TEST_FILE
    abs_file_path.write_text("line1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be >= 1"):
        read_file(str(TEST_FILE), project_dir, start_line=0, end_line=5)


def test_read_file_rejects_zero_end_line(project_dir: Path) -> None:
    """end_line=0 must raise ValueError (lines are 1-based)."""
    abs_file_path = project_dir / TEST_FILE
    abs_file_path.write_text("line1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be >= 1"):
        read_file(str(TEST_FILE), project_dir, start_line=1, end_line=0)


def test_read_file_rejects_negative_start_line(project_dir: Path) -> None:
    """Negative start_line must raise ValueError."""
    abs_file_path = project_dir / TEST_FILE
    abs_file_path.write_text("line1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be >= 1"):
        read_file(str(TEST_FILE), project_dir, start_line=-1, end_line=5)


def test_read_file_rejects_negative_end_line(project_dir: Path) -> None:
    """Negative end_line must raise ValueError."""
    abs_file_path = project_dir / TEST_FILE
    abs_file_path.write_text("line1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be >= 1"):
        read_file(str(TEST_FILE), project_dir, start_line=1, end_line=-1)


def test_read_file_rejects_end_before_start(project_dir: Path) -> None:
    """end_line < start_line must raise ValueError."""
    abs_file_path = project_dir / TEST_FILE
    abs_file_path.write_text("line1\nline2\nline3\nline4\nline5\n", encoding="utf-8")
    with pytest.raises(ValueError, match="end_line .* must be >= start_line"):
        read_file(str(TEST_FILE), project_dir, start_line=5, end_line=3)


def test_read_file_rejects_non_int_start_line(project_dir: Path) -> None:
    """String start_line must raise ValueError."""
    abs_file_path = project_dir / TEST_FILE
    abs_file_path.write_text("line1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be integers"):
        read_file(str(TEST_FILE), project_dir, start_line="1", end_line=5)  # type: ignore[arg-type]


def test_read_file_rejects_non_int_end_line(project_dir: Path) -> None:
    """Float end_line must raise ValueError."""
    abs_file_path = project_dir / TEST_FILE
    abs_file_path.write_text("line1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be integers"):
        read_file(str(TEST_FILE), project_dir, start_line=1, end_line=2.5)  # type: ignore[arg-type]


def test_read_file_accepts_bool_true_as_line_1(project_dir: Path) -> None:
    """bool True (== 1) is a valid int, reads line 1."""
    abs_file_path = project_dir / TEST_FILE
    abs_file_path.write_text("line1\nline2\n", encoding="utf-8")
    # Should NOT raise — True is int subclass with value 1
    content = read_file(str(TEST_FILE), project_dir, start_line=True, end_line=True)
    assert isinstance(content, str)


def test_read_file_rejects_bool_false_as_zero(project_dir: Path) -> None:
    """bool False (== 0) fails the >= 1 check."""
    abs_file_path = project_dir / TEST_FILE
    abs_file_path.write_text("line1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be >= 1"):
        read_file(str(TEST_FILE), project_dir, start_line=False, end_line=5)


def test_read_file_unchanged_without_new_params(project_dir: Path) -> None:
    """Calling without new params returns full content unchanged."""
    abs_file_path = project_dir / TEST_FILE
    abs_file_path.write_text(TEST_CONTENT, encoding="utf-8")
    content = read_file(str(TEST_FILE), project_dir)
    assert content == TEST_CONTENT


# --- Step 2: Line-range slicing tests ---


def _write_multiline_file(project_dir: Path, lines: int = 10) -> Path:
    """Helper: create a file with numbered lines."""
    abs_path = project_dir / TEST_FILE
    content = "".join(f"line {i}\n" for i in range(1, lines + 1))
    abs_path.write_text(content, encoding="utf-8")
    return abs_path


def test_read_file_slicing_basic(project_dir: Path) -> None:
    """Slice lines 3-5 from a 10-line file."""
    _write_multiline_file(project_dir)
    content = read_file(
        str(TEST_FILE), project_dir, start_line=3, end_line=5, with_line_numbers=False
    )
    assert content == "line 3\nline 4\nline 5\n"


def test_read_file_slicing_single_line(project_dir: Path) -> None:
    """Slice a single line."""
    _write_multiline_file(project_dir)
    content = read_file(
        str(TEST_FILE), project_dir, start_line=1, end_line=1, with_line_numbers=False
    )
    assert content == "line 1\n"


def test_read_file_slicing_clamp_past_eof(project_dir: Path) -> None:
    """end_line beyond file length returns available lines."""
    _write_multiline_file(project_dir)
    content = read_file(
        str(TEST_FILE), project_dir, start_line=8, end_line=20, with_line_numbers=False
    )
    assert content == "line 8\nline 9\nline 10\n"


def test_read_file_slicing_start_past_eof(project_dir: Path) -> None:
    """start_line beyond file length returns empty string."""
    _write_multiline_file(project_dir)
    content = read_file(
        str(TEST_FILE),
        project_dir,
        start_line=100,
        end_line=200,
        with_line_numbers=False,
    )
    assert content == ""


def test_read_file_slicing_exact_eof(project_dir: Path) -> None:
    """Slice the very last line of a 10-line file."""
    _write_multiline_file(project_dir)
    content = read_file(
        str(TEST_FILE), project_dir, start_line=10, end_line=10, with_line_numbers=False
    )
    assert content == "line 10\n"


def test_read_file_full_read_unchanged(project_dir: Path) -> None:
    """Full read (no range) returns identical content to direct file read."""
    abs_path = _write_multiline_file(project_dir)
    expected = abs_path.read_text(encoding="utf-8")
    content = read_file(str(TEST_FILE), project_dir)
    assert content == expected


def test_read_file_no_trailing_newline(project_dir: Path) -> None:
    """File without trailing newline: slicing last line preserves that."""
    abs_path = project_dir / TEST_FILE
    abs_path.write_text("line 1\nline 2\nline 3", encoding="utf-8")
    content = read_file(
        str(TEST_FILE), project_dir, start_line=3, end_line=3, with_line_numbers=False
    )
    assert content == "line 3"


def test_read_file_slicing_large_file(project_dir: Path) -> None:
    """Slicing a large file returns only the requested lines."""
    _write_multiline_file(project_dir, lines=10000)
    content = read_file(
        str(TEST_FILE),
        project_dir,
        start_line=5000,
        end_line=5002,
        with_line_numbers=False,
    )
    assert content == "line 5000\nline 5001\nline 5002\n"


def test_append_file_large_content(project_dir: Path) -> None:
    """Test appending large content to a file."""
    # Create absolute path for test file
    large_file = TEST_DIR / "large_file.txt"
    abs_file_path = project_dir / large_file

    # Create initial content
    initial_content = "Initial line.\n"
    with open(abs_file_path, "w", encoding="utf-8") as f:
        f.write(initial_content)

    # Create large content to append (100 lines)
    large_content = ""
    for i in range(1, 101):
        large_content += f"Line {i} of appended content.\n"

    # Append large content to the file
    result = append_file(str(large_file), large_content, project_dir=project_dir)

    # Verify the file was updated
    assert result is True
    assert abs_file_path.exists()

    # Verify the combined content
    expected_content = initial_content + large_content
    with open(abs_file_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert content == expected_content


# --- Step 3: with_line_numbers formatting tests ---


def test_read_file_line_numbers_default_on_for_range(project_dir: Path) -> None:
    """Default with_line_numbers is True when a range is given."""
    abs_path = project_dir / TEST_FILE
    abs_path.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")
    content = read_file(str(TEST_FILE), project_dir, start_line=2, end_line=3)
    assert content == "2→line 2\n3→line 3\n"


def test_read_file_line_numbers_default_off_for_full_read(project_dir: Path) -> None:
    """Default with_line_numbers is False for full reads (no range)."""
    abs_path = project_dir / TEST_FILE
    abs_path.write_text("line 1\nline 2\n", encoding="utf-8")
    content = read_file(str(TEST_FILE), project_dir)
    assert content == "line 1\nline 2\n"


def test_read_file_line_numbers_explicit_false_on_range(project_dir: Path) -> None:
    """Explicit with_line_numbers=False suppresses prefixes on range."""
    abs_path = project_dir / TEST_FILE
    abs_path.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")
    content = read_file(
        str(TEST_FILE), project_dir, start_line=2, end_line=3, with_line_numbers=False
    )
    assert content == "line 2\nline 3\n"


def test_read_file_line_numbers_explicit_true_on_full_read(project_dir: Path) -> None:
    """Explicit with_line_numbers=True adds prefixes on full read."""
    abs_path = project_dir / TEST_FILE
    abs_path.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")
    content = read_file(str(TEST_FILE), project_dir, with_line_numbers=True)
    assert content == "1→line 1\n2→line 2\n3→line 3\n"


def test_read_file_line_numbers_dynamic_width_narrow(project_dir: Path) -> None:
    """Lines 1-9 use width 1."""
    abs_path = project_dir / TEST_FILE
    content_lines = "".join(f"L{i}\n" for i in range(1, 10))
    abs_path.write_text(content_lines, encoding="utf-8")
    content = read_file(str(TEST_FILE), project_dir, start_line=1, end_line=9)
    assert content.startswith("1→L1\n")
    assert "9→L9\n" in content


def test_read_file_line_numbers_dynamic_width_wide(project_dir: Path) -> None:
    """Lines 99-101 use width 3 (right-aligned)."""
    abs_path = project_dir / TEST_FILE
    content_lines = "".join(f"L{i}\n" for i in range(1, 102))
    abs_path.write_text(content_lines, encoding="utf-8")
    content = read_file(str(TEST_FILE), project_dir, start_line=99, end_line=101)
    assert content == " 99→L99\n100→L100\n101→L101\n"


def test_read_file_slicing_start_past_eof_with_line_numbers(
    project_dir: Path,
) -> None:
    """start_line past EOF with line numbers still returns empty string."""
    _write_multiline_file(project_dir)
    content = read_file(
        str(TEST_FILE),
        project_dir,
        start_line=100,
        end_line=200,
        with_line_numbers=True,
    )
    assert content == ""


# --- CRLF normalization tests ---


def test_save_file_normalizes_crlf(project_dir: Path) -> None:
    """save_file normalizes CRLF to LF, avoiding double carriage returns."""
    result = save_file(str(TEST_FILE), "line1\r\nline2\r\n", project_dir=project_dir)
    assert result is True

    abs_file_path = project_dir / TEST_FILE
    raw = abs_file_path.read_bytes()
    assert b"\r\r\n" not in raw, "Double carriage return found — normalization failed"


def test_append_file_normalizes_crlf(project_dir: Path) -> None:
    """append_file normalizes CRLF to LF, avoiding double carriage returns."""
    abs_file_path = project_dir / TEST_FILE
    abs_file_path.write_text("existing\n", encoding="utf-8")

    result = append_file(str(TEST_FILE), "new\r\nline\r\n", project_dir=project_dir)
    assert result is True

    raw = abs_file_path.read_bytes()
    assert b"\r\r\n" not in raw, "Double carriage return found — normalization failed"


def test_append_file_validation_via_validate_save_parameters(
    project_dir: Path,
) -> None:
    """append_file still raises ValueError for invalid content after refactor."""
    abs_file_path = project_dir / TEST_FILE
    abs_file_path.write_text("existing\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Content must be a string"):
        append_file(str(TEST_FILE), 12345, project_dir=project_dir)


# --- Step 1: delete_directory util tests ---


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
