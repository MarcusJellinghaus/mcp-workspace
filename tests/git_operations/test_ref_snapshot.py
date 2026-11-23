"""Tests for reading a reference project at ``origin/<default>``."""

# pylint cannot narrow open_ref_snapshot's RefSnapshot | RefFallback through
# _snapshot's isinstance check, so it reports every snapshot attribute.
# pylint: disable=no-member

import os
import stat
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from git import Repo
from git.exc import InvalidGitRepositoryError, NoSuchPathError

from mcp_workspace.git_operations import core
from mcp_workspace.git_operations.ref_snapshot import (
    RefFallback,
    RefSnapshot,
    open_ref_snapshot,
)

pytestmark = pytest.mark.git_integration

NAME = "proj"
MakeClone = Callable[[str], Path]
_CLOSE_TARGET = "mcp_workspace.git_operations.ref_snapshot._close_repo_safely"
_REAL_CLOSE = core._close_repo_safely  # pylint: disable=protected-access


@contextmanager
def _repo(path: Path) -> Iterator[Repo]:
    """Open a repository for a test helper and close it afterwards."""
    repo = Repo(path)
    try:
        yield repo
    finally:
        repo.close()


def _git(path: Path, *args: str) -> str:
    """Run a git command in ``path`` and return its stdout."""
    with _repo(path) as repo:
        return str(repo.git.execute(["git", *args]))


def _commit(clone: Path, files: dict[str, bytes], message: str = "change") -> str:
    """Write ``files`` byte-exact, commit them, and return the new HEAD SHA."""
    for rel, data in files.items():
        target = clone / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    _git(clone, "config", "core.autocrlf", "false")
    _git(clone, "add", "--", *files)
    _git(clone, "commit", "-q", "-m", message)
    return _git(clone, "rev-parse", "HEAD")


def _push(clone: Path) -> None:
    """Push the clone's HEAD to ``main`` on origin."""
    _git(clone, "push", "-q", "origin", "HEAD:refs/heads/main")


def _origin_main(path: Path) -> str:
    """Return the SHA of ``refs/remotes/origin/main`` in ``path``."""
    return _git(path, "rev-parse", "refs/remotes/origin/main")


def _init_repo(path: Path) -> Path:
    """Create a repository with one commit and no remotes."""
    Repo.init(path).close()
    _git(path, "config", "user.name", "Test User")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "commit.gpgsign", "false")
    _commit(path, {"local.txt": b"local\n"})
    return path


def _snapshot(result: RefSnapshot | RefFallback) -> RefSnapshot:
    """Narrow an ``open_ref_snapshot`` result to a snapshot."""
    assert isinstance(result, RefSnapshot), result
    return result


def _plain_folder(tmp_path: Path) -> Path:
    path = tmp_path / "plain"
    path.mkdir()
    (path / "file.txt").write_text("x\n")
    return path


def _missing_folder(tmp_path: Path) -> Path:
    return tmp_path / "missing"


def _empty_git_dir(tmp_path: Path) -> Path:
    path = tmp_path / "empty_git"
    (path / ".git").mkdir(parents=True)
    return path


def _git_file_pointing_nowhere(tmp_path: Path) -> Path:
    path = tmp_path / "gitfile"
    path.mkdir()
    (path / ".git").write_text("gitdir: ../nowhere\n")
    return path


def _git_dir_with_only_head(tmp_path: Path) -> Path:
    path = tmp_path / "only_head"
    (path / ".git").mkdir(parents=True)
    (path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    return path


@pytest.fixture
def ref_work(make_clone: MakeClone) -> Path:
    """Work clone of an origin whose main holds a known tree.

    The tree also holds a symlink ``link`` and a gitlink ``sub``.
    """
    up = make_clone("up")
    _commit(
        up,
        {
            "CLAUDE.md": b"# Claude\n",
            "crlf.txt": b"one\r\ntwo\r\n",
            "src/a.py": b"print('a')\n",
            "src/b/c.txt": b"c\n",
            "z.txt": b"z\n",
        },
    )
    blob = _git(up, "hash-object", "-w", "--", "z.txt")
    head = _git(up, "rev-parse", "HEAD")
    _git(up, "update-index", "--add", "--cacheinfo", f"120000,{blob},link")
    _git(up, "update-index", "--add", "--cacheinfo", f"160000,{head},sub")
    _git(up, "commit", "-q", "-m", "link and gitlink")
    _push(up)
    return make_clone("work")


class TestUpstreamContentWins:
    """The snapshot reads origin's default branch, not the working tree."""

    def test_feature_branch_with_different_commit(self, make_clone: MakeClone) -> None:
        """A checked-out feature branch does not change what is read."""
        up = make_clone("up")
        _commit(up, {"data.txt": b"upstream\n"})
        _push(up)
        work = make_clone("work")
        _git(work, "checkout", "-q", "-b", "feature")
        _commit(work, {"data.txt": b"feature\n"})

        with open_ref_snapshot(work, NAME) as result:
            snap = _snapshot(result)
            assert snap.read_bytes("data.txt") == b"upstream\n"
            assert snap.ref == "origin/main"
            assert snap.sha == _origin_main(work)

    def test_dirty_working_tree(self, make_clone: MakeClone) -> None:
        """Uncommitted and untracked files are not read."""
        up = make_clone("up")
        _commit(up, {"data.txt": b"upstream\n"})
        _push(up)
        work = make_clone("work")
        (work / "data.txt").write_bytes(b"dirty\n")
        (work / "untracked.txt").write_bytes(b"untracked\n")

        with open_ref_snapshot(work, NAME) as result:
            snap = _snapshot(result)
            assert snap.read_bytes("data.txt") == b"upstream\n"
            with pytest.raises(FileNotFoundError):
                snap.read_bytes("untracked.txt")

    def test_behind_origin_after_fetch(self, make_clone: MakeClone) -> None:
        """After a fetch, the snapshot reads origin even though main is behind."""
        work = make_clone("work")
        local_head = _git(work, "rev-parse", "HEAD")
        up = make_clone("up")
        upstream_sha = _commit(up, {"data.txt": b"newer\n"})
        _push(up)
        _git(work, "fetch", "-q", "origin")

        with open_ref_snapshot(work, NAME) as result:
            snap = _snapshot(result)
            assert snap.read_bytes("data.txt") == b"newer\n"
            assert snap.ref == "origin/main"
            assert snap.sha == upstream_sha
        assert _git(work, "rev-parse", "HEAD") == local_head


class TestDefaultRef:
    """Resolution of the origin default branch."""

    def test_origin_head_is_labelled_by_its_target(self, origin_clone: Path) -> None:
        """``origin/HEAD`` resolves and is named after the branch it points at."""
        sha = _origin_main(origin_clone)
        with open_ref_snapshot(origin_clone, NAME) as result:
            snap = _snapshot(result)
            assert snap.ref == "origin/main"
            assert snap.sha == sha
            assert snap.where == f"origin/main @ {sha[:7]}"
            assert snap.name == NAME

    def test_dangling_origin_head_falls_through_to_main(
        self, origin_clone: Path
    ) -> None:
        """An ``origin/HEAD`` pointing at a missing branch is skipped."""
        _git(
            origin_clone,
            "symbolic-ref",
            "refs/remotes/origin/HEAD",
            "refs/remotes/origin/gone",
        )
        with open_ref_snapshot(origin_clone, NAME) as result:
            snap = _snapshot(result)
            assert snap.ref == "origin/main"
            assert snap.sha == _origin_main(origin_clone)

    def test_only_origin_master(self, origin_clone: Path) -> None:
        """Without ``origin/HEAD`` and ``origin/main``, ``origin/master`` is read."""
        sha = _origin_main(origin_clone)
        _git(origin_clone, "update-ref", "refs/remotes/origin/master", sha)
        _git(origin_clone, "remote", "set-head", "origin", "-d")
        _git(origin_clone, "update-ref", "-d", "refs/remotes/origin/main")

        with open_ref_snapshot(origin_clone, NAME) as result:
            snap = _snapshot(result)
            assert snap.ref == "origin/master"
            assert snap.sha == sha

    def test_detached_origin_head_keeps_its_own_name(self, origin_clone: Path) -> None:
        """A non-symbolic ``origin/HEAD`` is labelled ``origin/HEAD``."""
        sha = _origin_main(origin_clone)
        _git(origin_clone, "update-ref", "--no-deref", "refs/remotes/origin/HEAD", sha)

        with open_ref_snapshot(origin_clone, NAME) as result:
            snap = _snapshot(result)
            assert snap.ref == "origin/HEAD"
            assert snap.sha == sha

    def test_local_branch_does_not_shadow_remote_ref(self, origin_clone: Path) -> None:
        """A local branch named ``origin/main`` is not what gets read."""
        upstream_sha = _origin_main(origin_clone)
        local_sha = _commit(origin_clone, {"data.txt": b"local\n"})
        _git(origin_clone, "branch", "origin/main", local_sha)
        _git(origin_clone, "remote", "set-head", "origin", "-d")

        with open_ref_snapshot(origin_clone, NAME) as result:
            snap = _snapshot(result)
            assert snap.ref == "origin/main"
            assert snap.sha == upstream_sha


class TestFallbacks:
    """Folders that cannot be read at a ref."""

    def test_repo_without_remotes(self, tmp_path: Path) -> None:
        """A repository without remotes has no default ref."""
        path = _init_repo(tmp_path / "repo")
        with open_ref_snapshot(path, NAME) as result:
            assert result is RefFallback.NO_DEFAULT

    def test_origin_without_tracking_refs(self, tmp_path: Path) -> None:
        """An ``origin`` that was never fetched has no default ref."""
        path = _init_repo(tmp_path / "repo")
        _git(path, "remote", "add", "origin", "https://example.invalid/x.git")
        with open_ref_snapshot(path, NAME) as result:
            assert result is RefFallback.NO_DEFAULT

    def test_git_dir_without_config(self, tmp_path: Path) -> None:
        """A ``.git`` with HEAD, objects and refs but no config has no default."""
        path = tmp_path / "noconfig"
        (path / ".git" / "objects").mkdir(parents=True)
        (path / ".git" / "refs").mkdir()
        (path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
        with open_ref_snapshot(path, NAME) as result:
            assert result is RefFallback.NO_DEFAULT

    @pytest.mark.parametrize(
        "build",
        [
            _plain_folder,
            _missing_folder,
            _empty_git_dir,
            _git_file_pointing_nowhere,
            _git_dir_with_only_head,
        ],
        ids=lambda build: build.__name__.lstrip("_"),
    )
    def test_not_a_repo(self, tmp_path: Path, build: Callable[[Path], Path]) -> None:
        """Plain, missing and broken folders are not repositories."""
        path = build(tmp_path)
        with open_ref_snapshot(path, NAME) as result:
            assert result is RefFallback.NOT_A_REPO

    def test_plain_folder_inside_checkout(self, origin_clone: Path) -> None:
        """A folder nested in a checkout is not read from the parent repo."""
        nested = origin_clone / "nested"
        nested.mkdir()
        with open_ref_snapshot(nested, NAME) as result:
            assert result is RefFallback.NOT_A_REPO

    def test_corrupt_default_ref_raises_value_error(self, origin_clone: Path) -> None:
        """A default ref naming a missing object is an error, not a fallback."""
        ref_file = origin_clone / ".git" / "refs" / "remotes" / "origin" / "main"
        ref_file.parent.mkdir(parents=True, exist_ok=True)
        ref_file.write_text("1234567890" * 4 + "\n")

        with pytest.raises(ValueError, match=f"reference '{NAME}'") as info:
            with open_ref_snapshot(origin_clone, NAME):
                pass
        assert type(info.value) is ValueError


class TestListFiles:
    """Listing the files at the ref."""

    def test_order_matches_ls_tree_without_links(self, ref_work: Path) -> None:
        """Files come in ``ls-tree -r`` order; symlinks and gitlinks are left out."""
        with open_ref_snapshot(ref_work, NAME) as result:
            snap = _snapshot(result)
            names = _git(
                ref_work, "ls-tree", "-r", "--name-only", snap.sha
            ).splitlines()
            assert "link" in names and "sub" in names
            assert snap.list_files() == [n for n in names if n not in {"link", "sub"}]

    @pytest.mark.parametrize("path", ["link", "sub"])
    def test_links_are_not_found(self, ref_work: Path, path: str) -> None:
        """Reading a symlink or a gitlink is a not-found."""
        with open_ref_snapshot(ref_work, NAME) as result:
            snap = _snapshot(result)
            with pytest.raises(FileNotFoundError):
                snap.read_bytes(path)


class TestReadBytes:
    """Reading one file at the ref."""

    def test_crlf_bytes_kept_exactly(self, ref_work: Path) -> None:
        """Blob bytes come back unchanged, CRLF included."""
        with open_ref_snapshot(ref_work, NAME) as result:
            assert _snapshot(result).read_bytes("crlf.txt") == b"one\r\ntwo\r\n"

    def test_nested_file(self, ref_work: Path) -> None:
        """A file below two directories is found."""
        with open_ref_snapshot(ref_work, NAME) as result:
            assert _snapshot(result).read_bytes("src/b/c.txt") == b"c\n"

    def test_not_found_names_ref_sha_and_reference(self, ref_work: Path) -> None:
        """The not-found message names the ref, the short SHA and the reference."""
        with open_ref_snapshot(ref_work, NAME) as result:
            snap = _snapshot(result)
            with pytest.raises(FileNotFoundError) as info:
                snap.read_bytes("nope.txt")
            assert str(info.value) == (
                f"File 'nope.txt' is not in origin/main @ {snap.sha[:7]} "
                f"of reference '{NAME}'."
            )

    def test_case_hint(self, ref_work: Path) -> None:
        """A path differing only in case gets the tree's spelling as a hint."""
        with open_ref_snapshot(ref_work, NAME) as result:
            snap = _snapshot(result)
            with pytest.raises(FileNotFoundError) as info:
                snap.read_bytes("claude.md")
            assert str(info.value) == (
                f"File 'claude.md' is not in {snap.where} of reference '{NAME}'; "
                "did you mean 'CLAUDE.md'?"
            )

    def test_path_through_a_file_is_not_found(self, ref_work: Path) -> None:
        """A path that continues past a file is a not-found."""
        with open_ref_snapshot(ref_work, NAME) as result:
            with pytest.raises(FileNotFoundError):
                _snapshot(result).read_bytes("z.txt/x")

    @pytest.mark.parametrize("path", ["src", "src/b"])
    def test_directory(self, ref_work: Path, path: str) -> None:
        """A directory is not a file."""
        with open_ref_snapshot(ref_work, NAME) as result:
            with pytest.raises(IsADirectoryError) as info:
                _snapshot(result).read_bytes(path)
            assert str(info.value) == f"Path '{path}' is not a file"

    @pytest.mark.parametrize(
        ("path", "display_path", "error", "template"),
        [
            (
                "src/x.py",
                "src\\x.py",
                FileNotFoundError,
                "File 'src\\x.py' is not in {where} of reference '{name}'.",
            ),
            ("src", "./src/", IsADirectoryError, "Path './src/' is not a file"),
            ("", "./", IsADirectoryError, "Path './' is not a file"),
            (
                "src/x.py",
                None,
                FileNotFoundError,
                "File 'src/x.py' is not in {where} of reference '{name}'.",
            ),
            ("src", None, IsADirectoryError, "Path 'src' is not a file"),
            ("", None, IsADirectoryError, "Path '' is not a file"),
        ],
    )
    def test_messages_use_display_path(
        self,
        ref_work: Path,
        path: str,
        display_path: str | None,
        error: type[Exception],
        template: str,
    ) -> None:
        """Messages name the caller's text verbatim, else the tree path."""
        with open_ref_snapshot(ref_work, NAME) as result:
            snap = _snapshot(result)
            with pytest.raises(error) as info:
                snap.read_bytes(path, display_path)
            assert type(info.value) is error
            assert str(info.value) == template.format(where=snap.where, name=NAME)

    def test_missing_blob_object_raises_value_error(
        self, make_clone: MakeClone
    ) -> None:
        """A blob missing from the object database is a ``ValueError``."""
        work = make_clone("work")
        up = make_clone("up")
        _commit(up, {"new.txt": b"new\n"})
        _push(up)
        _git(work, "config", "fetch.unpackLimit", "100000")
        _git(work, "config", "transfer.unpackLimit", "100000")
        _git(work, "fetch", "-q", "origin")
        blob = _git(work, "rev-parse", "refs/remotes/origin/main:new.txt")
        loose = work / ".git" / "objects" / blob[:2] / blob[2:]
        if not loose.exists():
            pytest.skip("blob object stayed packed")
        os.chmod(loose, stat.S_IREAD | stat.S_IWRITE)
        loose.unlink()

        with open_ref_snapshot(work, NAME) as result:
            snap = _snapshot(result)
            with pytest.raises(ValueError, match=f"reference '{NAME}'") as info:
                snap.read_bytes("new.txt")
            assert type(info.value) is ValueError

    def test_root_tree_resolved_once(self, ref_work: Path) -> None:
        """Several reads on one snapshot resolve the commit's tree once."""
        with open_ref_snapshot(ref_work, NAME) as result:
            snap = _snapshot(result)
            with patch.object(snap.repo, "commit", wraps=snap.repo.commit) as spy:
                for path in ("CLAUDE.md", "src/a.py", "src/b/c.txt"):
                    snap.read_bytes(path)
            assert spy.call_count == 1
            assert snap.tree is snap.tree


class TestRepoLifetime:
    """Environment and closing of the snapshot's repository."""

    def test_noninteractive_environment(self, origin_clone: Path) -> None:
        """Git commands run for the snapshot never prompt."""
        with open_ref_snapshot(origin_clone, NAME) as result:
            env = _snapshot(result).repo.git.environment()
            assert env["GIT_TERMINAL_PROMPT"] == "0"

    def test_repo_closed_after_snapshot(self, origin_clone: Path) -> None:
        """The repository is closed when the context exits, not before."""
        with patch(_CLOSE_TARGET, wraps=_REAL_CLOSE) as close:
            with open_ref_snapshot(origin_clone, NAME) as result:
                snap = _snapshot(result)
                snap.list_files()
                close.assert_not_called()
        close.assert_called_once_with(snap.repo)

    def test_repo_closed_after_no_default(self, tmp_path: Path) -> None:
        """A repository without a default ref is closed too."""
        path = _init_repo(tmp_path / "repo")
        with patch(_CLOSE_TARGET, wraps=_REAL_CLOSE) as close:
            with open_ref_snapshot(path, NAME) as result:
                assert result is RefFallback.NO_DEFAULT
        close.assert_called_once()

    def test_body_exception_passes_through(self, origin_clone: Path) -> None:
        """An exception from the caller's body is neither caught nor replaced."""
        error = InvalidGitRepositoryError("from body")
        with patch(_CLOSE_TARGET, wraps=_REAL_CLOSE) as close:
            with pytest.raises(InvalidGitRepositoryError) as info:
                with open_ref_snapshot(origin_clone, NAME):
                    raise error
        assert info.value is error
        close.assert_called_once()

    def test_body_exception_passes_through_fallback(self, tmp_path: Path) -> None:
        """A fallback's body exception propagates unchanged."""
        error = NoSuchPathError("from body")
        with pytest.raises(NoSuchPathError) as info:
            with open_ref_snapshot(tmp_path / "missing", NAME) as result:
                assert result is RefFallback.NOT_A_REPO
                raise error
        assert info.value is error
