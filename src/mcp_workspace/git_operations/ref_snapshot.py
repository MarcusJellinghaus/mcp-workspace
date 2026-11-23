"""Read a reference project at its ``origin`` default branch.

This module owns every GitPython access needed to read at the ref. Callers
see ``RefSnapshot``, ``RefFallback`` and the builtin exceptions
``ValueError``, ``FileNotFoundError`` and ``IsADirectoryError`` — no
GitPython exception type leaves this module.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from functools import cached_property
from pathlib import Path
from typing import ParamSpec, TypeVar

from git import Repo
from git.exc import BadName, GitCommandError, ODBError
from git.objects import Blob, Submodule, Tree

from mcp_workspace.utils.url_credentials import scrub_credentials

from .core import (
    GIT_NONINTERACTIVE_ENV,
    GIT_SHORT_HASH_LENGTH,
    _close_repo_safely,
    has_origin,
    open_repo_if_any,
    run_git_raw,
)
from .porcelain_parsers import parse_ls_tree_z

_ORIGIN_HEAD = "refs/remotes/origin/HEAD"
# Full ref names only: a short ``origin/main`` can be shadowed by a local
# branch or tag of that name.
_DEFAULT_REF_CANDIDATES = (
    _ORIGIN_HEAD,
    "refs/remotes/origin/main",
    "refs/remotes/origin/master",
)
_REMOTES_PREFIX = "refs/remotes/"
_SYMLINK_MODE = 0o120000
_GIT_ERRORS = (GitCommandError, ODBError, ValueError)

_P = ParamSpec("_P")
_T = TypeVar("_T")


class RefFallback(Enum):
    """Why a folder cannot be read at ``origin/<default>``."""

    NOT_A_REPO = "not_a_repo"  # plain folder, broken/incomplete .git, missing path
    NO_DEFAULT = "no_default"  # git repo without origin, or no default ref resolves


def _guarded(
    name: str, action: Callable[_P, _T], *args: _P.args, **kwargs: _P.kwargs
) -> _T:
    """Run a GitPython action; turn its failures into a scrubbed ``ValueError``.

    Args:
        name: Reference project name, for the message
        action: Callable doing the GitPython work
        *args: Positional arguments for ``action``
        **kwargs: Keyword arguments for ``action``

    Returns:
        Whatever ``action`` returns.

    Raises:
        ValueError: If ``action`` raises a GitPython error or ``ValueError``.
    """
    detail = ""
    try:
        return action(*args, **kwargs)
    except _GIT_ERRORS as exc:
        detail = scrub_credentials(str(exc))
    raise ValueError(f"Git error reading reference '{name}': {detail}")


def _commit_tree(repo: Repo, sha: str) -> Tree:
    """Return the root tree of commit ``sha``."""
    return repo.commit(sha).tree


def _tree_entry(tree: Tree, path: str) -> Blob | Tree | Submodule | None:
    """Return the entry at ``path`` below ``tree``, or None when absent."""
    try:
        return tree[path]
    except KeyError:
        return None


def _blob_bytes(blob: Blob) -> bytes:
    """Return a blob's content from the object database, unaltered."""
    data: bytes = blob.data_stream.read()
    return data


def _label(repo: Repo, full: str) -> str:
    """Return the display name of a resolved default ref (``origin/main``)."""
    if full == _ORIGIN_HEAD:
        returncode, out, _ = run_git_raw(repo, "symbolic_ref", "-q", full)
        target = out.decode("utf-8", errors="replace").strip()
        if returncode == 0 and target:
            return target.removeprefix(_REMOTES_PREFIX)
    return full.removeprefix(_REMOTES_PREFIX)


def _resolve_origin_default(repo: Repo) -> tuple[str, str] | None:
    """Resolve the origin default branch.

    Returns:
        ``(ref_label, sha)``, or None when no candidate resolves. A missing or
        dangling ref falls through to the next candidate; any other failure
        propagates.
    """
    for full in _DEFAULT_REF_CANDIDATES:
        try:
            commit = repo.commit(full)
        except BadName:
            continue
        return _label(repo, full), commit.hexsha
    return None


@dataclass(frozen=True)
class RefSnapshot:
    """A reference project pinned to one commit of its origin default branch."""

    repo: Repo
    name: str  # reference project name, for messages
    ref: str  # e.g. "origin/main"
    sha: str  # full SHA, resolved once per call

    @cached_property
    def tree(self) -> Tree:
        """Root tree of ``sha``, resolved on first use and kept."""
        return _guarded(self.name, _commit_tree, self.repo, self.sha)

    @property
    def where(self) -> str:
        """Ref and short SHA for messages, e.g. ``origin/main @ 03d1741``."""
        return f"{self.ref} @ {self.sha[:GIT_SHORT_HASH_LENGTH]}"

    def list_files(self) -> list[str]:
        """List every file at the ref, in ``git ls-tree -r`` order.

        Returns:
            Repo-relative paths of blobs; symlinks and gitlinks are left out.

        Raises:
            ValueError: If git fails.
        """
        returncode, out, err = _guarded(
            self.name, run_git_raw, self.repo, "ls_tree", "-r", "-z", self.sha
        )
        if returncode != 0:
            raise ValueError(
                f"Git error reading reference '{self.name}': "
                f"{scrub_credentials(err.strip())}"
            )
        return [
            entry["path"]
            for entry in parse_ls_tree_z(out)
            if entry["type"] == "blob" and entry["mode"] != "120000"
        ]

    def read_bytes(self, path: str, display_path: str | None = None) -> bytes:
        """Read one file at the ref.

        Args:
            path: Tree path, as returned by ``ref_relative_path``
            display_path: The caller's original path, used verbatim in error
                messages; defaults to ``path``

        Returns:
            The blob's bytes, unaltered.

        Raises:
            FileNotFoundError: If no file is at ``path`` (symlinks and
                gitlinks included).
            IsADirectoryError: If ``path`` is a directory or the root.
            ValueError: If git fails.
        """  # noqa: DOC502 - _not_found builds the error; _guarded raises ValueError
        shown = path if display_path is None else display_path
        if path == "":
            raise IsADirectoryError(f"Path '{shown}' is not a file")
        tree = self.tree
        entry = _guarded(self.name, _tree_entry, tree, path)
        if isinstance(entry, Tree):
            raise IsADirectoryError(f"Path '{shown}' is not a file")
        if not isinstance(entry, Blob) or entry.mode == _SYMLINK_MODE:
            raise self._not_found(path, shown)
        return _guarded(self.name, _blob_bytes, entry)

    def _not_found(self, path: str, shown: str) -> FileNotFoundError:
        """Build the not-found error for ``path``.

        Returns:
            The error naming ``shown``, the ref and the reference, with the
            tree's spelling as a hint when a file differs only in case.
        """
        folded = path.casefold()
        hint = next(
            (f for f in self.list_files() if f != path and f.casefold() == folded),
            None,
        )
        message = f"File '{shown}' is not in {self.where} of reference '{self.name}'"
        suffix = f"; did you mean '{hint}'?" if hint else "."
        return FileNotFoundError(message + suffix)


@contextmanager
def open_ref_snapshot(path: Path, name: str) -> Iterator[RefSnapshot | RefFallback]:
    """Open a reference project for reading at ``origin/<default>``.

    The repository is opened once and closed when the context exits.
    Exceptions raised by the caller's body pass through unchanged.

    Args:
        path: Folder of the reference project
        name: Reference project name, for messages

    Yields:
        A ``RefSnapshot``, or ``RefFallback.NOT_A_REPO`` for a plain, broken
        or missing folder, or ``RefFallback.NO_DEFAULT`` for a repository
        without ``origin`` or without a resolvable default ref.

    Raises:
        ValueError: If git fails while resolving the default ref.
    """  # noqa: DOC502 - raised by _guarded
    repo = open_repo_if_any(path)
    if repo is None:
        yield RefFallback.NOT_A_REPO
        return
    try:
        repo.git.update_environment(**GIT_NONINTERACTIVE_ENV)
        resolved = (
            _guarded(name, _resolve_origin_default, repo)
            if _guarded(name, has_origin, repo)
            else None
        )
        if resolved is None:
            yield RefFallback.NO_DEFAULT
        else:
            ref, sha = resolved
            yield RefSnapshot(repo=repo, name=name, ref=ref, sha=sha)
    finally:
        _close_repo_safely(repo)
