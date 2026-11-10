"""Tests for the edit_file MCP server tool (async + locking)."""

import asyncio
from collections.abc import Generator
from pathlib import Path

import pytest

from tests.conftest import ToolMap

# Test constants
TEST_DIR = Path("testdata/test_file_tools")
TEST_FILE = TEST_DIR / "test_edit_api_file.txt"
TEST_CONTENT = """\
This is a test file for the edit_file API.
Line 2 with some content.
Line 3 with different content.
Line 4 to be edited.
Line 5 stays the same."""


@pytest.fixture(autouse=True)
def setup_test_file(project_dir: Path) -> Generator[None, None, None]:
    """Setup and teardown for each test."""
    test_dir_path = project_dir / TEST_DIR
    test_dir_path.mkdir(parents=True, exist_ok=True)

    yield

    # Teardown
    for suffix in ["test_edit_api_file.txt", "lock_test_a.txt", "lock_test_b.txt"]:
        path = project_dir / TEST_DIR / suffix
        if path.exists():
            path.unlink()


@pytest.mark.asyncio
async def test_basic_edit_via_server(project_dir: Path, tools: ToolMap) -> None:
    """Basic edit via server tool returns diff string."""
    tools["save_file"](str(TEST_FILE), TEST_CONTENT)

    result = await tools["edit_file"](
        file_path=str(TEST_FILE),
        old_string="Line 4 to be edited.",
        new_string="Line 4 has been modified.",
    )

    assert isinstance(result, str)
    assert "+Line 4 has been modified." in result
    assert "-Line 4 to be edited." in result

    # Verify file changed on disk
    content = (project_dir / TEST_FILE).read_text(encoding="utf-8")
    assert "Line 4 has been modified." in content
    assert "Line 4 to be edited." not in content


@pytest.mark.asyncio
async def test_text_not_found_raises_value_error(
    project_dir: Path, tools: ToolMap
) -> None:
    """Text not found raises ValueError."""
    tools["save_file"](str(TEST_FILE), TEST_CONTENT)

    with pytest.raises(ValueError, match="Text not found"):
        await tools["edit_file"](
            file_path=str(TEST_FILE),
            old_string="This text does not exist.",
            new_string="Should not appear.",
        )


@pytest.mark.asyncio
async def test_replace_all_via_server(project_dir: Path, tools: ToolMap) -> None:
    """replace_all=True replaces all occurrences."""
    repeated_content = "aaa bbb aaa ccc aaa"
    tools["save_file"](str(TEST_FILE), repeated_content)

    result = await tools["edit_file"](
        file_path=str(TEST_FILE),
        old_string="aaa",
        new_string="zzz",
        replace_all=True,
    )

    assert isinstance(result, str)
    content = (project_dir / TEST_FILE).read_text(encoding="utf-8")
    assert content == "zzz bbb zzz ccc zzz"


@pytest.mark.asyncio
async def test_empty_old_string_inserts_at_beginning(
    project_dir: Path, tools: ToolMap
) -> None:
    """Empty old_string inserts new_string at beginning of file."""
    tools["save_file"](str(TEST_FILE), TEST_CONTENT)

    result = await tools["edit_file"](
        file_path=str(TEST_FILE),
        old_string="",
        new_string="# Header\n",
    )

    assert isinstance(result, str)
    content = (project_dir / TEST_FILE).read_text(encoding="utf-8")
    assert content.startswith("# Header\n")


@pytest.mark.asyncio
async def test_gitignore_check_rejects_ignored_files(
    project_dir: Path, tools: ToolMap
) -> None:
    """Gitignored files are rejected."""
    # Create a .gitignore that excludes .log files
    (project_dir / ".gitignore").write_text("*.log\n", encoding="utf-8")
    log_file = project_dir / "debug.log"
    log_file.write_text("some log content", encoding="utf-8")

    with pytest.raises(ValueError, match="excluded by .gitignore"):
        await tools["edit_file"](
            file_path="debug.log",
            old_string="some",
            new_string="other",
        )

    # Cleanup
    (project_dir / ".gitignore").unlink()


@pytest.mark.asyncio
async def test_locking_serializes_same_file_edits(
    project_dir: Path, tools: ToolMap
) -> None:
    """Two concurrent async edits to same file both succeed (no lost writes)."""
    lock_file = TEST_DIR / "lock_test_a.txt"
    tools["save_file"](str(lock_file), "line_a\nline_b\n")

    async def edit_a() -> None:
        result: str = await tools["edit_file"](
            file_path=str(lock_file),
            old_string="line_a",
            new_string="LINE_A",
        )
        assert isinstance(result, str)

    async def edit_b() -> None:
        result: str = await tools["edit_file"](
            file_path=str(lock_file),
            old_string="line_b",
            new_string="LINE_B",
        )
        assert isinstance(result, str)

    await asyncio.gather(edit_a(), edit_b())

    content = (project_dir / lock_file).read_text(encoding="utf-8")
    assert "LINE_A" in content
    assert "LINE_B" in content


@pytest.mark.asyncio
async def test_different_files_not_blocked(project_dir: Path, tools: ToolMap) -> None:
    """Concurrent edits to different files don't interfere."""
    file_a = TEST_DIR / "lock_test_a.txt"
    file_b = TEST_DIR / "lock_test_b.txt"
    tools["save_file"](str(file_a), "content_a\n")
    tools["save_file"](str(file_b), "content_b\n")

    async def edit_a() -> None:
        result: str = await tools["edit_file"](
            file_path=str(file_a),
            old_string="content_a",
            new_string="CONTENT_A",
        )
        assert isinstance(result, str)

    async def edit_b() -> None:
        result: str = await tools["edit_file"](
            file_path=str(file_b),
            old_string="content_b",
            new_string="CONTENT_B",
        )
        assert isinstance(result, str)

    await asyncio.gather(edit_a(), edit_b())

    content_a = (project_dir / file_a).read_text(encoding="utf-8")
    content_b = (project_dir / file_b).read_text(encoding="utf-8")
    assert "CONTENT_A" in content_a
    assert "CONTENT_B" in content_b
