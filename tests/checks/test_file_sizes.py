"""Tests for file_sizes check module."""

import os
from pathlib import Path
from typing import List

import pytest

from mcp_workspace.checks.file_sizes import (
    _MAX_REPORT_VIOLATIONS,
    _MAX_STALE_ENTRIES,
    CheckResult,
    FileMetrics,
    check_file_sizes,
    count_lines,
    load_allowlist,
    render_allowlist,
    render_output,
)


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    """Create a minimal project directory with a .gitignore."""
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("__pycache__/\n*.pyc\n", encoding="utf-8")
    return tmp_path


def _write_file(base: Path, rel: str, lines: int) -> Path:
    """Helper: write a file with *lines* lines of text."""
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(f"line {i}" for i in range(lines)) + "\n", encoding="utf-8")
    return p


def _metrics(count: int) -> List[FileMetrics]:
    """Helper: build *count* violations, largest first."""
    return [
        FileMetrics(path=Path(f"src/f{i}.py"), line_count=1000 - i)
        for i in range(count)
    ]


class TestCountLines:
    """Tests for count_lines."""

    def test_counts_lines(self, tmp_path: Path) -> None:
        p = tmp_path / "a.py"
        p.write_text("a\nb\nc\n", encoding="utf-8")
        assert count_lines(p) == 3

    def test_empty_file(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.py"
        p.write_text("", encoding="utf-8")
        assert count_lines(p) == 0

    def test_binary_returns_negative(self, tmp_path: Path) -> None:
        p = tmp_path / "binary.bin"
        p.write_bytes(bytes(range(256)))
        assert count_lines(p) == -1

    def test_nonexistent_returns_negative(self, tmp_path: Path) -> None:
        assert count_lines(tmp_path / "nope.py") == -1


class TestLoadAllowlist:
    """Tests for load_allowlist."""

    def test_missing_file(self, tmp_path: Path) -> None:
        assert load_allowlist(tmp_path / "nope") == set()

    def test_parses_entries(self, tmp_path: Path) -> None:
        p = tmp_path / ".large-files-allowlist"
        p.write_text(
            "# comment\n" "\n" "src/big.py\n" "tests/huge.py  # inline comment\n",
            encoding="utf-8",
        )
        result = load_allowlist(p)
        assert result == {"src/big.py", "tests/huge.py"}

    def test_normalizes_backslashes(self, tmp_path: Path) -> None:
        p = tmp_path / "allowlist"
        p.write_text("src\\big.py\n", encoding="utf-8")
        assert "src/big.py" in load_allowlist(p)


class TestCheckFileSizes:
    """Tests for check_file_sizes."""

    def test_all_under_limit(self, project_dir: Path) -> None:
        _write_file(project_dir, "a.py", 10)
        _write_file(project_dir, "b.py", 5)
        result = check_file_sizes(project_dir, max_lines=100, allowlist=set())
        assert result.passed is True
        assert result.violations == []
        assert result.total_files_checked >= 2

    def test_violation_detected(self, project_dir: Path) -> None:
        _write_file(project_dir, "small.py", 5)
        _write_file(project_dir, "big.py", 200)
        result = check_file_sizes(project_dir, max_lines=100, allowlist=set())
        assert result.passed is False
        assert len(result.violations) == 1
        assert result.violations[0].line_count == 200

    def test_allowlisted_file_skipped(self, project_dir: Path) -> None:
        _write_file(project_dir, "big.py", 200)
        result = check_file_sizes(project_dir, max_lines=100, allowlist={"big.py"})
        assert result.passed is True
        assert result.allowlisted_count == 1

    def test_stale_allowlist_entry_missing_file(self, project_dir: Path) -> None:
        _write_file(project_dir, "a.py", 5)
        result = check_file_sizes(project_dir, max_lines=100, allowlist={"gone.py"})
        assert "gone.py" in result.stale_entries

    def test_stale_allowlist_entry_under_limit(self, project_dir: Path) -> None:
        _write_file(project_dir, "small.py", 5)
        result = check_file_sizes(project_dir, max_lines=100, allowlist={"small.py"})
        assert "small.py" in result.stale_entries

    def test_violations_sorted_descending(self, project_dir: Path) -> None:
        _write_file(project_dir, "a.py", 150)
        _write_file(project_dir, "b.py", 300)
        _write_file(project_dir, "c.py", 200)
        result = check_file_sizes(project_dir, max_lines=100, allowlist=set())
        counts = [v.line_count for v in result.violations]
        assert counts == sorted(counts, reverse=True)


class TestRenderOutput:
    """Tests for render_output."""

    def test_passed(self) -> None:
        result = CheckResult(passed=True, total_files_checked=10)
        output = render_output(result, max_lines=600)
        assert "passed" in output
        assert "10" in output

    def test_failed(self) -> None:
        result = CheckResult(
            passed=False,
            violations=[FileMetrics(path=Path("src/big.py"), line_count=812)],
            total_files_checked=45,
        )
        output = render_output(result, max_lines=600)
        assert "failed" in output
        assert "src/big.py" in output
        assert "812" in output

    def test_stale_entries_shown(self) -> None:
        result = CheckResult(
            passed=True,
            total_files_checked=5,
            stale_entries=["old.py"],
        )
        output = render_output(result, max_lines=600)
        assert "Stale" in output
        assert "old.py" in output

    def test_allowlisted_count_shown(self) -> None:
        result = CheckResult(
            passed=True,
            total_files_checked=5,
            allowlisted_count=2,
        )
        output = render_output(result, max_lines=600)
        assert "Allowlisted" in output
        assert "2" in output

    def test_violations_capped_at_50(self) -> None:
        result = CheckResult(passed=False, violations=_metrics(845))
        output = render_output(result, max_lines=600)
        notice = "  ... showing 50 of 845 violations (largest first)"
        output_lines = output.splitlines()
        assert notice in output_lines
        item_lines = [line for line in output_lines if line.startswith("  - ")]
        assert len(item_lines) == 50
        # The notice follows the last item directly, then the blank line and remedy.
        notice_index = output_lines.index(notice)
        assert output_lines[notice_index - 1] == "  - src/f49.py: 951 lines"
        assert output_lines[notice_index + 1 :] == [
            "",
            "Consider refactoring these files or adding them to the allowlist.",
        ]
        assert "845 file(s) exceed" in output
        assert "src/f50.py" not in output

    def test_stale_entries_capped_at_50(self) -> None:
        result = CheckResult(
            passed=True,
            total_files_checked=5,
            stale_entries=[f"old{i:03d}.py" for i in range(312)],
        )
        output = render_output(result, max_lines=600)
        notice = "  ... showing 50 of 312 stale entries"
        assert notice in output
        assert "Stale allowlist entries (312):" in output
        assert output.splitlines()[-1] == notice
        assert "largest" not in output

    def test_both_caps_fire(self) -> None:
        result = CheckResult(
            passed=False,
            violations=_metrics(60),
            allowlisted_count=3,
            stale_entries=[f"old{i:03d}.py" for i in range(60)],
        )
        output = render_output(result, max_lines=600)
        notices = [line for line in output.splitlines() if "showing" in line]
        assert notices == [
            "  ... showing 50 of 60 violations (largest first)",
            "  ... showing 50 of 60 stale entries",
        ]
        assert "File size check failed: 60 file(s) exceed 600 lines" in output
        assert "Allowlisted files: 3" in output
        assert "Consider refactoring these files or adding them to the allowlist." in (
            output
        )
        # The notices must not name a tool parameter - the caps are internal.
        for notice in notices:
            assert "max_lines" not in notice
            assert "max_report" not in notice

    def test_exactly_50_no_notice(self) -> None:
        assert _MAX_REPORT_VIOLATIONS == 50
        assert _MAX_STALE_ENTRIES == 50
        result = CheckResult(
            passed=False,
            violations=_metrics(_MAX_REPORT_VIOLATIONS),
            stale_entries=[f"old{i:03d}.py" for i in range(_MAX_STALE_ENTRIES)],
        )
        output = render_output(result, max_lines=600)
        assert "showing" not in output
        item_lines = [line for line in output.splitlines() if line.startswith("  - ")]
        assert len(item_lines) == _MAX_REPORT_VIOLATIONS + _MAX_STALE_ENTRIES


class TestRenderAllowlist:
    """Tests for render_allowlist."""

    def test_render(self) -> None:
        violations = [
            FileMetrics(path=Path("src/a.py"), line_count=100),
            FileMetrics(path=Path("src/b.py"), line_count=200),
        ]
        output = render_allowlist(violations)
        assert "src/a.py" in output
        assert "src/b.py" in output
