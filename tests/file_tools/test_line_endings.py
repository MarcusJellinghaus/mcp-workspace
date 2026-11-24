"""Tests for line-ending detection and selection."""

from pathlib import Path

import pytest
from git import Repo

import mcp_workspace.git_operations
from mcp_workspace.file_tools.line_endings import (
    describe_line_endings,
    target_newline,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a\r\nb\r\n", "2 lines, CRLF"),
        ("a\nb", "2 lines, LF"),
        ("a\rb\r", "2 lines, CR"),
        ("a\r\nb\n", "2 lines, mixed"),
        ("abc", "1 line"),
        ("a\x0b\x0cb c", "1 line"),
        ("äöü\r\n€\r\n日本語", "3 lines, CRLF"),
    ],
)
def test_describe_line_endings(text: str, expected: str) -> None:
    """Only CR, LF and CRLF break lines; the style is named when present."""
    assert describe_line_endings(text) == expected


def _record_lookups(
    monkeypatch: pytest.MonkeyPatch, value: str | None = "lf"
) -> list[str]:
    """Patch the gitattributes lookup to return value and record calls.

    Recording rather than raising: target_newline swallows lookup errors.
    """
    calls: list[str] = []

    def _lookup(rel_path: str, project_dir: Path) -> str | None:
        calls.append(rel_path)
        return value

    monkeypatch.setattr(mcp_workspace.git_operations, "get_eol_attribute", _lookup)
    return calls


@pytest.mark.parametrize(
    ("existing", "expected"),
    [
        (b"a\r\nb\r\n", "\r\n"),
        (b"a\nb\n", "\n"),
        (b"a\rb\r", "\r"),
        (b"a\r\nb\r\nc\n", "\r\n"),
        (b"a\nb\nc\r\n", "\n"),
        (b"a\rb\rc\n", "\r"),
    ],
)
def test_target_newline_keeps_existing_style(
    existing: bytes, expected: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An existing file keeps its (majority) ending without a git lookup."""
    calls = _record_lookups(monkeypatch)

    assert target_newline(existing, "x.txt", tmp_path) == expected
    assert not calls


def test_target_newline_tie_uses_lf(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A tie between endings without an eol= rule falls back to LF."""
    calls = _record_lookups(monkeypatch, None)

    assert target_newline(b"a\r\nb\nc", "x.txt", tmp_path) == "\n"
    assert target_newline(b"a\r\nb\nc\rd", "x.txt", tmp_path) == "\n"
    assert calls == ["x.txt", "x.txt"]


NO_BREAKS = [None, b"", b"no breaks"]


def _patch_lookup(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
    def _lookup(rel_path: str, project_dir: Path) -> str | None:
        return value

    monkeypatch.setattr(mcp_workspace.git_operations, "get_eol_attribute", _lookup)


@pytest.mark.parametrize("existing", NO_BREAKS)
@pytest.mark.parametrize(("value", "expected"), [("lf", "\n"), ("crlf", "\r\n")])
def test_target_newline_follows_eol_attribute(
    existing: bytes | None,
    value: str,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Without line breaks to copy, eol=lf / eol=crlf decides."""
    _patch_lookup(monkeypatch, value)

    assert target_newline(existing, "x.txt", tmp_path) == expected


@pytest.mark.parametrize("existing", NO_BREAKS)
@pytest.mark.parametrize("value", ["unspecified", None, "set"])
def test_target_newline_other_eol_values_use_lf(
    existing: bytes | None,
    value: str | None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Any eol value other than lf / crlf gives LF."""
    _patch_lookup(monkeypatch, value)

    assert target_newline(existing, "x.txt", tmp_path) == "\n"


@pytest.mark.parametrize("existing", NO_BREAKS)
def test_target_newline_lookup_error_uses_lf(
    existing: bytes | None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A failing lookup gives LF."""

    def _raise(rel_path: str, project_dir: Path) -> str | None:
        raise RuntimeError("git exploded")

    monkeypatch.setattr(mcp_workspace.git_operations, "get_eol_attribute", _raise)

    assert target_newline(existing, "x.txt", tmp_path) == "\n"


@pytest.mark.parametrize("existing", NO_BREAKS)
def test_target_newline_without_project_dir_uses_lf(
    existing: bytes | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without a project directory there is no lookup; the result is LF."""
    calls = _record_lookups(monkeypatch)

    assert target_newline(existing, "x.txt", None) == "\n"
    assert not calls


@pytest.mark.git_integration
def test_target_newline_reads_gitattributes(tmp_path: Path) -> None:
    """A real repository's eol=crlf rule is read."""
    Repo.init(tmp_path).close()
    (tmp_path / ".gitattributes").write_bytes(b"*.bat eol=crlf\n")

    assert target_newline(None, "x.bat", tmp_path) == "\r\n"


def test_target_newline_outside_repository_uses_lf(tmp_path: Path) -> None:
    """A folder that is not a repository gives LF."""
    assert target_newline(None, "x.sh", tmp_path) == "\n"
