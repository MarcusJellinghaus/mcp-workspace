import tempfile
import unittest
from pathlib import Path

import pytest

from mcp_workspace.file_tools.edit_file import edit_file
from mcp_workspace.file_tools.path_utils import normalize_line_endings


class TestEditFileIndentationIssues(unittest.TestCase):
    """Tests specifically designed to test simplified indentation handling."""

    def test_normalize_line_endings(self) -> None:
        """Test line ending normalization."""
        text_with_mixed = "line1\r\nline2\nline3\r\n"
        normalized = normalize_line_endings(text_with_mixed)
        expected = "line1\nline2\nline3\n"
        self.assertEqual(normalized, expected)

    def setUp(self) -> None:
        # Create a temporary directory and file for testing
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_dir = Path(self.temp_dir.name)
        self.test_file = self.project_dir / "test_file.py"

    def tearDown(self) -> None:
        # Clean up after tests
        self.temp_dir.cleanup()

    def test_extreme_indentation_handling(self) -> None:
        """Test handling code with extreme indentation discrepancies."""
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write(
                'def main():\n    input_file, output_dir, verbose = parse_arguments()\n\n    if verbose:\n        print(f"Verbose mode enabled")\n        print(f"Input file: {input_file}")\n\n    processor = DataProcessor(input_file, output_dir)\n\n    if processor.load_data():\n        print(f"Successfully loaded {len(processor.data)} lines")\n\n        results = processor.process_data()\n\n        if processor.save_results(results):\n            print(f"Results saved to {output_dir}")\n\n            if verbose and results[\'total_lines\'] > 0:\n                                                                            print(f"Summary:")\n                                                                            print(f"  - Processed {results[\'total_lines\']} lines")\n                                                                            print(f"  - Found {len(results[\'word_counts\'])} unique words")\n        else:\n            print("Failed to save results")\n    else:\n        print("Failed to load data")\n'
            )

        result = edit_file(
            str(self.test_file),
            old_string="            if verbose and results['total_lines'] > 0:\n                                                                            print(f\"Summary:\")\n                                                                            print(f\"  - Processed {results['total_lines']} lines\")\n                                                                            print(f\"  - Found {len(results['word_counts'])} unique words\")",
            new_string="            if verbose and results['total_lines'] > 0:\n                print(f\"Summary:\")\n                print(f\"  - Processed {results['total_lines']} lines\")\n                print(f\"  - Found {len(results['word_counts'])} unique words\")",
        )

        # Should succeed and return a diff
        self.assertIn("---", result)

        with open(self.test_file, encoding="utf-8") as f:
            content = f.read()

        # Verify the edit fixed the indentation
        self.assertIn("            if verbose and results['total_lines'] > 0:", content)
        self.assertIn('                print(f"Summary:")', content)

    def test_optimization_edit_already_applied(self) -> None:
        """Test the optimization in edit_file that checks if edits are already applied."""
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write("def test_function():\n    return 'test'\n")

        # First apply an edit
        result1 = edit_file(
            str(self.test_file),
            old_string="test_function",
            new_string="modified_function",
        )
        self.assertIn("---", result1)

        # Try to apply the same edit again — should return message, not raise
        result2 = edit_file(
            str(self.test_file),
            old_string="test_function",
            new_string="modified_function",
        )
        self.assertNotIn("---", result2)
        self.assertIn("No changes needed", result2)

    def test_false_positive_already_applied_bug_fix(self) -> None:
        """Test fix for false positive in already-applied detection where new_string appears elsewhere."""
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write('function_name = "test"\nprint("test")\n')

        # This edit should be applied, not skipped due to "test" appearing in print
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
        self.assertIn('print("test")', content)

    def test_multiple_matches_raises_without_replace_all(self) -> None:
        """Test that multiple matches raise ValueError without replace_all."""
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write(
                'def process(data):\n    print("Processing data...")\n    return data\n\ndef analyze(data):\n    print("Processing data...")\n    return data * 2\n'
            )

        with pytest.raises(ValueError, match="Multiple matches"):
            edit_file(
                str(self.test_file),
                old_string='    print("Processing data...")',
                new_string='    print("Data processing started...")',
            )

    def test_prefix_match_does_not_create_duplicates(self) -> None:
        """Reproduces the exact bug: substring old_string should not duplicate suffix."""
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write(
                "def mock_config_path(self, tmp_path) -> None:  # type: ignore[misc]\n"
            )

        result = edit_file(
            str(self.test_file),
            old_string="def mock_config_path(self, tmp_path) -> None:",
            new_string="def mock_config_path(self, tmp_path) -> None:  # type: ignore[misc]",
        )

        # Should detect as already applied (returns message, not diff)
        self.assertNotIn("---", result)

        with open(self.test_file, encoding="utf-8") as f:
            content = f.read()
        # Must NOT have duplicated suffix
        self.assertNotIn("# type: ignore[misc]  # type: ignore[misc]", content)

    def test_legitimate_prefix_replacement_proceeds(self) -> None:
        """Ensures the guard doesn't block valid edits."""
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write("foo = 1\n")

        result = edit_file(
            str(self.test_file),
            old_string="foo",
            new_string="foobar",
        )

        self.assertIn("---", result)

        with open(self.test_file, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("foobar = 1", content)

    def test_new_string_longer_than_remaining_content_proceeds(self) -> None:
        """Ensures no false skip when new_string extends beyond end of file."""
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write("short")

        result = edit_file(
            str(self.test_file),
            old_string="short",
            new_string="short_with_much_longer_suffix",
        )

        self.assertIn("---", result)

        with open(self.test_file, encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "short_with_much_longer_suffix")
