"""Tests that the file-writing tools keep a file's line endings."""

from pathlib import Path

import pytest
from git import Repo

import mcp_workspace.git_operations
from mcp_workspace.file_tools import line_endings
from mcp_workspace.file_tools.edit_file import edit_file
from mcp_workspace.file_tools.file_operations import save_file


def _patch_lookup(monkeypatch: pytest.MonkeyPatch, value: str | None) -> list[str]:
    """Patch the gitattributes lookup to return value and record calls."""
    calls: list[str] = []

    def _lookup(rel_path: str, project_dir: Path) -> str | None:
        calls.append(rel_path)
        return value

    monkeypatch.setattr(mcp_workspace.git_operations, "get_eol_attribute", _lookup)
    return calls


@pytest.mark.parametrize("nl", [b"\n", b"\r\n", b"\r"])
def test_edit_file_keeps_style(
    nl: bytes, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """LF, CRLF and CR files keep their ending, multi-line new_string included."""
    calls = _patch_lookup(monkeypatch, "lf")
    (tmp_path / "f.txt").write_bytes(b"one" + nl + b"two" + nl + b"three" + nl)

    edit_file("f.txt", "two", "2a\n2b", project_dir=tmp_path)

    assert (tmp_path / "f.txt").read_bytes() == nl.join(
        [b"one", b"2a", b"2b", b"three", b""]
    )
    assert not calls


def test_edit_file_mixed_gets_majority(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A mixed file (2x CRLF, 1x LF) is written all CRLF."""
    _patch_lookup(monkeypatch, "lf")
    (tmp_path / "f.txt").write_bytes(b"a\r\nb\nc\r\n")

    edit_file("f.txt", "b", "x", project_dir=tmp_path)

    assert (tmp_path / "f.txt").read_bytes() == b"a\r\nx\r\nc\r\n"


@pytest.mark.parametrize("platform", ["\n", "\r\n"])
def test_edit_file_tie_uses_platform(
    platform: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A tie between endings falls back to the platform default."""
    monkeypatch.setattr(line_endings, "PLATFORM_NEWLINE", platform)
    _patch_lookup(monkeypatch, "lf")
    (tmp_path / "f.txt").write_bytes(b"a\r\nb\nc")

    edit_file("f.txt", "c", "x", project_dir=tmp_path)

    nl = platform.encode()
    assert (tmp_path / "f.txt").read_bytes() == b"a" + nl + b"b" + nl + b"x"


@pytest.mark.parametrize(("value", "nl"), [("lf", b"\n"), ("crlf", b"\r\n")])
def test_edit_file_no_breaks_follows_eol_attribute(
    value: str, nl: bytes, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A file without line breaks takes its ending from gitattributes eol=."""
    monkeypatch.setattr(line_endings, "PLATFORM_NEWLINE", "\r")
    calls = _patch_lookup(monkeypatch, value)
    (tmp_path / "f.txt").write_bytes(b"one two")

    edit_file("f.txt", " ", "\n", project_dir=tmp_path)

    assert (tmp_path / "f.txt").read_bytes() == b"one" + nl + b"two"
    assert calls == ["f.txt"]


@pytest.mark.parametrize(("value", "nl"), [("lf", b"\n"), ("crlf", b"\r\n")])
def test_edit_file_empty_file_prepend_follows_eol_attribute(
    value: str, nl: bytes, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Prepending to an empty file takes the ending from gitattributes eol=."""
    monkeypatch.setattr(line_endings, "PLATFORM_NEWLINE", "\r")
    _patch_lookup(monkeypatch, value)
    (tmp_path / "f.txt").write_bytes(b"")

    edit_file("f.txt", "", "a\nb\n", project_dir=tmp_path)

    assert (tmp_path / "f.txt").read_bytes() == b"a" + nl + b"b" + nl


def test_edit_file_diff_is_lf(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The returned diff of a CRLF file contains no CR."""
    _patch_lookup(monkeypatch, "lf")
    (tmp_path / "f.txt").write_bytes(b"a\r\nb\r\n")

    diff = edit_file("f.txt", "b", "x\ny", project_dir=tmp_path)

    assert "+x\n" in diff
    assert "\r" not in diff


def test_edit_file_already_applied_leaves_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An already-applied edit on a CRLF file neither writes nor looks up."""
    calls = _patch_lookup(monkeypatch, "lf")
    original = b"a\r\nnew\r\n"
    (tmp_path / "f.txt").write_bytes(original)

    result = edit_file("f.txt", "old", "new", project_dir=tmp_path)

    assert "already applied" in result
    assert (tmp_path / "f.txt").read_bytes() == original
    assert not calls


@pytest.mark.parametrize("nl", [b"\n", b"\r\n", b"\r"])
def test_save_file_keeps_style(
    nl: bytes, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Overwriting an LF, CRLF or CR file keeps its ending, without a lookup."""
    calls = _patch_lookup(monkeypatch, "lf")
    (tmp_path / "f.txt").write_bytes(b"old" + nl + b"text" + nl)

    save_file("f.txt", "a\nb\n", project_dir=tmp_path)

    assert (tmp_path / "f.txt").read_bytes() == b"a" + nl + b"b" + nl
    assert not calls


def test_save_file_crlf_content_onto_lf_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """CRLF content saved onto an existing LF file is written LF."""
    monkeypatch.setattr(line_endings, "PLATFORM_NEWLINE", "\r\n")
    _patch_lookup(monkeypatch, "crlf")
    (tmp_path / "f.txt").write_bytes(b"old\n")

    save_file("f.txt", "a\r\nb\r\n", project_dir=tmp_path)

    assert (tmp_path / "f.txt").read_bytes() == b"a\nb\n"


def test_save_file_mixed_gets_majority(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A mixed target (2x CRLF, 1x LF) is overwritten all CRLF."""
    monkeypatch.setattr(line_endings, "PLATFORM_NEWLINE", "\n")
    _patch_lookup(monkeypatch, "lf")
    (tmp_path / "f.txt").write_bytes(b"a\r\nb\nc\r\n")

    save_file("f.txt", "x\ny\n", project_dir=tmp_path)

    assert (tmp_path / "f.txt").read_bytes() == b"x\r\ny\r\n"


@pytest.mark.parametrize("platform", ["\n", "\r\n"])
def test_save_file_tie_uses_platform(
    platform: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A tie between endings in the target falls back to the platform default."""
    monkeypatch.setattr(line_endings, "PLATFORM_NEWLINE", platform)
    _patch_lookup(monkeypatch, "lf")
    (tmp_path / "f.txt").write_bytes(b"a\r\nb\n")

    save_file("f.txt", "x\ny\n", project_dir=tmp_path)

    nl = platform.encode()
    assert (tmp_path / "f.txt").read_bytes() == b"x" + nl + b"y" + nl


@pytest.mark.parametrize(
    ("name", "platform", "nl"),
    [("run.sh", "\r\n", b"\n"), ("run.bat", "\n", b"\r\n")],
)
def test_save_file_new_file_follows_gitattributes(
    name: str,
    platform: str,
    nl: bytes,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A new file in a repository follows .gitattributes eol= over the platform."""
    monkeypatch.setattr(line_endings, "PLATFORM_NEWLINE", platform)
    Repo.init(tmp_path).close()
    (tmp_path / ".gitattributes").write_bytes(b"*.sh eol=lf\n*.bat eol=crlf\n")

    save_file(name, "a\nb\n", project_dir=tmp_path)

    assert (tmp_path / name).read_bytes() == b"a" + nl + b"b" + nl


@pytest.mark.parametrize("platform", ["\n", "\r\n"])
def test_save_file_new_file_without_repo_uses_platform(
    platform: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A new file outside a repository gets the platform default."""
    monkeypatch.setattr(line_endings, "PLATFORM_NEWLINE", platform)

    save_file("sub/run.sh", "a\nb\n", project_dir=tmp_path)

    nl = platform.encode()
    assert (tmp_path / "sub" / "run.sh").read_bytes() == b"a" + nl + b"b" + nl


@pytest.mark.parametrize("existing", [b"", b"no breaks"])
@pytest.mark.parametrize(("value", "nl"), [("lf", b"\n"), ("crlf", b"\r\n")])
def test_save_file_no_breaks_follows_eol_attribute(
    existing: bytes,
    value: str,
    nl: bytes,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An existing empty file, or one without line breaks, follows eol=."""
    monkeypatch.setattr(line_endings, "PLATFORM_NEWLINE", "\r")
    calls = _patch_lookup(monkeypatch, value)
    (tmp_path / "f.txt").write_bytes(existing)

    save_file("f.txt", "a\nb\n", project_dir=tmp_path)

    assert (tmp_path / "f.txt").read_bytes() == b"a" + nl + b"b" + nl
    assert calls == ["f.txt"]


def test_save_file_overwrites_non_utf8_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Overwriting a file that is not valid UTF-8 succeeds."""
    _patch_lookup(monkeypatch, "lf")
    (tmp_path / "f.txt").write_bytes(b"\xff\xfe\x00bad\n")

    assert save_file("f.txt", "good\n", project_dir=tmp_path) is True

    assert (tmp_path / "f.txt").read_bytes() == b"good\n"
