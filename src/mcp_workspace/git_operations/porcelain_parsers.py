"""Pure parsers for NUL-separated (``-z``) git porcelain output.

No git calls and no repositories: every function takes raw stdout bytes.
Paths are decoded as UTF-8 (invalid bytes replaced).
"""

from typing import NamedTuple, Optional


class StatusEntry(NamedTuple):
    """One entry of ``git status --porcelain=v1 -z``."""

    # Not ``index``: that would shadow ``tuple.index``
    index_status: str  # X
    worktree_status: str  # Y
    path: str
    orig_path: Optional[str]  # rename/copy source


def _decode(raw: bytes) -> str:
    """Decode a path field as UTF-8."""
    return raw.decode("utf-8", errors="replace")


def parse_status_z(output: bytes) -> list[StatusEntry]:
    """Parse ``git status --porcelain=v1 -z`` output.

    Args:
        output: Raw stdout bytes

    Returns:
        Entries in output order; a rename or copy carries its source path in
        ``orig_path``. Empty output returns an empty list.
    """
    fields = output.split(b"\0")
    entries: list[StatusEntry] = []
    i = 0
    while i < len(fields):
        field = fields[i]
        if not field:
            i += 1
            continue
        x, y, path = chr(field[0]), chr(field[1]), _decode(field[3:])
        orig_path = None
        if x in "RC" and i + 1 < len(fields):
            orig_path = _decode(fields[i + 1])
            i += 1
        entries.append(StatusEntry(x, y, path, orig_path))
        i += 1
    return entries


def parse_merge_tree_z(output: bytes) -> tuple[Optional[str], list[str]]:
    """Parse ``git merge-tree --write-tree --name-only --no-messages -z`` output.

    Args:
        output: Raw stdout bytes: ``<tree>\\0<path>\\0...``

    Returns:
        ``(tree_oid, paths)``; ``tree_oid`` is None for empty output. Each
        conflicted path is listed once, in output order.
    """
    fields = [field for field in output.split(b"\0") if field]
    if not fields:
        return None, []
    paths: list[str] = []
    for field in fields[1:]:
        path = _decode(field)
        if path not in paths:
            paths.append(path)
    return _decode(fields[0]), paths


def parse_ls_remote_heads(output: bytes) -> list[str]:
    """Parse ``git ls-remote --heads`` output.

    Args:
        output: Raw stdout bytes: ``<sha>\\trefs/heads/<name>\\n``...

    Returns:
        Branch names without the ``refs/heads/`` prefix, in output order.
        Empty output returns an empty list.
    """
    branches: list[str] = []
    for line in output.splitlines():
        _, sep, ref = line.partition(b"\t")
        if not sep:
            continue
        branches.append(_decode(ref.strip()).removeprefix("refs/heads/"))
    return branches
