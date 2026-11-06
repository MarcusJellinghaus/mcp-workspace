#!/usr/bin/env python3
r"""Render a CI step summary from a Cobertura coverage.xml.

Standalone script, stdlib only. Parses the coverage.xml produced by
``coverage xml`` (Cobertura format), rolls up line counts by top-level
package, and renders Markdown for ``$GITHUB_STEP_SUMMARY``. Never fails
the build based on a coverage number -- this is reporting only.

Usage:
    python tools/ci_coverage_summary.py --coverage-xml coverage.xml
    python tools/ci_coverage_summary.py --coverage-xml coverage.xml \
        --diff-report diff-coverage.md --output summary.md
"""

import argparse
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

ROOT_PACKAGE = "src.mcp_workspace"

MARKER_TRAP_CAVEAT = (
    "_`github_integration` tests run only when `GH_INTEGRATION_TOKEN` and "
    "`GH_TEST_REPO_URL` are available. When that job is skipped, lines only "
    "reachable under them show as uncovered._"
)


@dataclass
class PackageRollup:
    """Line totals for one top-level package bucket."""

    name: str
    lines_valid: int
    lines_covered: int

    @property
    def rate(self) -> float:
        """Covered fraction of this package's lines."""
        return self.lines_covered / self.lines_valid if self.lines_valid else 0.0


@dataclass
class CoverageSummary:
    """Grand totals plus the per-package breakdown."""

    lines_valid: int
    lines_covered: int
    packages: list[PackageRollup]

    @property
    def rate(self) -> float:
        """Covered fraction of all lines."""
        return self.lines_covered / self.lines_valid if self.lines_valid else 0.0


def top_level_package_name(full_name: str) -> str:
    """Bucket a Cobertura package name under its top-level segment.

    ``coverage xml`` run after ``coverage combine`` has no measured root to
    work from, so it names packages from the working directory:
    ``src.mcp_workspace.github_operations.issues`` -> ``github_operations``.
    The root package itself (loose top-level modules like ``main.py``) buckets
    into the readable ``mcp_workspace`` row. Names relative to the measured
    root (``checks``, and ``.`` for the root package), which ``coverage xml``
    writes when a source is configured, bucket the same way.
    """
    relative = full_name.removeprefix(ROOT_PACKAGE).strip(".")
    return relative.split(".")[0] if relative else "mcp_workspace"


def parse_coverage_xml(xml_path: Path) -> CoverageSummary:
    """Parse a Cobertura coverage.xml, summing line hits per top-level bucket."""
    root = ET.parse(xml_path).getroot()  # noqa: S314 - CI's own coverage.xml (trusted)
    buckets: dict[str, PackageRollup] = {}
    total_valid = 0
    total_covered = 0

    for package in root.findall(".//package"):
        bucket_name = top_level_package_name(package.get("name") or "")
        rollup = buckets.setdefault(
            bucket_name, PackageRollup(bucket_name, lines_valid=0, lines_covered=0)
        )
        for line in package.findall(".//class/lines/line"):
            rollup.lines_valid += 1
            total_valid += 1
            if line.get("hits") != "0":
                rollup.lines_covered += 1
                total_covered += 1

    packages = sorted(buckets.values(), key=lambda p: p.name)
    return CoverageSummary(
        lines_valid=total_valid, lines_covered=total_covered, packages=packages
    )


def render_step_summary(summary: CoverageSummary, diff_report: str | None) -> str:
    """Render the step-summary Markdown for one coverage run."""
    lines = [
        f"## Coverage: {summary.rate:.0%}",
        "",
        MARKER_TRAP_CAVEAT,
        "",
        "<details>",
        "<summary>Per-package breakdown</summary>",
        "",
        "| Package | Lines valid | Lines covered | Rate |",
        "| --- | --- | --- | --- |",
    ]
    for package in summary.packages:
        lines.append(
            f"| {package.name} | {package.lines_valid} | {package.lines_covered} "
            f"| {package.rate:.0%} |"
        )
    lines.extend(["", "</details>"])

    if diff_report is not None:
        lines.extend(
            [
                "",
                "**Diff coverage (advisory, not a gate)**",
                "",
                diff_report,
            ]
        )

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: parse coverage.xml and append the summary to --output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage-xml", required=True, type=Path)
    parser.add_argument("--diff-report", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    diff_report = (
        args.diff_report.read_text(encoding="utf-8")
        if args.diff_report is not None
        else None
    )
    summary = parse_coverage_xml(args.coverage_xml)
    rendered = render_step_summary(summary, diff_report)

    output_path = args.output or (
        Path(os.environ["GITHUB_STEP_SUMMARY"])
        if "GITHUB_STEP_SUMMARY" in os.environ
        else None
    )
    if output_path is None:
        sys.stdout.write(rendered)
    else:
        with open(output_path, "a", encoding="utf-8") as f:
            f.write(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
