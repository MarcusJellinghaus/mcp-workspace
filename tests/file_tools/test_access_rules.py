"""Tests for the .mcp-file-access rules file parser."""

import logging
import sys
from pathlib import Path

import pytest

from mcp_workspace.file_tools.access_rules import (
    ACCESS_RULES_FILE,
    READ_ONLY,
    READ_WRITE,
    AccessRule,
    AccessRules,
    access_rules_warning,
    load_access_rules,
    validate_access_rules,
)

MODULE_LOGGER = "mcp_workspace.file_tools.access_rules"


def _write_rules(project_dir: Path, content: str) -> None:
    """Write the rules file into project_dir."""
    (project_dir / ACCESS_RULES_FILE).write_text(content, encoding="utf-8")


def _load(project_dir: Path, content: str) -> AccessRules:
    """Write the rules file and load it."""
    _write_rules(project_dir, content)
    return load_access_rules(project_dir)


def test_absent_file_gives_no_rules_and_no_problems(tmp_path: Path) -> None:
    """Without a rules file there are no rules and nothing is wrong."""
    rules = load_access_rules(tmp_path)

    assert rules == AccessRules()
    assert validate_access_rules(tmp_path) == []
    assert rules.match("anything.txt") is None


def test_both_levels_parse_skipping_comments_and_blanks(tmp_path: Path) -> None:
    """Both levels parse; comments, blank lines and extra whitespace are fine."""
    rules = _load(
        tmp_path,
        "# header comment\n"
        "\n"
        "read-write    /.scratch/\n"
        "   \n"
        "  # indented comment\n"
        "read-only\t/.mcp.json\n",
    )

    assert rules.problems == ()
    assert rules.rules == (
        AccessRule(level=READ_WRITE, pattern="/.scratch/", line=3),
        AccessRule(level=READ_ONLY, pattern="/.mcp.json", line=6),
    )
    assert validate_access_rules(tmp_path) == []


def test_last_match_wins_specific_after_general(tmp_path: Path) -> None:
    """A later, more specific rule overrides an earlier directory rule."""
    rules = _load(tmp_path, "read-only config/\nread-write config/local.json\n")

    matched = rules.match("config/local.json")
    assert matched is not None
    assert matched.level == READ_WRITE
    other = rules.match("config/other.json")
    assert other is not None
    assert other.level == READ_ONLY


def test_last_match_wins_general_after_specific(tmp_path: Path) -> None:
    """A later directory rule overrides an earlier, more specific rule."""
    rules = _load(tmp_path, "read-write config/local.json\nread-only config/\n")

    matched = rules.match("config/local.json")
    assert matched is not None
    assert matched.level == READ_ONLY
    assert matched.line == 2


def test_match_directory_and_contents(tmp_path: Path) -> None:
    """An anchored directory rule matches the directory and everything below."""
    rules = _load(tmp_path, "read-write /.scratch/\n")

    assert rules.match(".scratch", is_dir=True) is not None
    assert rules.match(".scratch/a/b.py") is not None
    assert rules.match("other") is None
    assert rules.match("sub/.scratch/x.py") is None


@pytest.mark.skipif(sys.platform != "win32", reason="case-insensitive on win32 only")
def test_match_is_case_insensitive_on_win32(tmp_path: Path) -> None:
    """On Windows, rule matching ignores letter case."""
    rules = _load(tmp_path, "read-only /.mcp.json\n")

    assert rules.match(".MCP.json") is not None


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("read-only a\nreadonly /b\n", "line 2: unknown level 'readonly'"),
        ("read-only\n", "line 1: expected '<level> <pattern>'"),
        ("read-write !keep.txt\n", "line 1: negation '!' is not allowed"),
        ("read-only #comment\n", "line 1: invalid pattern '#comment'"),
        ("read-only foo\\\n", "line 1: invalid pattern 'foo\\'"),
    ],
)
def test_invalid_line_gives_problem_and_no_rules(
    tmp_path: Path, content: str, expected: str
) -> None:
    """An invalid line is reported with its line number and drops every rule."""
    rules = _load(tmp_path, content)

    assert rules.problems == (expected,)
    assert rules.rules == ()
    assert rules.match("a") is None
    assert validate_access_rules(tmp_path) == [expected]


def test_all_invalid_lines_are_reported(tmp_path: Path) -> None:
    """Every invalid line is reported, not just the first."""
    rules = _load(tmp_path, "bogus a\nread-only /ok\nread-write !b\n")

    assert rules.problems == (
        "line 1: unknown level 'bogus'",
        "line 3: negation '!' is not allowed",
    )
    assert rules.rules == ()


def test_non_utf8_file_is_invalid(tmp_path: Path) -> None:
    """A rules file that is not valid UTF-8 is reported as such."""
    (tmp_path / ACCESS_RULES_FILE).write_bytes(b"read-only /caf\xe9\n")

    rules = load_access_rules(tmp_path)

    assert rules.problems == ("is not valid UTF-8",)
    assert rules.rules == ()


def test_utf8_bom_is_accepted(tmp_path: Path) -> None:
    """A UTF-8 byte order mark does not corrupt the first line."""
    (tmp_path / ACCESS_RULES_FILE).write_bytes(b"\xef\xbb\xbfread-only /a\n")

    rules = load_access_rules(tmp_path)

    assert rules.problems == ()
    assert rules.rules == (AccessRule(level=READ_ONLY, pattern="/a", line=1),)


def test_directory_at_rules_path_is_invalid(tmp_path: Path) -> None:
    """A directory named like the rules file is reported, not ignored."""
    (tmp_path / ACCESS_RULES_FILE).mkdir()

    rules = load_access_rules(tmp_path)

    assert rules.problems == ("is a directory",)
    assert rules.rules == ()


def test_problem_is_logged_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Loading the same invalid file twice logs a single warning."""
    _write_rules(tmp_path, "readonly /a\n")

    with caplog.at_level(logging.WARNING, logger=MODULE_LOGGER):
        load_access_rules(tmp_path)
        load_access_rules(tmp_path)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "line 1: unknown level 'readonly'" in warnings[0].getMessage()


def test_leads_into_anchored_literal_prefix(tmp_path: Path) -> None:
    """An anchored rule leads into every directory on its literal prefix."""
    rules = _load(tmp_path, "read-only /logs/sub/*.log\n")

    assert rules.leads_into("logs") is True
    assert rules.leads_into("logs/sub") is True
    assert rules.leads_into("other") is False
    assert rules.leads_into("log") is False


@pytest.mark.parametrize("pattern", ["*.log", "**/x", "logs/"])
def test_leads_into_false_for_unanchored_or_wildcard_start(
    tmp_path: Path, pattern: str
) -> None:
    """Unanchored rules and rules starting with a wildcard lead nowhere."""
    rules = _load(tmp_path, f"read-only {pattern}\n")

    assert rules.problems == ()
    assert rules.leads_into("logs") is False
    assert rules.leads_into("x") is False


def test_leads_into_false_without_rules() -> None:
    """No rules, no leads."""
    assert AccessRules().leads_into("logs") is False


def test_access_rules_warning() -> None:
    """The warning line is None when valid and names every problem otherwise."""
    assert access_rules_warning([]) is None

    warning = access_rules_warning(["line 1: a", "line 2: b"])

    assert warning is not None
    assert warning.startswith("WARNING: .mcp-file-access is invalid (")
    assert "line 1: a; line 2: b" in warning
    assert warning.endswith("- writes are refused and no gitignored path is exposed.")
