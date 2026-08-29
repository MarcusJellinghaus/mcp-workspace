"""Tests for tree_listing module."""

from typing import List

from mcp_workspace.file_tools.tree_listing import (
    _build_tree,
    _collapse,
    _count_lines,
    _find_collapsible,
    _recursive_file_count,
    _score,
    _TreeNode,
    _truncate,
    list_directory_tree,
)


class TestListDirectoryTree:
    """Tests for list_directory_tree public API."""

    def test_empty_input(self) -> None:
        """Empty input returns empty list."""
        assert list_directory_tree([]) == []

    def test_flat_files_only(self) -> None:
        """Flat files with no subdirs are returned as-is."""
        paths = ["a.py", "b.py", "c.txt"]
        result = list_directory_tree(paths)
        assert sorted(result) == sorted(paths)

    def test_nested_structure(self) -> None:
        """All paths preserved through tree round-trip."""
        paths = ["src/a.py", "src/b.py", "tests/test_a.py"]
        result = list_directory_tree(paths)
        assert sorted(result) == sorted(paths)

    def test_base_path_stripping(self) -> None:
        """base_path is stripped internally but preserved in output."""
        paths = ["src/utils/a.py", "src/utils/b.py"]
        result = list_directory_tree(paths, base_path="src")
        assert sorted(result) == sorted(paths)

    def test_deeply_nested(self) -> None:
        """Deeply nested path round-trips correctly."""
        paths = ["a/b/c/d/file.txt"]
        result = list_directory_tree(paths)
        assert result == paths

    def test_base_path_dot_is_noop(self) -> None:
        """base_path='.' works as a no-op."""
        paths = ["src/a.py", "tests/test_a.py"]
        result = list_directory_tree(paths, base_path=".")
        assert sorted(result) == sorted(paths)

    def test_base_path_empty_is_noop(self) -> None:
        """base_path='' works as a no-op."""
        paths = ["src/a.py", "tests/test_a.py"]
        result = list_directory_tree(paths, base_path="")
        assert sorted(result) == sorted(paths)

    def test_base_path_with_trailing_slash(self) -> None:
        """base_path with trailing slash works correctly."""
        paths = ["src/utils/a.py"]
        result = list_directory_tree(paths, base_path="src/")
        assert result == paths

    def test_multiple_files_in_nested_dirs(self) -> None:
        """Multiple files across multiple nested directories."""
        paths = [
            "src/a.py",
            "src/utils/b.py",
            "src/utils/helpers/c.py",
            "tests/test_a.py",
            "README.md",
        ]
        result = list_directory_tree(paths)
        assert sorted(result) == sorted(paths)


class TestSortOrder:
    """Tests for deterministic sort order: dirs first, alphabetical."""

    def test_dirs_before_files_alphabetical(self) -> None:
        """Dirs first at root, both groups alphabetical."""
        paths = ["z.py", "a.py", "tests/b.py", "src/x.py", "src/a.py"]
        result = list_directory_tree(paths)
        assert result == ["src/a.py", "src/x.py", "tests/b.py", "a.py", "z.py"]

    def test_sort_at_every_level(self) -> None:
        """Sort applies at every nesting level, not just root."""
        paths = [
            "src/z.py",
            "src/a.py",
            "src/utils/z.py",
            "src/utils/a.py",
            "src/core/x.py",
        ]
        result = list_directory_tree(paths)
        assert result == [
            "src/core/x.py",
            "src/utils/a.py",
            "src/utils/z.py",
            "src/a.py",
            "src/z.py",
        ]

    def test_dirs_only_false_no_dir_lines(self) -> None:
        """Default mode produces file paths only, no directory lines."""
        paths = ["src/a.py", "b.py"]
        result = list_directory_tree(paths, dirs_only=False)
        assert result == ["src/a.py", "b.py"]
        assert not any(entry.endswith("/") for entry in result)


class TestDirsOnlyMode:
    """Tests for dirs_only=True mode."""

    def test_dirs_only_basic(self) -> None:
        """Only directories shown, each with trailing /."""
        paths = ["z.py", "a.py", "tests/b.py", "src/x.py", "src/a.py"]
        result = list_directory_tree(paths, dirs_only=True)
        assert result == ["src/", "tests/"]

    def test_dirs_only_nested(self) -> None:
        """Nested dirs shown with full path and trailing /."""
        paths = ["src/utils/a.py", "src/core/b.py", "tests/test_a.py"]
        result = list_directory_tree(paths, dirs_only=True)
        assert result == ["src/", "src/core/", "src/utils/", "tests/"]

    def test_dirs_only_no_files(self) -> None:
        """Files completely excluded in dirs_only mode."""
        paths = ["a.py", "b.txt", "src/c.py"]
        result = list_directory_tree(paths, dirs_only=True)
        assert not any(not entry.endswith("/") for entry in result)
        assert "a.py" not in result
        assert "b.txt" not in result

    def test_dirs_only_with_base_path(self) -> None:
        """dirs_only works correctly with base_path."""
        paths = ["src/utils/a.py", "src/core/b.py"]
        result = list_directory_tree(paths, base_path="src", dirs_only=True)
        assert result == ["src/core/", "src/utils/"]


def _make_paths(dirs: List[str], files_per_dir: int, depth: int = 1) -> List[str]:
    """Generate file paths for testing large trees.

    Creates `files_per_dir` files in each directory at each nesting level
    up to `depth`.
    """
    paths: List[str] = []
    for d in dirs:
        for level in range(depth):
            if level == 0:
                prefix = d
            else:
                prefix = d + "/" + "/".join(f"sub{i}" for i in range(level))
            for i in range(files_per_dir):
                paths.append(f"{prefix}/file{i}.py")
    return paths


class TestCollapsing:
    """Tests for auto-collapsing behavior."""

    def test_no_collapsing_needed(self) -> None:
        """Tree with < 250 lines is unchanged."""
        paths = ["src/a.py", "src/b.py", "tests/test_a.py"]
        result = list_directory_tree(paths)
        assert sorted(result) == sorted(paths)

    def test_collapsing_triggers(self) -> None:
        """Tree with > 250 lines is collapsed to <= 250."""
        # Create many dirs at depth 2 with many files each
        dirs = [f"src/pkg{i}" for i in range(30)]
        paths = _make_paths(dirs, files_per_dir=10)
        result = list_directory_tree(paths)
        assert len(result) <= 250

    def test_depth1_protection(self) -> None:
        """Depth-1 dirs are never collapsed."""
        dirs = [f"src/pkg{i}" for i in range(30)]
        paths = _make_paths(dirs, files_per_dir=10)
        result = list_directory_tree(paths)
        # src/ is depth-1, should never be collapsed
        # collapsed lines look like "dir/ (N files)", not like regular file paths
        collapsed = [r for r in result if "(" in r and "files)" in r]
        for line in collapsed:
            # Collapsed entries should be at depth >= 2
            parts = line.split("/")
            assert len(parts) >= 2  # at least "src/pkgX/ (N files)"

    def test_collapsed_line_format(self) -> None:
        """Collapsed dirs show 'dirname/ (N files)' format."""
        dirs = [f"src/pkg{i}" for i in range(30)]
        paths = _make_paths(dirs, files_per_dir=10)
        result = list_directory_tree(paths)
        collapsed = [r for r in result if "files)" in r]
        assert len(collapsed) > 0
        for line in collapsed:
            assert line.endswith(" files)")
            # Format: "src/pkgN/ (10 files)"
            assert "/ (" in line

    def test_collapsed_format_zero_files(self) -> None:
        """Collapsed dir with no files shows just 'dirname/'."""
        node = _TreeNode(name="empty")
        node.collapsed = True
        node.collapsed_file_count = 0
        # Build a tree with this empty collapsed node at depth 2
        root = _TreeNode(name="")
        parent = _TreeNode(name="src")
        parent.children["empty"] = node
        root.children["src"] = parent
        from mcp_workspace.file_tools.tree_listing import _render

        result = _render(root, "", dirs_only=False)
        assert "src/empty/" in result
        assert not any("files)" in r for r in result if "empty" in r)

    def test_deeper_dirs_collapsed_first(self) -> None:
        """Depth-3 dir collapses before depth-2 with same content."""
        # depth-2 dir: src/shallow/ with 5 files
        # depth-3 dir: src/mid/deep/ with 5 files
        tree = _build_tree(
            [
                *[f"src/shallow/file{i}.py" for i in range(5)],
                *[f"src/mid/deep/file{i}.py" for i in range(5)],
                *[f"src/mid/file{i}.py" for i in range(2)],
            ],
            ".",
        )
        # Score for depth-3 (deep): (5 + 0*0.3) * 3 = 15
        # Score for depth-2 (shallow): (5 + 0*0.3) * 2 = 10
        # Score for depth-2 (mid): (2 + 1*0.3) * 2 = 4.6
        candidates = _find_collapsible(tree, depth=1)
        candidates.sort(key=lambda x: (-x[0], x[1]))
        assert candidates[0][1] == "deep"  # depth-3 first

    def test_scoring_prefers_file_heavy_dirs(self) -> None:
        """Dir with 10 files scores higher than dir with 10 subdirs."""
        # file-heavy: 10 files, 0 children
        file_heavy = _TreeNode(name="files")
        file_heavy.files = [f"f{i}.py" for i in range(10)]

        # subdir-heavy: 0 files, 10 children
        subdir_heavy = _TreeNode(name="subdirs")
        for i in range(10):
            subdir_heavy.children[f"child{i}"] = _TreeNode(name=f"child{i}")

        # At same depth=2: file_heavy=10*2=20, subdir_heavy=3.0*2=6.0
        assert _score(file_heavy, 2) > _score(subdir_heavy, 2)

    def test_root_with_only_files(self) -> None:
        """Root with only files, no dirs → truncated at 250."""
        paths = [f"file{i}.py" for i in range(300)]
        result = list_directory_tree(paths)
        # No dirs to collapse, but truncation applies
        assert len(result) == 251
        assert result[-1].startswith("... and")

    def test_collapsing_applies_to_dirs_only_mode(self) -> None:
        """Collapsing works in dirs_only=True mode."""
        # Need > 250 directory lines
        dirs = [f"src/pkg{i}/sub{j}" for i in range(30) for j in range(10)]
        paths = _make_paths(dirs, files_per_dir=1)
        result = list_directory_tree(paths, dirs_only=True)
        assert len(result) <= 250

    def test_collapsed_file_count_is_recursive(self) -> None:
        """Collapsing a dir with nested subdirs counts all files."""
        node = _TreeNode(name="top")
        child = _TreeNode(name="child")
        child.files = ["a.py", "b.py"]
        grandchild = _TreeNode(name="grandchild")
        grandchild.files = ["c.py", "d.py", "e.py"]
        child.children["grandchild"] = grandchild
        node.children["child"] = child
        node.files = ["root.py"]
        assert _recursive_file_count(node) == 6  # 1 + 2 + 3

    def test_parent_score_stability_after_child_collapse(self) -> None:
        """Parent score unchanged after child collapse."""
        parent = _TreeNode(name="parent")
        parent.files = ["a.py", "b.py"]
        child1 = _TreeNode(name="c1")
        child1.files = ["x.py"]
        child2 = _TreeNode(name="c2")
        child2.files = ["y.py"]
        child3 = _TreeNode(name="c3")
        child3.files = ["z.py"]
        parent.children = {"c1": child1, "c2": child2, "c3": child3}

        score_before = _score(parent, 2)

        # Collapse one child
        child1.collapsed = True
        child1.collapsed_file_count = 1
        child1.files.clear()

        score_after = _score(parent, 2)
        assert score_before == score_after


class TestTruncation:
    """Tests for truncation after collapsing."""

    def test_no_truncation_under_limit(self) -> None:
        """Lines <= 250 are returned unchanged."""
        lines = [f"file{i}.py" for i in range(200)]
        result = _truncate(lines)
        assert result == lines

    def test_no_truncation_at_limit(self) -> None:
        """Exactly 250 lines are returned unchanged."""
        lines = [f"file{i}.py" for i in range(250)]
        result = _truncate(lines)
        assert result == lines

    def test_truncation_triggers(self) -> None:
        """More than 250 lines produces exactly 251 entries (250 + summary)."""
        lines = [f"file{i}.py" for i in range(300)]
        result = _truncate(lines)
        assert len(result) == 251

    def test_summary_line_format(self) -> None:
        """Summary line matches expected format."""
        lines = [f"file{i}.py" for i in range(300)]
        result = _truncate(lines)
        summary = result[-1]
        assert summary == (
            "... and 50 more entries (0 dirs, 50 files) — 300 total. "
            "Narrow with path=<subdir> or dirs_only=True."
        )

    def test_dir_file_counts_in_summary(self) -> None:
        """Summary correctly distinguishes dirs vs files in truncated portion."""
        # Put dirs first (sorted order), then files
        lines = (
            [f"dir{i}/" for i in range(240)]
            + [f"dir{i}/ (5 files)" for i in range(20)]
            + [f"file{i}.py" for i in range(40)]
        )
        # Total = 300, kept = 250, truncated = 50
        # Truncated: 10 collapsed dirs ("dir{10-19}/ (5 files)") + 40 files
        result = _truncate(lines)
        summary = result[-1]
        assert "10 dirs" in summary
        assert "40 files" in summary
        assert "300 total" in summary

    def test_truncation_preserves_order(self) -> None:
        """First 250 entries are kept in original order."""
        lines = [f"src/pkg{i}/" for i in range(130)] + [
            f"file{i}.py" for i in range(130)
        ]
        result = _truncate(lines)
        assert result[:250] == lines[:250]

    def test_truncation_in_dirs_only_mode(self) -> None:
        """In dirs_only mode, all truncated entries count as dirs."""
        lines = [f"src/pkg{i}/" for i in range(300)]
        result = _truncate(lines)
        summary = result[-1]
        assert "50 dirs" in summary
        assert "0 files" in summary

    def test_truncation_via_list_directory_tree(self) -> None:
        """list_directory_tree applies truncation to root-level files."""
        paths = [f"file{i}.py" for i in range(300)]
        result = list_directory_tree(paths)
        assert len(result) == 251
        assert result[-1].startswith("... and")


class TestCountLines:
    """Tests for _count_lines helper."""

    def test_collapsed_node_is_one_line(self) -> None:
        """A collapsed node counts as 1 line."""
        node = _TreeNode(name="pkg")
        node.collapsed = True
        node.collapsed_file_count = 50
        assert _count_lines(node, dirs_only=False) == 1

    def test_files_counted(self) -> None:
        """Each file is one line."""
        node = _TreeNode(name="pkg")
        node.files = ["a.py", "b.py", "c.py"]
        assert _count_lines(node, dirs_only=False) == 3

    def test_dirs_only_counts_dirs(self) -> None:
        """In dirs_only mode, expanded child dirs are lines."""
        root = _TreeNode(name="")
        child1 = _TreeNode(name="a")
        child2 = _TreeNode(name="b")
        root.children = {"a": child1, "b": child2}
        root.files = ["x.py"]
        # dirs_only: 2 dir lines + recurse into children (0 each)
        assert _count_lines(root, dirs_only=True) == 2
