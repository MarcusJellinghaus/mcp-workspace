"""Tests for compact_diffs.py — realistic refactor and header-only change scenarios."""

import pytest

from mcp_workspace.git_operations.compact_diffs import (
    parse_diff,
    render_compact_diff,
)

# Realistic diff: Calculator class moved from old_module.py to calculator.py,
# with a genuine import change in main.py.
_REALISTIC_REFACTOR_DIFF = """\
diff --git old_module.py old_module.py
--- old_module.py
+++ old_module.py
@@ -1,25 +1,3 @@
 \"\"\"Old module — Calculator has moved to calculator.py.\"\"\"
 
-
-class Calculator:
-    \"\"\"Simple calculator with basic arithmetic operations.\"\"\"
-
-    def __init__(self, precision: int = 2) -> None:
-        \"\"\"Initialise with decimal precision for results.\"\"\"
-        self.precision = precision
-
-    def add(self, a: float, b: float) -> float:
-        \"\"\"Return the sum of a and b, rounded to self.precision.\"\"\"
-        return round(a + b, self.precision)
-
-    def subtract(self, a: float, b: float) -> float:
-        \"\"\"Return a minus b, rounded to self.precision.\"\"\"
-        return round(a - b, self.precision)
-
-    def multiply(self, a: float, b: float) -> float:
-        \"\"\"Return the product of a and b, rounded to self.precision.\"\"\"
-        return round(a * b, self.precision)
-
 
 CONSTANT_VALUE = 42
 ANOTHER_CONSTANT = \"hello world from old_module\"
diff --git calculator.py calculator.py
new file mode 100644
--- /dev/null
+++ calculator.py
@@ -0,0 +1,25 @@
+\"\"\"Calculator module — extracted from old_module.py.\"\"\"
+
+
+class Calculator:
+    \"\"\"Simple calculator with basic arithmetic operations.\"\"\"
+
+    def __init__(self, precision: int = 2) -> None:
+        \"\"\"Initialise with decimal precision for results.\"\"\"
+        self.precision = precision
+
+    def add(self, a: float, b: float) -> float:
+        \"\"\"Return the sum of a and b, rounded to self.precision.\"\"\"
+        return round(a + b, self.precision)
+
+    def subtract(self, a: float, b: float) -> float:
+        \"\"\"Return a minus b, rounded to self.precision.\"\"\"
+        return round(a - b, self.precision)
+
+    def multiply(self, a: float, b: float) -> float:
+        \"\"\"Return the product of a and b, rounded to self.precision.\"\"\"
+        return round(a * b, self.precision)
+
+
+CALCULATOR_VERSION = \"1.0.0\"
diff --git main.py main.py
--- main.py
+++ main.py
@@ -1,3 +1,3 @@
-from old_module import Calculator
+from calculator import Calculator
 
 GREETING = \"Hello from main\"
"""


class TestRenderCompactDiffRealistic:
    """End-to-end tests using a realistic refactoring diff."""

    def test_output_is_shorter_than_input(self) -> None:
        """Core property: compacting a moved-class diff produces fewer lines."""
        result = render_compact_diff(_REALISTIC_REFACTOR_DIFF, "")
        assert len(result.splitlines()) < len(_REALISTIC_REFACTOR_DIFF.splitlines())

    def test_class_signature_visible_in_preview(self) -> None:
        """The class name survives in the preview on both sides."""
        result = render_compact_diff(_REALISTIC_REFACTOR_DIFF, "")
        assert "class Calculator:" in result

    def test_method_bodies_suppressed(self) -> None:
        """Method bodies inside the moved class are hidden in the summary."""
        result = render_compact_diff(_REALISTIC_REFACTOR_DIFF, "")
        assert "def subtract" not in result
        assert "def multiply" not in result

    def test_genuine_change_preserved(self) -> None:
        """Lines that are not moved (the import update in main.py) are always shown."""
        result = render_compact_diff(_REALISTIC_REFACTOR_DIFF, "")
        assert "-from old_module import Calculator" in result
        assert "+from calculator import Calculator" in result

    def test_summary_references_other_file(self) -> None:
        """Moved-block summaries name the source/destination file."""
        result = render_compact_diff(_REALISTIC_REFACTOR_DIFF, "")
        assert "# [moved to calculator.py: 15 lines not shown]" in result
        assert "# [moved from old_module.py: 16 lines not shown]" in result

    def test_full_output_snapshot(self) -> None:
        """Snapshot of the complete compact diff output."""
        result = render_compact_diff(_REALISTIC_REFACTOR_DIFF, "")
        expected = (
            "diff --git old_module.py old_module.py\n"
            "--- old_module.py\n"
            "+++ old_module.py\n"
            "@@ -1,25 +1,3 @@\n"
            ' """Old module \u2014 Calculator has moved to calculator.py."""\n'
            " \n"
            "-\n"
            "-class Calculator:\n"
            '-    """Simple calculator with basic arithmetic operations."""\n'
            "-\n"
            "-    def __init__(self, precision: int = 2) -> None:\n"
            "-# [moved to calculator.py: 15 lines not shown]\n"
            " \n"
            " CONSTANT_VALUE = 42\n"
            ' ANOTHER_CONSTANT = "hello world from old_module"\n'
            "diff --git calculator.py calculator.py\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            "+++ calculator.py\n"
            "@@ -0,0 +1,25 @@\n"
            '+"""Calculator module \u2014 extracted from old_module.py."""\n'
            "+\n"
            "+\n"
            "+class Calculator:\n"
            '+    """Simple calculator with basic arithmetic operations."""\n'
            "+\n"
            "+    def __init__(self, precision: int = 2) -> None:\n"
            "+# [moved from old_module.py: 16 lines not shown]\n"
            '+CALCULATOR_VERSION = "1.0.0"\n'
            "diff --git main.py main.py\n"
            "--- main.py\n"
            "+++ main.py\n"
            "@@ -1,3 +1,3 @@\n"
            "-from old_module import Calculator\n"
            "+from calculator import Calculator\n"
            " \n"
            ' GREETING = "Hello from main"'
        )
        assert result == expected


# ---------------------------------------------------------------------------
# Raw diff strings for header-only change types
# ---------------------------------------------------------------------------

_HEADER_ONLY_CASES = [
    pytest.param(
        (
            "diff --git a/old.py b/new.py\n"
            "similarity index 100%\n"
            "rename from old.py\n"
            "rename to new.py\n"
        ),
        ["rename from", "rename to"],
        id="pure_rename",
    ),
    pytest.param(
        (
            "diff --git a/src.py b/dst.py\n"
            "similarity index 100%\n"
            "copy from src.py\n"
            "copy to dst.py\n"
        ),
        ["copy from", "copy to"],
        id="pure_copy",
    ),
    pytest.param(
        ("diff --git a/script.sh b/script.sh\nold mode 100644\nnew mode 100755\n"),
        ["old mode", "new mode"],
        id="mode_change",
    ),
    pytest.param(
        (
            "diff --git a/image.png b/image.png\n"
            "index abc123..def456 100644\n"
            "Binary files a/image.png and b/image.png differ\n"
        ),
        ["Binary"],
        id="binary_change",
    ),
    pytest.param(
        "diff --git a/empty.py b/empty.py\nnew file mode 100644\n",
        ["new file mode"],
        id="empty_file_creation",
    ),
    pytest.param(
        "diff --git a/empty.py b/empty.py\ndeleted file mode 100644\n",
        ["deleted file mode"],
        id="empty_file_deletion",
    ),
]


# ---------------------------------------------------------------------------
# TestParseDiffHeaderOnly
# ---------------------------------------------------------------------------


class TestParseDiffHeaderOnly:
    """Parameterised tests: raw diff strings -> parse_diff -> assert headers."""

    @pytest.mark.parametrize(("raw_diff", "expected_substrings"), _HEADER_ONLY_CASES)
    def test_parse_diff_header_only_change_types(
        self, raw_diff: str, expected_substrings: list[str]
    ) -> None:
        files = parse_diff(raw_diff)
        assert len(files) == 1
        file_diff = files[0]
        assert file_diff.hunks == []
        headers_joined = "\n".join(file_diff.headers)
        for substring in expected_substrings:
            assert substring in headers_joined


# ---------------------------------------------------------------------------
# TestRenderCompactDiffHeaderOnly
# ---------------------------------------------------------------------------


class TestRenderCompactDiffHeaderOnly:
    """Parameterised tests: raw diff strings -> render_compact_diff -> non-empty with expected headers."""

    @pytest.mark.parametrize(("raw_diff", "expected_substrings"), _HEADER_ONLY_CASES)
    def test_render_compact_diff_header_only_change_types(
        self, raw_diff: str, expected_substrings: list[str]
    ) -> None:
        result = render_compact_diff(raw_diff, "")
        assert result != ""
        for substring in expected_substrings:
            assert substring in result
