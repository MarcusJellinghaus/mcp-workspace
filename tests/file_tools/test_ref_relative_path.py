"""Tests for ref_relative_path: lexical path normalisation for a tree lookup."""

import os
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from mcp_workspace.file_tools.path_utils import ref_relative_path
from tests.conftest import requires_symlinks

# Builds a root under tmp_path; returns it with an absolute input spelled from it.
RootBuilder = Callable[[Path], tuple[Path, str]]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """Provide a reference project root that exists on disk."""
    ref = tmp_path / "ref"
    ref.mkdir()
    return ref


@pytest.mark.parametrize(
    "path",
    ["src/x.py", "src\\x.py", "./src/x.py", ".\\src\\x.py", "src//x.py"],
)
def test_relative_spellings_give_forward_slash_path(path: str, root: Path) -> None:
    """Relative paths in any separator style map to the same tree path."""
    assert ref_relative_path(path, root) == "src/x.py"


def test_absolute_path_inside_root(root: Path) -> None:
    """An absolute path under the root is made relative to it."""
    assert ref_relative_path(str(root / "src" / "x.py"), root) == "src/x.py"


@pytest.mark.parametrize("path", [".", "./", ".\\"])
def test_root_itself_gives_empty_string(path: str, root: Path) -> None:
    """The root itself maps to the empty tree path."""
    assert ref_relative_path(path, root) == ""


def test_absolute_root_gives_empty_string(root: Path) -> None:
    """The root's own absolute path maps to the empty tree path."""
    assert ref_relative_path(str(root), root) == ""
    assert ref_relative_path(str(root.resolve()), root) == ""


def _dot_segment_root(tmp_path: Path) -> tuple[Path, str]:
    """Build a root reached through a '.' segment.

    Returns:
        The root and the absolute input string that keeps the '.' segment.
    """
    root = tmp_path / "a" / "." / "ref"
    root.mkdir(parents=True)
    spelled = os.path.join(str(tmp_path), "a", ".", "ref", "src", "x.py")
    return root, spelled


def _symlinked_parent_root(tmp_path: Path) -> tuple[Path, str]:
    """Build a root whose parent is a directory symlink.

    Returns:
        The unresolved root and the absolute input built from it.
    """
    real = tmp_path / "real"
    (real / "ref").mkdir(parents=True)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    root = link / "ref"
    return root, str(root / "src" / "x.py")


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(_dot_segment_root, id="dot-segment"),
        pytest.param(
            _symlinked_parent_root, id="symlinked-parent", marks=requires_symlinks
        ),
    ],
)
def test_unresolved_root_matches_lexical_and_resolved_inputs(
    build: RootBuilder, tmp_path: Path
) -> None:
    """Inputs built from the unresolved root and from the resolved root both match."""
    root, spelled = build(tmp_path)
    assert ref_relative_path(spelled, root) == "src/x.py"
    assert ref_relative_path(str(root / "src" / "x.py"), root) == "src/x.py"
    assert ref_relative_path(str(root.resolve() / "src" / "x.py"), root) == "src/x.py"


def test_plain_tmp_path_root_matches_both_spellings(tmp_path: Path) -> None:
    """tmp_path may sit under a symlink (macOS /var) or 8.3 names (Windows)."""
    assert ref_relative_path(str(tmp_path / "src" / "x.py"), tmp_path) == "src/x.py"
    assert (
        ref_relative_path(str(tmp_path.resolve() / "src" / "x.py"), tmp_path)
        == "src/x.py"
    )


@pytest.mark.skipif(sys.platform != "win32", reason="Windows drive letters")
def test_windows_drive_case_and_mixed_separators(root: Path) -> None:
    """Drive-letter case and separator style do not matter on Windows."""
    absolute = str(root.resolve() / "src" / "x.py")
    swapped = absolute[0].swapcase() + absolute[1:]
    mixed = swapped.replace("\\", "/", 2)
    assert ref_relative_path(swapped, root) == "src/x.py"
    assert ref_relative_path(mixed, root) == "src/x.py"
    assert ref_relative_path(absolute.replace("\\", "/"), root) == "src/x.py"


@pytest.mark.parametrize("path", ["../x", "src/../x", "..\\x", "src\\..\\x"])
def test_dotdot_is_rejected(path: str, root: Path) -> None:
    """A '..' segment anywhere is rejected as traversal."""
    with pytest.raises(ValueError, match="traversal"):
        ref_relative_path(path, root)


def test_absolute_dotdot_into_root_is_rejected(root: Path) -> None:
    """A '..' segment cannot be stripped away by the root prefix."""
    path = str(root) + os.sep + ".." + os.sep + "ref" + os.sep + "x.py"
    with pytest.raises(ValueError, match="traversal"):
        ref_relative_path(path, root)


def test_absolute_path_outside_root_is_rejected(tmp_path: Path, root: Path) -> None:
    """An absolute path outside the root is rejected."""
    with pytest.raises(ValueError, match="outside the project directory"):
        ref_relative_path(str(tmp_path / "other" / "x.py"), root)


def test_sibling_with_root_name_prefix_is_rejected(tmp_path: Path, root: Path) -> None:
    """The comparison is per segment, so 'ref2' is not under 'ref'."""
    with pytest.raises(ValueError, match="outside the project directory"):
        ref_relative_path(str(tmp_path / "ref2" / "x.py"), root)


@pytest.mark.parametrize(
    "path", [".git/config", ".GIT/config", ".git./config", "sub/.git/HEAD", ".git"]
)
def test_git_dir_is_rejected(path: str, root: Path) -> None:
    """Any spelling of a .git entry is rejected."""
    with pytest.raises(ValueError, match="inside a git directory"):
        ref_relative_path(path, root)


def test_absolute_git_dir_is_rejected(root: Path) -> None:
    """A .git entry reached through an absolute path is rejected too."""
    with pytest.raises(ValueError, match="inside a git directory"):
        ref_relative_path(str(root / ".git" / "config"), root)


def test_github_dir_is_allowed(root: Path) -> None:
    """Names that only start with .git are ordinary paths."""
    assert ref_relative_path(".github/x.yml", root) == ".github/x.yml"


def test_nul_byte_is_rejected(root: Path) -> None:
    """A NUL byte is rejected with the outside-project error."""
    with pytest.raises(ValueError, match="outside the project directory"):
        ref_relative_path("a\0b", root)


def test_error_texts_match_normalize_path(root: Path) -> None:
    """The traversal message names the caller's path and the root."""
    with pytest.raises(ValueError) as exc_info:
        ref_relative_path("../x", root)
    message = str(exc_info.value)
    assert "'../x'" in message
    assert f"'{root}'" in message
    assert "contains '..' traversal and would escape" in message
