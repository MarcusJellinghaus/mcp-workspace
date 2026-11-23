"""Tests for verify_file_access."""

from pathlib import Path
from typing import Any

import pytest

from mcp_workspace.file_tools.access_rules import ACCESS_RULES_FILE
from mcp_workspace.file_tools.verification import verify_file_access


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        pytest.param(
            None,
            {
                "rules_file": {
                    "ok": True,
                    "value": "absent - gitignore only",
                    "severity": "error",
                },
                "overall_ok": True,
            },
            id="absent",
        ),
        pytest.param(
            "read-only /a\nread-write /b\n",
            {
                "rules_file": {"ok": True, "value": "2 rules", "severity": "error"},
                "overall_ok": True,
            },
            id="two-rules",
        ),
        pytest.param(
            "# comment\n",
            {
                "rules_file": {"ok": True, "value": "0 rules", "severity": "error"},
                "overall_ok": True,
            },
            id="comment-only",
        ),
        pytest.param(
            "readonly /a\n",
            {
                "rules_file": {
                    "ok": False,
                    "value": "invalid",
                    "severity": "error",
                    "error": "line 1: unknown level 'readonly'",
                },
                "overall_ok": False,
            },
            id="invalid",
        ),
        pytest.param(
            "<dir>",
            {
                "rules_file": {
                    "ok": False,
                    "value": "invalid",
                    "severity": "error",
                    "error": "is a directory",
                },
                "overall_ok": False,
            },
            id="directory",
        ),
    ],
)
def test_verify_file_access(
    tmp_path: Path, content: str | None, expected: dict[str, Any]
) -> None:
    rules_file = tmp_path / ACCESS_RULES_FILE
    if content == "<dir>":
        rules_file.mkdir()
    elif content is not None:
        rules_file.write_text(content, encoding="utf-8")

    assert verify_file_access(tmp_path) == expected
