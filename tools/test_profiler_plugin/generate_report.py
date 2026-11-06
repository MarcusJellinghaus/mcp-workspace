"""Generate human-readable text reports from profiling data.

This script:
1. Reads durations.json to find slow tests (>threshold)
2. Generates detailed text reports for each slow test
3. Creates a summary report of all profiling results
"""

import io
import json
import pstats
import sys
from pathlib import Path

# Configuration
PROF_OUTPUT_DIR = Path("docs/tests/performance_data/prof")
DURATIONS_FILE = PROF_OUTPUT_DIR / "durations.json"
SUMMARY_FILE = PROF_OUTPUT_DIR / "summary.txt"
TOP_N_FUNCTIONS = 50  # Number of functions to show in detailed reports


def sanitize_test_name(nodeid: str) -> str:
    """Convert pytest node ID to a safe filename.

    Must match the sanitization in test_profiler_plugin.py
    """
    safe_name = nodeid.replace("::", "__").replace("/", "_").replace("\\", "_")
    safe_name = safe_name.replace(".py", "")
    return safe_name


def generate_profile_report(
    prof_file: Path, output_file: Path, nodeid: str, duration: float
) -> None:
    """Generate a detailed, LLM-friendly text report from a .prof file."""
    stats = pstats.Stats(str(prof_file))
    stats.strip_dirs()

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("PYTEST PROFILE REPORT\n")
        f.write("=" * 80 + "\n\n")

        f.write(f"Test: {nodeid}\n")
        f.write(f"Duration: {duration:.3f} seconds\n")
        f.write(f"Profile file: {prof_file.name}\n\n")

        f.write("SUMMARY\n")
        f.write("-" * 80 + "\n")
        stream = io.StringIO()
        stats.stream = stream
        stats.print_stats(0)
        f.write(stream.getvalue() + "\n")

        f.write("TOP FUNCTIONS BY CUMULATIVE TIME\n")
        f.write("-" * 80 + "\n")
        f.write(
            "This shows functions sorted by total time spent, including time in called functions.\n\n"
        )
        stream = io.StringIO()
        stats.stream = stream
        stats.sort_stats(pstats.SortKey.CUMULATIVE)
        stats.print_stats(TOP_N_FUNCTIONS)
        f.write(stream.getvalue() + "\n")

        f.write("TOP FUNCTIONS BY INTERNAL TIME (TIME)\n")
        f.write("-" * 80 + "\n")
        f.write(
            "This shows functions sorted by time spent in the function itself (excluding subcalls).\n\n"
        )
        stream = io.StringIO()
        stats.stream = stream
        stats.sort_stats(pstats.SortKey.TIME)
        stats.print_stats(TOP_N_FUNCTIONS)
        f.write(stream.getvalue() + "\n")

        f.write("CALLER INFORMATION (Top 20)\n")
        f.write("-" * 80 + "\n")
        f.write("This shows which functions called the top functions.\n\n")
        stream = io.StringIO()
        stats.stream = stream
        stats.sort_stats(pstats.SortKey.CUMULATIVE)
        stats.print_callers(20)
        f.write(stream.getvalue())


def create_summary_report(
    durations_data: dict[str, object], slow_tests: list[tuple[str, float]]
) -> None:
    """Create a summary report of all profiling results."""
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("PYTEST PROFILING SUMMARY\n")
        f.write("=" * 80 + "\n\n")

        total_tests = durations_data.get("total_tests", 0)
        threshold = durations_data.get("threshold_seconds", 1.0)
        slow_count = len(slow_tests)

        f.write("STATISTICS\n")
        f.write("-" * 80 + "\n")
        f.write(f"Total tests profiled: {total_tests}\n")
        f.write(f"Slow test threshold: >{threshold} seconds\n")
        f.write(f"Slow tests found: {slow_count}\n\n")

        if slow_tests:
            f.write("SLOW TESTS (sorted by duration)\n")
            f.write("-" * 80 + "\n")
            f.write(f"{'Duration':<12} {'Test'}\n")
            f.write("-" * 80 + "\n")
            for nodeid, duration in slow_tests:
                f.write(f"{duration:>8.3f}s    {nodeid}\n")
            f.write("\n")
        else:
            f.write(f"No slow tests found (all tests completed in <{threshold}s).\n\n")

        f.write("OUTPUT FILES\n")
        f.write("-" * 80 + "\n")
        f.write(f"Profile data directory: {PROF_OUTPUT_DIR}\n\n")
        f.write("Generated files:\n")
        f.write("  - *.prof files: Binary profile data for ALL tests\n")
        f.write("  - *_report.txt: Detailed text reports for slow tests only\n")
        f.write("  - durations.json: Machine-readable test timing data\n")
        f.write("  - summary.txt: This file\n\n")

        f.write("ANALYZING RESULTS\n")
        f.write("-" * 80 + "\n")
        f.write("1. Check this summary for an overview of slow tests\n")
        f.write("2. Read individual *_report.txt files for detailed analysis\n")
        f.write("3. Look for functions with high 'cumtime' or 'tottime' values\n")
        f.write("4. Use the caller information to understand the call chain\n\n")


def main() -> int:
    """Main report generation logic."""
    print("Reading test durations...")

    if not DURATIONS_FILE.exists():
        print(f"ERROR: {DURATIONS_FILE} not found!")
        print("Make sure pytest ran successfully with the profiling plugin.")
        return 1

    with open(DURATIONS_FILE) as f:
        durations_data: dict[str, object] = json.load(f)

    threshold = durations_data.get("threshold_seconds", 1.0)
    durations: dict[str, float] = durations_data.get("durations", {})  # type: ignore[assignment]

    slow_tests = [
        (nodeid, duration)
        for nodeid, duration in durations.items()
        if duration >= threshold  # type: ignore[operator]
    ]

    print(f"Found {len(slow_tests)} slow tests (>{threshold}s)")

    if not slow_tests:
        print("No reports to generate.")
        create_summary_report(durations_data, slow_tests)
        print(f"\nSummary saved to: {SUMMARY_FILE}")
        return 0

    print(f"\nGenerating reports for {len(slow_tests)} slow tests...")

    for idx, (nodeid, duration) in enumerate(slow_tests, 1):
        safe_name = sanitize_test_name(nodeid)
        prof_file = PROF_OUTPUT_DIR / f"{safe_name}.prof"
        report_file = PROF_OUTPUT_DIR / f"{safe_name}_report.txt"

        print(f"[{idx}/{len(slow_tests)}] {nodeid} ({duration:.2f}s) ... ", end="")

        if not prof_file.exists():
            print(f"ERROR: {prof_file} not found!")
            continue

        try:
            generate_profile_report(prof_file, report_file, nodeid, duration)
            print("Done")
        except Exception as e:
            print(f"Failed: {e}")

    print("\nCreating summary report...")
    create_summary_report(durations_data, slow_tests)

    print(f"\n[OK] Reports generated: {len(slow_tests)}")
    print(f"[OK] Summary saved to: {SUMMARY_FILE}")
    print(f"[OK] Output directory: {PROF_OUTPUT_DIR}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
