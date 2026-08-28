"""Tree-based directory listing with collapsing and truncation.

Builds a tree from flat file paths, supports auto-collapsing of large
directories, and renders back to a flat list of path strings.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

_COLLAPSE_THRESHOLD = 250


@dataclass
class _TreeNode:
    """Internal tree node representing a directory."""

    name: str
    children: Dict[str, "_TreeNode"] = field(default_factory=dict)
    files: List[str] = field(default_factory=list)
    collapsed: bool = False
    collapsed_file_count: int = 0


def _build_tree(file_paths: List[str], base_path: str) -> _TreeNode:
    """Build tree from flat file paths.

    Args:
        file_paths: List of project-relative file paths.
        base_path: Path prefix to strip from each path for tree building.

    Returns:
        Root tree node.
    """
    root = _TreeNode(name="")
    strip_prefix = ""
    if base_path not in (".", ""):
        strip_prefix = base_path.rstrip("/") + "/"

    for file_path in file_paths:
        # Normalize separators so split("/") works on Windows
        file_path = file_path.replace("\\", "/")
        # Strip base_path prefix for tree building
        rel_path = file_path
        if strip_prefix and file_path.startswith(strip_prefix):
            rel_path = file_path[len(strip_prefix) :]

        parts = rel_path.split("/")
        node = root

        # Walk/create directory nodes for all parts except the last (filename)
        for dir_part in parts[:-1]:
            if dir_part not in node.children:
                node.children[dir_part] = _TreeNode(name=dir_part)
            node = node.children[dir_part]

        # Add filename to leaf node
        node.files.append(parts[-1])

    return root


def _count_lines(node: _TreeNode, dirs_only: bool) -> int:
    """Count how many output lines the tree would produce.

    Returns:
        Number of output lines for this node's subtree.
    """
    if node.collapsed:
        return 1
    count = 0
    for child in node.children.values():
        if child.collapsed:
            count += 1
        else:
            if dirs_only:
                count += 1  # the dir line itself
            count += _count_lines(child, dirs_only)
    if not dirs_only:
        count += len(node.files)
    return count


def _recursive_file_count(node: _TreeNode) -> int:
    """Count all files recursively under a node (post-collapse).

    Returns:
        Total number of files in the node's subtree.
    """
    total = len(node.files)
    for child in node.children.values():
        total += _recursive_file_count(child)
    return total


def _score(node: _TreeNode, depth: int) -> float:
    """Score a node for collapse priority.

    Returns:
        (len(files) + len(children) * 0.3) * depth.
    """
    return (len(node.files) + len(node.children) * 0.3) * depth


def _find_collapsible(
    node: _TreeNode, depth: int
) -> List[Tuple[float, str, _TreeNode]]:
    """Find all collapsible directories (depth >= 2, not already collapsed).

    Returns:
        List of (score, name, node) tuples for collapsible directories.
    """
    results: List[Tuple[float, str, _TreeNode]] = []
    for child in node.children.values():
        if depth >= 2 and not child.collapsed:
            results.append((_score(child, depth), child.name, child))
        results.extend(_find_collapsible(child, depth + 1))
    return results


def _collapse(root: _TreeNode, dirs_only: bool) -> None:
    """Greedy loop: while line_count > 250, collapse highest-scoring dir."""
    while _count_lines(root, dirs_only) > _COLLAPSE_THRESHOLD:
        candidates = _find_collapsible(root, depth=1)
        if not candidates:
            break
        candidates.sort(key=lambda x: (-x[0], x[1]))
        _, _, target = candidates[0]
        target.collapsed = True
        target.collapsed_file_count = _recursive_file_count(target)
        target.children.clear()
        target.files.clear()


def _render(node: _TreeNode, prefix: str, dirs_only: bool) -> List[str]:
    """Render tree to flat list of path strings.

    Args:
        node: Tree node to render.
        prefix: Path prefix to prepend (includes base_path for project-relative output).
        dirs_only: If True, only include directory entries (not files).

    Returns:
        List of rendered path strings.
    """
    results: List[str] = []

    for child_name in sorted(node.children):
        child_node = node.children[child_name]
        child_prefix = prefix + child_name + "/"
        if child_node.collapsed:
            if child_node.collapsed_file_count > 0:
                count = child_node.collapsed_file_count
                results.append(f"{child_prefix} ({count} files)")
            else:
                results.append(child_prefix)
        else:
            if dirs_only:
                results.append(child_prefix)
            results.extend(_render(child_node, child_prefix, dirs_only))

    if not dirs_only:
        for filename in sorted(node.files):
            results.append(prefix + filename)

    return results


def _truncate(lines: List[str], limit: int = _COLLAPSE_THRESHOLD) -> List[str]:
    """If lines exceed limit, keep first `limit` entries and append summary.

    Returns:
        The lines unchanged if within limit, otherwise the first `limit`
        entries plus a summary line.
    """
    if len(lines) <= limit:
        return lines
    kept = lines[:limit]
    remaining = lines[limit:]
    remaining_dirs = sum(1 for line in remaining if line.endswith("/") or "/ (" in line)
    remaining_files = len(remaining) - remaining_dirs
    total = len(lines)
    # The 250-line cap is deliberate: list_directory has no lift parameter and
    # is not getting one. Callers narrow instead - path=<subdir>, dirs_only=True,
    # or search_files for targeted lookups.
    summary = (
        f"... and {len(remaining)} more entries "
        f"({remaining_dirs} dirs, {remaining_files} files) \u2014 {total} total. "
        f"Narrow with path=<subdir> or dirs_only=True."
    )
    return kept + [summary]


def list_directory_tree(
    file_paths: List[str],
    base_path: str = ".",
    dirs_only: bool = False,
) -> List[str]:
    """Build tree from file paths and render back to flat list.

    Builds an internal tree, auto-collapses large deep directories when the
    listing exceeds 250 lines, then truncates if still too long.

    Args:
        file_paths: List of project-relative file paths.
        base_path: Base path for scoping (stripped internally, re-added in output).
        dirs_only: If True, only return directory entries.

    Returns:
        List of project-relative path strings.
    """
    if not file_paths:
        return []

    tree = _build_tree(file_paths, base_path)
    _collapse(tree, dirs_only)
    render_prefix = ""
    if base_path not in (".", ""):
        render_prefix = base_path.rstrip("/") + "/"
    lines = _render(tree, prefix=render_prefix, dirs_only=dirs_only)
    return _truncate(lines)
