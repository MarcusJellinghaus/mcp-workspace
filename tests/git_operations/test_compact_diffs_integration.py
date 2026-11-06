"""Integration tests for compact_diffs with real git repos.

Tests exercise the full pipeline: real git operations → get_compact_diff → assertions.
"""

from pathlib import Path

import pytest
from git import Repo

from mcp_workspace.git_operations.branch_queries import (
    get_current_branch_name,
)
from mcp_workspace.git_operations.compact_diffs import get_compact_diff


@pytest.mark.git_integration
class TestCompactDiffRenames:
    """Integration tests for rename detection in compact diffs."""

    def test_pure_rename_appears_in_compact_diff(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """A pure rename (no content change) shows rename headers."""
        repo, project_dir = git_repo_with_commit
        base_branch = get_current_branch_name(project_dir)
        assert base_branch is not None

        repo.git.checkout("-b", "feature-pure-rename")

        # Rename README.md → RENAMED.md with no content change
        repo.git.mv("README.md", "RENAMED.md")
        repo.index.commit("Rename README to RENAMED")

        result = get_compact_diff(project_dir, base_branch)

        assert "rename from" in result
        assert "rename to" in result

    def test_partial_rename_shows_headers_and_hunks(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """A rename with content changes shows rename headers AND diff hunks."""
        repo, project_dir = git_repo_with_commit

        # Make README large enough so a small edit still exceeds rename threshold
        original_lines = [f"Line {i} of the original content here." for i in range(20)]
        original_content = "\n".join(original_lines) + "\n"
        readme = project_dir / "README.md"
        readme.write_text(original_content)
        repo.index.add(["README.md"])
        repo.index.commit("Expand README for rename test")

        base_branch = get_current_branch_name(project_dir)
        assert base_branch is not None

        repo.git.checkout("-b", "feature-partial-rename")

        # Enable rename detection in the test repo config
        with repo.config_writer() as config:
            config.set_value("diff", "renames", "true")

        # Rename and make a small content change (keep most content identical)
        modified_lines = list(original_lines)
        modified_lines[-1] = "Line 19 has been CHANGED."
        modified_content = "\n".join(modified_lines) + "\n"
        repo.git.mv("README.md", "RENAMED.md")
        renamed = project_dir / "RENAMED.md"
        renamed.write_text(modified_content)
        repo.index.add(["RENAMED.md"])
        repo.index.commit("Rename README and modify content")

        result = get_compact_diff(project_dir, base_branch)

        assert "rename from" in result
        assert "rename to" in result
        assert "@@" in result


@pytest.mark.git_integration
class TestCompactDiffCopies:
    """Integration tests for copy detection in compact diffs."""

    def test_pure_copy_appears_in_compact_diff(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """A copy detected by -C90% shows copy headers."""
        repo, project_dir = git_repo_with_commit

        # Make README large enough for copy detection to work reliably
        large_content = (
            "# Test Project\n\n"
            "This file has enough content for git copy detection.\n"
            "Line three of the original content here.\n"
            "Line four of the original content here.\n"
            "Line five of the original content here.\n"
            "Line six of the original content here.\n"
            "Line seven of the original content here.\n"
            "Line eight of the original content here.\n"
            "Line nine of the original content here.\n"
        )
        readme = project_dir / "README.md"
        readme.write_text(large_content)
        repo.index.add(["README.md"])
        repo.index.commit("Expand README for copy test")

        base_branch = get_current_branch_name(project_dir)
        assert base_branch is not None

        repo.git.checkout("-b", "feature-copy")

        # Modify the source file slightly so git considers it in the commit,
        # then create a near-identical copy under a new name.
        readme.write_text(large_content + "Minor edit added.\n")
        copy_file = project_dir / "README_COPY.md"
        copy_file.write_text(large_content)
        repo.index.add(["README.md", "README_COPY.md"])
        repo.index.commit("Copy README with minor source edit")

        result = get_compact_diff(project_dir, base_branch)

        assert "copy from" in result
        assert "copy to" in result


@pytest.mark.git_integration
class TestCompactDiffModeChanges:
    """Integration tests for file mode changes in compact diffs."""

    def test_mode_change_appears_in_compact_diff(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """A file mode change shows old mode / new mode headers."""
        repo, project_dir = git_repo_with_commit
        base_branch = get_current_branch_name(project_dir)
        assert base_branch is not None

        repo.git.checkout("-b", "feature-mode-change")

        # Set core.fileMode=true so the index records mode changes
        with repo.config_writer() as config:
            config.set_value("core", "fileMode", "true")

        repo.git.execute(["git", "update-index", "--chmod=+x", "README.md"])
        repo.index.commit("Make README executable")

        result = get_compact_diff(project_dir, base_branch)

        assert "old mode" in result
        assert "new mode" in result


@pytest.mark.git_integration
class TestCompactDiffBinaryAndEmpty:
    """Integration tests for binary files and empty file create/delete."""

    def test_binary_change_appears_in_compact_diff(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """A new binary file shows Binary header."""
        repo, project_dir = git_repo_with_commit
        base_branch = get_current_branch_name(project_dir)
        assert base_branch is not None

        repo.git.checkout("-b", "feature-binary")

        # Create a binary file (PNG header bytes)
        binary_file = project_dir / "image.png"
        binary_file.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        )
        repo.index.add(["image.png"])
        repo.index.commit("Add binary image")

        result = get_compact_diff(project_dir, base_branch)

        assert "Binary" in result or "binary" in result

    def test_empty_file_creation_appears_in_compact_diff(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """A new empty file shows 'new file mode' header."""
        repo, project_dir = git_repo_with_commit
        base_branch = get_current_branch_name(project_dir)
        assert base_branch is not None

        repo.git.checkout("-b", "feature-empty-create")

        empty_file = project_dir / "empty.py"
        empty_file.write_text("")
        repo.index.add(["empty.py"])
        repo.index.commit("Add empty file")

        result = get_compact_diff(project_dir, base_branch)

        assert "new file mode" in result

    def test_empty_file_deletion_appears_in_compact_diff(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        """Deleting an empty file shows 'deleted file mode' header."""
        repo, project_dir = git_repo_with_commit

        # Add an empty file on the base branch
        empty_file = project_dir / "to_delete.py"
        empty_file.write_text("")
        repo.index.add(["to_delete.py"])
        repo.index.commit("Add empty file for deletion")

        base_branch = get_current_branch_name(project_dir)
        assert base_branch is not None

        repo.git.checkout("-b", "feature-empty-delete")

        # Delete the file
        empty_file.unlink()
        repo.index.remove(["to_delete.py"])
        repo.index.commit("Delete empty file")

        result = get_compact_diff(project_dir, base_branch)

        assert "deleted file mode" in result
