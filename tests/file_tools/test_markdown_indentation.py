import tempfile
import unittest
from pathlib import Path

from mcp_workspace.file_tools.edit_file import edit_file


class TestMarkdownIndentation(unittest.TestCase):
    """Test specifically for markdown indentation issues."""

    def setUp(self) -> None:
        # Create a temporary directory for testing
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        # Clean up after tests
        self.temp_dir.cleanup()

    def test_bullet_point_indentation(self) -> None:
        # Create a markdown file with nested bullet points
        markdown_file = self.project_dir / "markdown_test_temp.md"
        with open(markdown_file, "w", encoding="utf-8") as f:
            f.write(
                "# Documentation\n\n"
                "## Features\n\n"
                "- Top level feature\n"
                "- Available options:\n"
                "- option1: description\n"
                "- option2: description\n"
                "- Another top level feature"
            )

        # Verify file was created
        with open(markdown_file, encoding="utf-8") as f:
            content = f.read()

        self.assertIn("# Documentation", content)
        self.assertIn("- Available options:", content)

        # Edit to add indentation to nested bullet points
        old_string = (
            "- Available options:\n- option1: description\n- option2: description"
        )
        new_string = (
            "- Available options:\n  - option1: description\n  - option2: description"
        )

        result = edit_file(str(markdown_file), old_string, new_string)

        # Verify the edit returned a diff string
        self.assertIsInstance(result, str)
        self.assertIn("---", result)  # diff header

        # Read the updated content
        with open(markdown_file, encoding="utf-8") as f:
            updated_content = f.read()

        # Check that the text was edited
        self.assertIn("- Available options:", updated_content)
        self.assertIn("option1: description", updated_content)
        self.assertIn("option2: description", updated_content)

        # Check that the indentation changed
        self.assertIn("  - option1: description", updated_content)
        self.assertIn("  - option2: description", updated_content)
