import tempfile
import unittest
from pathlib import Path

from mcp_workspace.file_tools.edit_file import (
    _is_edit_already_applied,
    edit_file,
)


class TestEditAlreadyAppliedFix(unittest.TestCase):
    """Tests for the fix to already-applied detection false positives."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_dir = Path(self.temp_dir.name)
        self.test_file = self.project_dir / "test_file.py"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_is_edit_already_applied_helper_function(self) -> None:
        """Test the _is_edit_already_applied helper function directly."""
        # Edit not applied yet (old text exists, new text doesn't)
        content = "function_name = 'original'"
        self.assertFalse(
            _is_edit_already_applied(content, "function_name", "new_function_name")
        )

        # Edit already applied (old text gone, new text present)
        content = "modified_function = 'original'"
        self.assertTrue(
            _is_edit_already_applied(content, "function_name", "modified_function")
        )

        # False positive scenario (new text appears elsewhere but old still exists)
        content = 'function_name = "test"\nprint("test")'
        self.assertFalse(_is_edit_already_applied(content, "function_name", "test"))

        # Both old and new text exist (partial edit state)
        content = "function_name = 'test'\nmodified_function = 'other'"
        self.assertFalse(
            _is_edit_already_applied(content, "function_name", "modified_function")
        )

    def test_false_positive_prevention_single_line(self) -> None:
        """Test that the fix prevents false positives with single-line edits."""
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write('function_name = "test"\nprint("test")\n')

        # This edit should be applied, not skipped
        result = edit_file(
            str(self.test_file),
            old_string="function_name",
            new_string="test",
        )

        # Should succeed and produce a diff
        self.assertIn("---", result)

        with open(self.test_file, encoding="utf-8") as f:
            content = f.read()
        self.assertIn('test = "test"', content)
        self.assertNotIn('function_name = "test"', content)

    def test_false_positive_prevention_multiline(self) -> None:
        """Test that the fix prevents false positives with multi-line edits."""
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write(
                "def old_function():\n"
                '    return "result"\n'
                "\n"
                '# Comment mentions: return "result"\n'
                'print("Debug info")\n'
            )

        result = edit_file(
            str(self.test_file),
            old_string='def old_function():\n    return "result"',
            new_string='def new_function():\n    return "result"',
        )

        # Should succeed and produce a diff
        self.assertIn("---", result)

        with open(self.test_file, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("def new_function():", content)
        self.assertNotIn("def old_function():", content)
        self.assertIn('# Comment mentions: return "result"', content)

    def test_legitimate_already_applied_detection(self) -> None:
        """Test that legitimate already-applied cases are still detected correctly."""
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write("def test_function():\n    return 'test'\n")

        # First application should succeed with diff
        result1 = edit_file(
            str(self.test_file),
            old_string="test_function",
            new_string="modified_function",
        )
        self.assertIn("---", result1)

        # Second application should return message (already applied)
        result2 = edit_file(
            str(self.test_file),
            old_string="test_function",
            new_string="modified_function",
        )
        self.assertNotIn("---", result2)
        self.assertIn("No changes needed", result2)

    def test_complex_false_positive_scenario(self) -> None:
        """Test a complex scenario that could trigger false positives."""
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write(
                "def process_data():\n"
                "    return process(data)\n"
                "\n"
                "def handle_process():\n"
                '    print("Handling process")\n'
                "\n"
                "# TODO: Update process_data function\n"
            )

        # Edit that renames — but "process" appears elsewhere, so old_string
        # "process_data" still matches. With new interface, multiple matches
        # would need replace_all. But "process_data" appears twice (def + comment),
        # so let's use replace_all=True.
        result = edit_file(
            str(self.test_file),
            old_string="process_data",
            new_string="process",
            replace_all=True,
        )

        self.assertIn("---", result)

        with open(self.test_file, encoding="utf-8") as f:
            content = f.read()

        # Both occurrences should be changed
        self.assertIn("def process():", content)
        self.assertNotIn("process_data", content)
        self.assertIn("return process(data)", content)
        self.assertIn("handle_process", content)


if __name__ == "__main__":
    unittest.main()
