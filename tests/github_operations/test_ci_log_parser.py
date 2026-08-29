"""Tests for ci_log_parser module."""

from unittest.mock import MagicMock, patch

import pytest

from mcp_workspace.github_operations.ci_log_parser import (
    _extract_failed_step_log,
    _find_log_content,
    _parse_groups,
    _strip_timestamps,
    build_ci_error_details,
    truncate_ci_details,
)


class TestTruncateCiDetails:
    """Tests for truncate_ci_details."""

    def test_short_content_unchanged(self) -> None:
        """Content within limits is returned unchanged."""
        content = "line1\nline2\nline3"
        result = truncate_ci_details(content, max_lines=10)
        assert result == content

    def test_exact_limit_unchanged(self) -> None:
        """Content exactly at limit is returned unchanged."""
        lines = [f"line{i}" for i in range(10)]
        content = "\n".join(lines)
        result = truncate_ci_details(content, max_lines=10)
        assert result == content

    def test_over_limit_truncated(self) -> None:
        """Content over limit is truncated with head + tail."""
        lines = [f"line{i}" for i in range(20)]
        content = "\n".join(lines)
        result = truncate_ci_details(content, max_lines=10, head_lines=3)
        assert "line0" in result
        assert "line1" in result
        assert "line2" in result
        assert "line19" in result
        assert "omitted" in result

    def test_truncation_marker_shows_count(self) -> None:
        """Truncation marker uses square bracket format from p_coder."""
        lines = [f"line{i}" for i in range(30)]
        content = "\n".join(lines)
        result = truncate_ci_details(content, max_lines=10, head_lines=3)
        assert (
            "[... 20 lines omitted: showing 10 of 30 — raise max_log_lines for more ...]"
            in result
        )
        # No extra blank lines around marker
        result_lines = result.split("\n")
        marker_idx = next(i for i, line in enumerate(result_lines) if "omitted" in line)
        # Line before marker should not be blank
        assert result_lines[marker_idx - 1] != ""
        # Line after marker should not be blank
        assert result_lines[marker_idx + 1] != ""

    def test_empty_input_returns_empty(self) -> None:
        """Empty string input returns empty string."""
        assert truncate_ci_details("") == ""

    @pytest.mark.parametrize("max_lines", [10, 3, 0, -5])
    def test_small_cap_truncates_without_duplicating(self, max_lines: int) -> None:
        """A small, zero or negative cap still truncates, and the marker counts hold."""
        content = "\n".join(f"line{i}" for i in range(300))
        result = truncate_ci_details(content, max_lines=max_lines)

        expected = max(0, max_lines)
        result_lines = result.split("\n")
        # Kept lines plus the marker; at 0 and -5 the marker stands alone.
        assert len(result_lines) == expected + 1
        assert f"showing {expected} of 300" in result
        assert f"[... {300 - expected} lines omitted:" in result
        assert 300 - expected >= 0

        body = [line for line in result_lines if "lines omitted:" not in line]
        assert len(set(body)) == len(body)


class TestStripTimestamps:
    """Tests for _strip_timestamps."""

    def test_strips_github_actions_timestamps(self) -> None:
        """GitHub Actions timestamps are removed from log lines."""
        log = "2024-01-15T10:30:45.1234567Z Run npm test\n2024-01-15T10:30:46.9876543Z FAIL src/test.js"
        result = _strip_timestamps(log)
        assert result == "Run npm test\nFAIL src/test.js"

    def test_preserves_lines_without_timestamps(self) -> None:
        """Lines without timestamps are preserved as-is."""
        log = "no timestamp here\nalso no timestamp"
        result = _strip_timestamps(log)
        assert result == log

    def test_handles_empty_string(self) -> None:
        """Empty string input returns empty string."""
        assert _strip_timestamps("") == ""

    def test_strips_timestamp_after_ansi_codes(self) -> None:
        """Timestamps after ANSI escape codes are stripped."""
        log = "\x1b[36m2024-01-15T10:30:45.1234567Z some content"
        result = _strip_timestamps(log)
        assert "2024-01-15T10:30:45" not in result
        assert "some content" in result


class TestParseGroups:
    """Tests for _parse_groups."""

    def test_parses_single_group(self) -> None:
        """Single group is parsed correctly."""
        log = "##[group]Setup\ninstalling deps\ndone\n##[endgroup]"
        groups = _parse_groups(log)
        assert len(groups) >= 1
        group_names = [g[0] for g in groups]
        assert "Setup" in group_names

    def test_parses_multiple_groups(self) -> None:
        """Multiple groups are parsed in order."""
        log = "##[group]Setup\nstep1\n##[endgroup]\n##[group]Test\nstep2\n##[endgroup]"
        groups = _parse_groups(log)
        group_names = [g[0] for g in groups if g[0]]
        assert "Setup" in group_names
        assert "Test" in group_names

    def test_handles_content_outside_groups(self) -> None:
        """Content after endgroup is attached to preceding group."""
        log = "##[group]Inside\ncontent\n##[endgroup]\nafter"
        groups = _parse_groups(log)
        # "after" should be attached to the preceding "Inside" group
        inside_group = [g for g in groups if g[0] == "Inside"]
        assert len(inside_group) == 1
        assert "after" in inside_group[0][1]

    def test_handles_empty_string(self) -> None:
        """Empty string returns minimal result."""
        groups = _parse_groups("")
        # Should return at least one group with empty content
        assert isinstance(groups, list)

    def test_mid_line_group_marker_not_treated_as_group(self) -> None:
        """Line containing ##[group] mid-line is NOT treated as group start."""
        log = "##[group]Real Group\ncontent\n##[endgroup]\nsee ##[group] docs for info"
        groups = _parse_groups(log)
        group_names = [g[0] for g in groups]
        assert "Real Group" in group_names
        # The mid-line ##[group] should NOT create a new group
        assert " docs for info" not in group_names


class TestExtractFailedStepLog:
    """Tests for _extract_failed_step_log."""

    def test_extracts_matching_step(self) -> None:
        """Matching step group content is extracted."""
        log = "##[group]Setup\nsetup line\n##[endgroup]\n##[group]Run tests\nerror here\n##[endgroup]"
        result = _extract_failed_step_log(log, "Run tests")
        assert "error here" in result

    def test_case_insensitive_match(self) -> None:
        """Step name matching is case-insensitive."""
        log = "##[group]Run Tests\nerror line\n##[endgroup]"
        result = _extract_failed_step_log(log, "run tests")
        assert "error line" in result

    def test_exact_match_preferred_over_contains(self) -> None:
        """Exact match is preferred over contains match."""
        log = (
            "##[group]Run tests\nexact match content\n##[endgroup]\n"
            "##[group]Run tests and lint\ncontains match content\n##[endgroup]"
        )
        result = _extract_failed_step_log(log, "Run tests")
        assert "exact match content" in result
        assert "contains match content" not in result

    def test_prefix_match_preferred_over_contains(self) -> None:
        """Prefix match is preferred over contains match."""
        log = (
            "##[group]Run tests (ubuntu)\nprefix match content\n##[endgroup]\n"
            "##[group]Setup Run tests\ncontains match content\n##[endgroup]"
        )
        result = _extract_failed_step_log(log, "Run tests")
        assert "prefix match content" in result
        assert "contains match content" not in result

    def test_error_fallback_when_no_group_matches(self) -> None:
        """Returns error group content when no group name matches."""
        log = (
            "##[group]Setup\nsetup line\n##[endgroup]\n"
            "##[group]Build\n##[error]build failed\ndetail line\n##[endgroup]"
        )
        result = _extract_failed_step_log(log, "nonexistent step")
        assert "--- Build ---" in result
        assert "build failed" in result
        assert "detail line" in result

    def test_returns_empty_when_no_match_and_no_errors(self) -> None:
        """Returns empty string when no group matches AND no ##[error] lines."""
        log = "##[group]Setup\nsetup line\n##[endgroup]\n##[group]Build\nbuild line\n##[endgroup]"
        result = _extract_failed_step_log(log, "nonexistent step")
        assert result == ""


class TestFindLogContent:
    """Tests for _find_log_content."""

    def test_finds_by_suffix_match(self) -> None:
        """Tier 1: _{job_name}.txt suffix match works."""
        logs = {"0_test-job.txt": "test output"}
        result = _find_log_content(logs, "test-job", 3, "Run tests")
        assert result == "test output"

    def test_finds_by_old_format(self) -> None:
        """Tier 2: {job_name}/{step_number}_{step_name}.txt exact path."""
        logs = {"test-job/3_Run tests.txt": "test output"}
        result = _find_log_content(logs, "test-job", 3, "Run tests")
        assert result == "test output"

    def test_returns_empty_for_no_match(self) -> None:
        """Returns empty string when no logs match."""
        logs = {"other-job/1_step.txt": "content"}
        result = _find_log_content(logs, "nonexistent-job", 1, "step")
        assert result == ""

    def test_returns_empty_for_empty_logs(self) -> None:
        """Returns empty string for empty logs dict."""
        result = _find_log_content({}, "job", 1, "step")
        assert result == ""

    def test_suffix_match_preferred_over_old_format(self) -> None:
        """Suffix match takes priority over old format matching."""
        logs = {
            "Job Name/3_Run tests.txt": "old format match",
            "other/0_Job Name.txt": "suffix match",
        }
        result = _find_log_content(logs, "Job Name", 3, "Run tests")
        assert result == "suffix match"


class TestBuildCiErrorDetails:
    """Tests for build_ci_error_details."""

    def test_returns_none_for_no_jobs(self) -> None:
        """Returns None when no jobs in status result."""
        ci_manager = MagicMock()
        result = build_ci_error_details(ci_manager, {"jobs": []})
        assert result is None

    def test_returns_none_for_no_failed_jobs(self) -> None:
        """Returns None when all jobs succeeded."""
        ci_manager = MagicMock()
        status = {"jobs": [{"conclusion": "success", "name": "test"}]}
        result = build_ci_error_details(ci_manager, status)
        assert result is None

    def test_returns_report_when_no_logs_available(self) -> None:
        """Returns report with job info and fallback text when no logs."""
        ci_manager = MagicMock()
        ci_manager.get_run_logs.return_value = {}
        status = {
            "run": {"url": "https://github.com/org/repo/actions/runs/123"},
            "jobs": [
                {
                    "conclusion": "failure",
                    "name": "test-job",
                    "id": 456,
                    "run_id": 123,
                    "steps": [
                        {"name": "Run tests", "number": 3, "conclusion": "failure"}
                    ],
                }
            ],
        }
        result = build_ci_error_details(ci_manager, status)
        assert result is not None
        assert "test-job" in result
        assert "(logs not available locally)" in result

    def test_builds_report_for_failed_job(self) -> None:
        """Builds error details report for a failed job with logs."""
        ci_manager = MagicMock()
        ci_manager.get_run_logs.return_value = {
            "0_test-job.txt": "2024-01-15T10:30:45.1234567Z Error: test failed"
        }
        status = {
            "run": {"url": "https://github.com/org/repo/actions/runs/123"},
            "jobs": [
                {
                    "conclusion": "failure",
                    "name": "test-job",
                    "id": 456,
                    "run_id": 123,
                    "steps": [
                        {"name": "Run tests", "number": 3, "conclusion": "failure"}
                    ],
                }
            ],
        }
        result = build_ci_error_details(ci_manager, status)
        assert result is not None
        assert "test-job" in result
        assert "Run tests" in result
        assert "## CI Failure Summary" in result

    def test_limits_run_ids_to_three(self) -> None:
        """Only fetches logs for up to 3 unique run IDs."""
        ci_manager = MagicMock()
        ci_manager.get_run_logs.return_value = {}
        jobs = [
            {
                "conclusion": "failure",
                "name": f"job-{i}",
                "id": i + 100,
                "run_id": i,
                "steps": [],
            }
            for i in range(5)
        ]
        status = {"run": {"url": "https://example.com/runs/1"}, "jobs": jobs}
        build_ci_error_details(ci_manager, status)
        assert ci_manager.get_run_logs.call_count == 3

    def test_handles_log_fetch_failure(self) -> None:
        """Returns report with job info even when log fetch fails."""
        ci_manager = MagicMock()
        ci_manager.get_run_logs.side_effect = RuntimeError("API error")
        status = {
            "run": {"url": "https://github.com/org/repo/actions/runs/123"},
            "jobs": [
                {
                    "conclusion": "failure",
                    "name": "test-job",
                    "id": 456,
                    "run_id": 123,
                    "steps": [],
                }
            ],
        }
        result = build_ci_error_details(ci_manager, status)
        assert result is not None
        assert "test-job" in result

    def test_truncates_long_output(self) -> None:
        """Output is truncated when exceeding max_lines."""
        ci_manager = MagicMock()
        # Create a large log with a matching group
        inner_lines = "\n".join([f"line {i}" for i in range(500)])
        long_log = f"##[group]Run tests\n{inner_lines}\n##[endgroup]"
        ci_manager.get_run_logs.return_value = {"0_test-job.txt": long_log}
        status = {
            "run": {"url": "https://github.com/org/repo/actions/runs/123"},
            "jobs": [
                {
                    "conclusion": "failure",
                    "name": "test-job",
                    "id": 456,
                    "run_id": 123,
                    "steps": [
                        {"name": "Run tests", "number": 3, "conclusion": "failure"}
                    ],
                }
            ],
        }
        result = build_ci_error_details(ci_manager, status, max_lines=20)
        assert result is not None
        assert "omitted" in result

    def test_both_marker_sites_use_one_spelling(self) -> None:
        """`truncate_ci_details` and `build_ci_error_details` emit the same marker shape."""
        ci_manager = MagicMock()
        inner_lines = "\n".join([f"line {i}" for i in range(500)])
        long_log = f"##[group]Run tests\n{inner_lines}\n##[endgroup]"
        ci_manager.get_run_logs.return_value = {"0_test-job.txt": long_log}
        status = {
            "run": {"url": "https://github.com/org/repo/actions/runs/123"},
            "jobs": [
                {
                    "conclusion": "failure",
                    "name": "test-job",
                    "id": 456,
                    "run_id": 123,
                    "steps": [
                        {"name": "Run tests", "number": 3, "conclusion": "failure"}
                    ],
                }
            ],
        }
        # max_lines=60 leaves this job a per-job budget large enough to keep
        # some log lines, so the inline marker fires instead of the job being
        # dropped into the "Other failed jobs" list.
        build_result = build_ci_error_details(ci_manager, status, max_lines=60)
        truncate_result = truncate_ci_details(long_log, max_lines=20)

        assert build_result is not None
        for result in (build_result, truncate_result):
            assert "lines omitted: showing " in result
            assert "raise max_log_lines for more" in result

    def test_run_url_in_output(self) -> None:
        """Run URL is included in the output report."""
        ci_manager = MagicMock()
        ci_manager.get_run_logs.return_value = {}
        status = {
            "run": {"url": "https://github.com/org/repo/actions/runs/789"},
            "jobs": [
                {
                    "conclusion": "failure",
                    "name": "lint",
                    "id": 100,
                    "run_id": 789,
                    "steps": [],
                }
            ],
        }
        result = build_ci_error_details(ci_manager, status)
        assert result is not None
        assert "https://github.com/org/repo/actions/runs/789" in result

    def test_per_job_line_budget_truncation(self) -> None:
        """Jobs exceeding line budget show truncation message."""
        ci_manager = MagicMock()
        # Many failed jobs — some should be truncated
        jobs = [
            {
                "conclusion": "failure",
                "name": f"job-{i}",
                "id": i + 100,
                "run_id": 1,
                "steps": [{"name": "step", "number": 1, "conclusion": "failure"}],
            }
            for i in range(20)
        ]
        ci_manager.get_run_logs.return_value = {}
        status = {
            "run": {"url": "https://example.com/runs/1"},
            "jobs": jobs,
        }
        result = build_ci_error_details(ci_manager, status, max_lines=30)
        assert result is not None
        # Should show some jobs and indicate truncation
        assert "job-0" in result
        assert (
            "## Other failed jobs (logs omitted — raise max_log_lines to include them)"
            in result
        )
