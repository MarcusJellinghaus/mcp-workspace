import tempfile
import unittest
from pathlib import Path

from mcp_workspace.file_tools.edit_file import edit_file


class TestEditFile(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_dir = Path(self.temp_dir.name)
        self.test_file = self.project_dir / "test_file.py"
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write("def test_function():\n    return 'test'\n")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_basic_replacement(self) -> None:
        """Replaces first occurrence and returns diff string."""
        result = edit_file(
            str(self.test_file),
            old_string="test_function",
            new_string="modified_function",
        )

        self.assertIsInstance(result, str)
        self.assertIn("-def test_function():", result)
        self.assertIn("+def modified_function():", result)

        with open(self.test_file, encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "def modified_function():\n    return 'test'\n")

    def test_with_project_dir(self) -> None:
        """Relative path resolution works with project_dir."""
        result = edit_file(
            "test_file.py",
            old_string="test_function",
            new_string="modified_function",
            project_dir=self.project_dir,
        )

        self.assertIsInstance(result, str)
        self.assertIn("modified_function", result)

        with open(self.test_file, encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "def modified_function():\n    return 'test'\n")

    def test_file_not_found(self) -> None:
        """Raises FileNotFoundError for missing file."""
        with self.assertRaises(FileNotFoundError):
            edit_file(
                str(self.project_dir / "nonexistent.py"),
                old_string="hello",
                new_string="world",
            )

    def test_text_not_found(self) -> None:
        """Raises ValueError when old_string not in file."""
        with self.assertRaises(ValueError) as ctx:
            edit_file(
                str(self.test_file),
                old_string="nonexistent_text",
                new_string="replacement",
            )
        self.assertIn("not found", str(ctx.exception).lower())

    def test_already_applied_contextual(self) -> None:
        """Apply edit, re-apply → returns message string."""
        # First apply
        result1 = edit_file(
            str(self.test_file),
            old_string="test_function",
            new_string="modified_function",
        )
        self.assertIn("modified_function", result1)

        # Re-apply same edit
        result2 = edit_file(
            str(self.test_file),
            old_string="test_function",
            new_string="modified_function",
        )
        self.assertIn("already applied", result2.lower())

    def test_already_applied_position_aware(self) -> None:
        """old_string is prefix of new_string, content already has new_string."""
        # Write file where old_string is a prefix of new_string
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write("def func_extended():\n    pass\n")

        result = edit_file(
            str(self.test_file),
            old_string="def func",
            new_string="def func_extended",
        )
        self.assertIn("already applied", result.lower())

    def test_empty_old_string_inserts_at_beginning(self) -> None:
        """Empty old_string inserts new_string at beginning of file."""
        result = edit_file(
            str(self.test_file),
            old_string="",
            new_string="# Header comment\n",
        )

        self.assertIsInstance(result, str)
        with open(self.test_file, encoding="utf-8") as f:
            content = f.read()
        self.assertTrue(content.startswith("# Header comment\n"))
        self.assertIn("def test_function():", content)

    def test_replace_all(self) -> None:
        """replace_all=True replaces all occurrences."""
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write("aaa bbb aaa ccc aaa\n")

        result = edit_file(
            str(self.test_file),
            old_string="aaa",
            new_string="xxx",
            replace_all=True,
        )

        self.assertIsInstance(result, str)
        with open(self.test_file, encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "xxx bbb xxx ccc xxx\n")

    def test_multiple_matches_without_replace_all(self) -> None:
        """Raises ValueError when multiple matches and replace_all=False."""
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write("aaa bbb aaa ccc aaa\n")

        with self.assertRaises(ValueError) as ctx:
            edit_file(
                str(self.test_file),
                old_string="aaa",
                new_string="xxx",
            )
        self.assertIn("multiple", str(ctx.exception).lower())

    def test_large_block_replacement(self) -> None:
        """Multi-line edit works correctly."""
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write(
                "class Foo:\n"
                "    def bar(self):\n"
                "        return 1\n"
                "\n"
                "    def baz(self):\n"
                "        return 2\n"
            )

        result = edit_file(
            str(self.test_file),
            old_string="    def bar(self):\n        return 1",
            new_string="    def bar(self):\n        x = compute()\n        return x",
        )

        self.assertIsInstance(result, str)
        with open(self.test_file, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("x = compute()", content)
        self.assertIn("return x", content)
        # baz method should be untouched
        self.assertIn("def baz(self):", content)

    def test_mixed_indentation(self) -> None:
        """Tabs and spaces preserved correctly."""
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write("def f1():\n    return 1\n\ndef f2():\n\treturn 2\n")

        edit_file(
            str(self.test_file),
            old_string="    return 1",
            new_string="    return 10",
        )
        edit_file(
            str(self.test_file),
            old_string="\treturn 2",
            new_string="\treturn 20",
        )

        with open(self.test_file, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("    return 10", content)
        self.assertIn("\treturn 20", content)

    def test_crlf_normalization(self) -> None:
        """CRLF in old_string/new_string/file content handled."""
        # Write file with CRLF
        self.test_file.write_bytes(b"hello\r\nworld\r\n")

        result = edit_file(
            str(self.test_file),
            old_string="hello\r\nworld",
            new_string="hi\r\nworld",
        )

        self.assertIsInstance(result, str)
        with open(self.test_file, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("hi", content)
        self.assertNotIn("\r", content)

    def test_backslash_hint(self) -> None:
        """Single backslash old_string triggers hint in ValueError message."""
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write('path = "C:\\\\Users\\\\test"\n')

        with self.assertRaises(ValueError) as ctx:
            edit_file(
                str(self.test_file),
                old_string='path = "C:\\Users\\test"',
                new_string='path = "C:\\NewUsers\\test"',
            )
        self.assertIn("backslash", str(ctx.exception).lower())

    def test_delete_text_empty_new_string(self) -> None:
        """Replaces old_string with empty string, removing it."""
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write("line1\nline2\nline3\n")

        result = edit_file(
            str(self.test_file),
            old_string="line2\n",
            new_string="",
        )

        self.assertIsInstance(result, str)
        with open(self.test_file, encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "line1\nline3\n")

    def test_diff_headers_have_newlines(self) -> None:
        """Header lines and hunk marker are separated by `\\n`, not run together."""
        result = edit_file(
            "test_file.py",
            old_string="test_function",
            new_string="modified_function",
            project_dir=self.project_dir,
        )

        self.assertIn("\n+++ ", result)
        self.assertIn("\n@@ ", result)

    def _assert_diff_uses_relative_forward_slash_path(
        self, file_path: str, expected_from: str, expected_to: str
    ) -> None:
        """Diff header paths are relative and use forward slashes (no `a//...`, no backslashes)."""
        # Set up a file at the corresponding relative location.
        target = self.project_dir / file_path.replace("\\", "/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("def test_function():\n    return 'test'\n", encoding="utf-8")

        result = edit_file(
            file_path,
            old_string="test_function",
            new_string="modified_function",
            project_dir=self.project_dir,
        )

        self.assertIn(expected_from, result)
        self.assertIn(expected_to, result)
        self.assertNotIn("a//", result)

        for line in result.splitlines():
            if line.startswith("--- ") or line.startswith("+++ "):
                self.assertNotIn("\\", line)

    def test_diff_uses_relative_forward_slash_path_flat(self) -> None:
        """Flat relative file path produces forward-slash header paths."""
        self._assert_diff_uses_relative_forward_slash_path(
            "test_file.py", "--- a/test_file.py", "+++ b/test_file.py"
        )

    def test_diff_uses_relative_forward_slash_path_backslash(self) -> None:
        """Windows-style backslash relative path is normalized to forward slashes."""
        self._assert_diff_uses_relative_forward_slash_path(
            "sub\\dir\\test_file.py",
            "--- a/sub/dir/test_file.py",
            "+++ b/sub/dir/test_file.py",
        )
