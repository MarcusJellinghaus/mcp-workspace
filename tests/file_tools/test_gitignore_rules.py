"""Tests for gitignore rule loading: nested .gitignore files and info/exclude."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from igittigitt import IgnoreParser

from mcp_workspace.file_tools.directory_utils import (
    _rules_for,
    is_path_gitignored,
    list_files,
)

MODULE_LOGGER = "mcp_workspace.file_tools.directory_utils"


@contextmanager
def _spy_parsed_files() -> Iterator[list[Path]]:
    """Record every rule file parsed while the context is active."""
    original = IgnoreParser.parse_rule_file
    parsed: list[Path] = []
    with patch.object(
        IgnoreParser, "parse_rule_file", autospec=True, side_effect=original
    ) as spy:
        yield parsed
    parsed.extend(Path(call.args[1]) for call in spy.call_args_list)


def _write(path: Path, content: str) -> None:
    """Write content to path, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_nested_gitignore_applies_below_its_directory(tmp_path: Path) -> None:
    """A .gitignore in a subdirectory applies to that directory and below."""
    _write(tmp_path / "sub" / ".gitignore", "*.tmp\n")

    assert is_path_gitignored("sub/x.tmp", tmp_path) is True
    assert is_path_gitignored("sub/deep/x.tmp", tmp_path) is True
    assert is_path_gitignored("x.tmp", tmp_path) is False


def test_deeper_gitignore_wins(tmp_path: Path) -> None:
    """A deeper .gitignore overrides a shallower one."""
    _write(tmp_path / ".gitignore", "*.log\n")
    _write(tmp_path / "sub" / ".gitignore", "!keep.log\n")

    assert is_path_gitignored("sub/keep.log", tmp_path) is False
    assert is_path_gitignored("sub/x.log", tmp_path) is True
    assert is_path_gitignored("keep.log", tmp_path) is True


def test_no_reinclude_inside_excluded_directory(tmp_path: Path) -> None:
    """A negation cannot re-include a path inside an excluded directory."""
    _write(tmp_path / ".gitignore", "secret/\n!secret/keep.txt\n")
    _write(tmp_path / "secret" / "keep.txt", "x")

    assert is_path_gitignored("secret/keep.txt", tmp_path) is True


def test_gitignore_inside_ignored_directory_is_not_read(tmp_path: Path) -> None:
    """A .gitignore inside an ignored directory is never parsed."""
    _write(tmp_path / ".gitignore", "build/\n")
    _write(tmp_path / "build" / ".gitignore", "!*\n")
    _write(tmp_path / "build" / "a", "x")

    with _spy_parsed_files() as parsed:
        assert is_path_gitignored("build/a", tmp_path) is True

    assert tmp_path / ".gitignore" in parsed
    assert tmp_path / "build" / ".gitignore" not in parsed


def test_info_exclude_is_applied(tmp_path: Path) -> None:
    """.git/info/exclude is applied, below the root .gitignore in precedence."""
    _write(tmp_path / ".git" / "info" / "exclude", "*.bak\n")

    assert is_path_gitignored("a.bak", tmp_path) is True

    _write(tmp_path / ".gitignore", "!keep.bak\n")

    assert is_path_gitignored("keep.bak", tmp_path) is False
    assert is_path_gitignored("x.bak", tmp_path) is True


def test_info_exclude_of_worktree(tmp_path: Path) -> None:
    """A worktree's .git file leads via commondir to the shared info/exclude."""
    common = tmp_path / "common"
    worktree_git = common / "worktrees" / "wt"
    _write(worktree_git / "commondir", "../..\n")
    _write(common / "info" / "exclude", "*.bak\n")
    project = tmp_path / "proj"
    _write(project / ".git", f"gitdir: {worktree_git.as_posix()}\n")

    assert is_path_gitignored("a.bak", project) is True


def test_info_exclude_of_submodule(tmp_path: Path) -> None:
    """A submodule's relative gitdir without commondir holds its info/exclude."""
    _write(
        tmp_path / "super" / ".git" / "modules" / "sub" / "info" / "exclude", "*.bak\n"
    )
    project = tmp_path / "super" / "sub"
    _write(project / ".git", "gitdir: ../.git/modules/sub\n")

    assert is_path_gitignored("a.bak", project) is True


def test_git_file_without_gitdir_line(tmp_path: Path) -> None:
    """A .git file without a gitdir line is tolerated."""
    _write(tmp_path / ".git", "not a gitdir pointer\n")

    assert is_path_gitignored("a.bak", tmp_path) is False


def test_nothing_outside_project_dir_is_read(tmp_path: Path) -> None:
    """Rules above project_dir are not read, and a path leaving it is not ignored."""
    _write(tmp_path / ".gitignore", "*.log\n")
    project = tmp_path / "proj"
    project.mkdir()

    with _spy_parsed_files() as parsed:
        assert is_path_gitignored("../x.log", project) is False

    assert all(p.is_relative_to(project) for p in parsed)


def test_unreadable_rule_file_logs_one_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A rule file that cannot be read is skipped with a single warning."""
    _write(tmp_path / ".gitignore", "*.log\n")

    with (
        patch.object(
            IgnoreParser,
            "parse_rule_file",
            autospec=True,
            side_effect=OSError("unreadable"),
        ),
        caplog.at_level(logging.WARNING, logger=MODULE_LOGGER),
    ):
        assert is_path_gitignored("a.log", tmp_path) is False

    warnings = [
        r
        for r in caplog.records
        if r.name == MODULE_LOGGER and r.levelno == logging.WARNING
    ]
    assert len(warnings) == 1


def test_rule_loading_logs_nothing_above_debug(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Rule loading emits no INFO+ records (issue #48)."""
    with caplog.at_level(logging.INFO, logger=MODULE_LOGGER):
        _rules_for(tmp_path / "sub", tmp_path)  # no rule files
        is_path_gitignored("sub/a.log", tmp_path)
        _write(tmp_path / ".git" / "info" / "exclude", "*.bak\n")
        _write(tmp_path / ".gitignore", "*.log\n")
        _write(tmp_path / "sub" / ".gitignore", "*.tmp\n")
        _rules_for(tmp_path / "sub", tmp_path)  # every rule file present
        is_path_gitignored("sub/a.log", tmp_path)
        list_files(".", tmp_path)
        list_files("sub", tmp_path)

    assert [r for r in caplog.records if r.name == MODULE_LOGGER] == []


def test_project_root_is_never_ignored(tmp_path: Path) -> None:
    """The project root itself is not ignored, even by a catch-all rule."""
    _write(tmp_path / ".gitignore", "*\n")

    assert is_path_gitignored(".", tmp_path) is False


def test_listing_omits_ignored_names_in_every_directory(tmp_path: Path) -> None:
    """Root rules apply to listings of the root and of subdirectories (#392)."""
    _write(tmp_path / ".gitignore", "secret/\n*.env\n")
    _write(tmp_path / "secret" / "key.txt", "x")
    _write(tmp_path / "sub" / "a.env", "x")
    _write(tmp_path / "sub" / "ok.txt", "x")

    files = list_files(".", tmp_path)

    assert "secret/key.txt" not in files
    assert "sub/a.env" not in files
    assert "sub/ok.txt" in files
    assert list_files("secret", tmp_path) == []
    assert list_files("sub", tmp_path) == ["sub/ok.txt"]


def test_listing_applies_nested_gitignore(tmp_path: Path) -> None:
    """A nested .gitignore hides matching files below its own directory only."""
    _write(tmp_path / "sub" / ".gitignore", "*.tmp\n")
    _write(tmp_path / "sub" / "x.tmp", "x")
    _write(tmp_path / "x.tmp", "x")

    files = list_files(".", tmp_path)

    assert "sub/x.tmp" not in files
    assert "x.tmp" in files


def test_listing_siblings_do_not_share_rules(tmp_path: Path) -> None:
    """Rules of one directory's .gitignore do not leak into a sibling."""
    _write(tmp_path / "a" / ".gitignore", "*.txt\n")
    _write(tmp_path / "a" / "x.txt", "x")
    _write(tmp_path / "b" / "x.txt", "x")

    files = list_files(".", tmp_path)

    assert "a/x.txt" not in files
    assert "b/x.txt" in files


def test_listing_deeper_negation_reincludes(tmp_path: Path) -> None:
    """A deeper .gitignore negation re-includes a file the root ignores."""
    _write(tmp_path / ".gitignore", "*.log\n")
    _write(tmp_path / "sub" / ".gitignore", "!keep.log\n")
    _write(tmp_path / "sub" / "keep.log", "x")
    _write(tmp_path / "sub" / "x.log", "x")

    files = list_files(".", tmp_path)

    assert "sub/keep.log" in files
    assert "sub/x.log" not in files


def test_listing_does_not_read_gitignore_in_ignored_directory(
    tmp_path: Path,
) -> None:
    """The walk prunes an ignored directory without reading its .gitignore."""
    _write(tmp_path / ".gitignore", "build/\n")
    _write(tmp_path / "build" / ".gitignore", "!*\n")
    _write(tmp_path / "build" / "a", "x")

    with _spy_parsed_files() as parsed:
        files = list_files(".", tmp_path)

    assert "build/a" not in files
    assert tmp_path / "build" / ".gitignore" not in parsed


def test_listing_without_gitignore_lists_everything(tmp_path: Path) -> None:
    """use_gitignore=False lists every file outside .git, ignored ones included."""
    _write(tmp_path / ".gitignore", "secret/\n*.env\n")
    _write(tmp_path / "secret" / "key.txt", "x")
    _write(tmp_path / "sub" / "a.env", "x")
    _write(tmp_path / ".git" / "config", "x")

    files = list_files(".", tmp_path, use_gitignore=False)

    assert set(files) == {".gitignore", "secret/key.txt", "sub/a.env"}
