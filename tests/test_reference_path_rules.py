"""Reference file tools apply the same path rules as the workspace file tools."""

import os
from pathlib import Path

import pytest

from mcp_workspace import server_reference_tools
from mcp_workspace.reference_projects import ReferenceProject
from mcp_workspace.server_reference_tools import (
    list_reference_directory,
    read_reference_file,
    search_reference_files,
)

SECRET_TEXT = "SECRET=1\n"
CONFIG_TEXT = "[remote]\n\turl = https://example.invalid/r\n"


@pytest.fixture(name="reference")
def reference_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Reference project with a git directory, ignored files and a plain file."""
    ref = tmp_path / "ref"
    (ref / ".git").mkdir(parents=True)
    (ref / ".git" / "config").write_text(CONFIG_TEXT, encoding="utf-8")
    (ref / "secret").mkdir()
    (ref / "secret" / "key.txt").write_text(SECRET_TEXT, encoding="utf-8")
    (ref / ".gitignore").write_text(".env\nsecret/\n", encoding="utf-8")
    (ref / ".env").write_text(SECRET_TEXT, encoding="utf-8")
    (ref / "plain.txt").write_text("plain\n", encoding="utf-8")
    monkeypatch.setattr(
        server_reference_tools,
        "_reference_projects",
        {"ref": ReferenceProject(name="ref", path=ref)},
    )
    return ref


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.",
        ".env::$DATA",
        "secret/key.txt",
        ".git/config",
        ".GIT/config",
        ".git./config",
    ],
)
async def test_protected_paths_refused(reference: Path, path: str) -> None:
    with pytest.raises(ValueError) as excinfo:
        await read_reference_file("ref", path)
    assert "SECRET" not in str(excinfo.value)
    assert "example.invalid" not in str(excinfo.value)


@pytest.mark.asyncio
async def test_absolute_gitignored_path_refused(reference: Path) -> None:
    with pytest.raises(ValueError, match="excluded by .gitignore"):
        await read_reference_file("ref", str(reference / ".env"))


@pytest.mark.asyncio
async def test_link_to_gitignored_file_refused(reference: Path) -> None:
    try:
        os.symlink(reference / ".env", reference / "envlink")
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    with pytest.raises(ValueError, match="excluded by .gitignore"):
        await read_reference_file("ref", "envlink")
    result = await search_reference_files("ref", pattern="SECRET")
    assert result["details"] == []


@pytest.mark.asyncio
async def test_ordinary_file_still_reads(reference: Path) -> None:
    assert await read_reference_file("ref", "plain.txt") == "plain\n"
    assert await read_reference_file("ref", ".gitignore") == ".env\nsecret/\n"


@pytest.mark.asyncio
async def test_search_skips_protected_paths(reference: Path) -> None:
    secret_hits = await search_reference_files("ref", pattern="SECRET")
    config_hits = await search_reference_files("ref", pattern="example.invalid")
    assert secret_hits["details"] == []
    assert config_hits["details"] == []
    assert "skipped_files" not in secret_hits


@pytest.mark.asyncio
async def test_glob_search_skips_protected_paths(reference: Path) -> None:
    result = await search_reference_files("ref", glob="**/*")
    assert sorted(result["files"]) == [".gitignore", "plain.txt"]


@pytest.mark.asyncio
async def test_listing_skips_protected_paths(reference: Path) -> None:
    assert sorted(await list_reference_directory("ref")) == [".gitignore", "plain.txt"]
