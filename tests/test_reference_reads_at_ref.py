"""The reference file tools read, list and search at origin/<default>."""

import os
import stat
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from git import Repo

from mcp_workspace.file_tools import read_file as read_file_util
from mcp_workspace.git_operations.origin_fetch import FetchOutcome
from mcp_workspace.git_operations.ref_snapshot import RefSnapshot
from mcp_workspace.reference_projects import ReferenceProject
from tests.conftest import ToolMap

pytestmark = [pytest.mark.git_integration, pytest.mark.asyncio]

MakeClone = Callable[[str], Path]
MakeTools = Callable[..., ToolMap]

_FETCH_TARGET = "mcp_workspace.git_operations.origin_fetch.fetch_origin"
_RUN_GIT_TARGET = "mcp_workspace.git_operations.origin_fetch.run_git_timed"
_FALLBACK = "[reference ref: no usable origin default branch — read the local folder]"


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
    """Write ``files`` byte-exact, commit them (ignored ones too), return HEAD."""
    for rel, data in files.items():
        target = clone / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    _git(clone, "config", "core.autocrlf", "false")
    _git(clone, "add", "-f", "--", *files)
    _git(clone, "commit", "-q", "-m", message)
    return _git(clone, "rev-parse", "HEAD")


def _push(clone: Path) -> None:
    """Push the clone's HEAD to ``main`` on origin."""
    _git(clone, "push", "-q", "origin", "HEAD:refs/heads/main")


def _short_main(path: Path) -> str:
    """Return ``origin/main @ <short sha>`` for ``path``."""
    return f"origin/main @ {_git(path, 'rev-parse', 'refs/remotes/origin/main')[:7]}"


def _init_repo(path: Path) -> Path:
    """Create a repository with one commit (``local.txt``) and no remotes."""
    path.mkdir(parents=True)
    Repo.init(path).close()
    _git(path, "config", "user.name", "Test User")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "commit.gpgsign", "false")
    _commit(path, {"local.txt": b"local\n"})
    return path


def _upstream(make_clone: MakeClone, files: dict[str, bytes]) -> Path:
    """Push ``files`` to origin's main from a helper clone ``up``."""
    up = make_clone("up")
    _commit(up, files)
    _push(up)
    return up


def _tools(
    make_tools: MakeTools, path: Path, interval: int = 0, **settings: object
) -> ToolMap:
    """Tools with one reference project ``ref`` at ``path``."""
    return make_tools(
        reference_projects={"ref": ReferenceProject(name="ref", path=path)},
        reference_fetch_interval_minutes=interval,
        **settings,
    )


async def _read(tools: ToolMap, path: str, **kwargs: object) -> str:
    result: str = await tools["read_reference_file"]("ref", path, **kwargs)
    return result


async def _list(tools: ToolMap) -> list[str]:
    result: list[str] = await tools["list_reference_directory"]("ref")
    return result


async def _search(tools: ToolMap, **kwargs: object) -> dict[str, Any]:
    result: dict[str, Any] = await tools["search_reference_files"]("ref", **kwargs)
    return result


def _hit_files(result: dict[str, Any]) -> list[str]:
    """Files of a content search's matches, in result order, without repeats."""
    return list(dict.fromkeys(match["file"] for match in result["details"]))


def _ls_tree(path: Path) -> list[str]:
    """Paths at origin/main of ``path`` in ``git ls-tree -r`` order."""
    return _git(
        path, "ls-tree", "-r", "--name-only", "refs/remotes/origin/main"
    ).splitlines()


# Local folders that are not read at a ref -----------------------------------


def _plain_folder(tmp_path: Path) -> Path:
    path = tmp_path / "plain"
    path.mkdir()
    (path / "file.txt").write_text("x\n", encoding="utf-8")
    return path


def _broken_git(tmp_path: Path) -> Path:
    path = _plain_folder(tmp_path)
    (path / ".git").mkdir()
    return path


def _nested_in_checkout(tmp_path: Path) -> Path:
    outer = _init_repo(tmp_path / "outer")
    _git(outer, "remote", "add", "origin", "https://example.invalid/x.git")
    path = outer / "nested"
    path.mkdir()
    (path / "file.txt").write_text("x\n", encoding="utf-8")
    return path


def _repo_without_origin(tmp_path: Path) -> Path:
    path = _init_repo(tmp_path / "repo")
    (path / "file.txt").write_text("x\n", encoding="utf-8")
    return path


class TestUpstreamContentWins:
    """Read and list return origin/main, whatever the checkout's state."""

    async def test_feature_branch(
        self, make_clone: MakeClone, make_tools: MakeTools
    ) -> None:
        _upstream(make_clone, {"data.txt": b"upstream\n"})
        work = make_clone("work")
        _git(work, "checkout", "-q", "-b", "feature")
        _commit(work, {"data.txt": b"feature\n", "feature.txt": b"f\n"})
        tools = _tools(make_tools, work)

        assert await _read(tools, "data.txt") == "upstream\n"
        listing = await _list(tools)
        assert "data.txt" in listing
        assert "feature.txt" not in listing
        assert not any(entry.startswith("[reference") for entry in listing)

    async def test_dirty_working_tree(
        self, make_clone: MakeClone, make_tools: MakeTools
    ) -> None:
        _upstream(make_clone, {"data.txt": b"upstream\n"})
        work = make_clone("work")
        (work / "data.txt").write_bytes(b"dirty\n")
        (work / "untracked.txt").write_bytes(b"untracked\n")
        tools = _tools(make_tools, work)

        assert await _read(tools, "data.txt") == "upstream\n"
        listing = await _list(tools)
        assert sorted(listing) == ["README.md", "data.txt"]

    async def test_behind_origin_after_manual_fetch(
        self, make_clone: MakeClone, make_tools: MakeTools
    ) -> None:
        work = make_clone("work")
        _upstream(make_clone, {"data.txt": b"newer\n"})
        _git(work, "fetch", "-q", "origin")
        tools = _tools(make_tools, work)

        assert await _read(tools, "data.txt") == "newer\n"
        assert sorted(await _list(tools)) == ["README.md", "data.txt"]
        assert not (work / "data.txt").exists()

    async def test_behind_origin_auto_fetches(
        self, make_clone: MakeClone, make_tools: MakeTools
    ) -> None:
        """With interval 15 and no manual fetch, the first read fetches."""
        work = make_clone("work")
        _upstream(make_clone, {"data.txt": b"newer\n"})
        tools = _tools(make_tools, work, interval=15)

        assert await _read(tools, "data.txt") == "newer\n"

    async def test_dangling_origin_head_reads_origin_main(
        self, make_clone: MakeClone, make_tools: MakeTools
    ) -> None:
        _upstream(make_clone, {"data.txt": b"upstream\n"})
        work = make_clone("work")
        _git(
            work,
            "symbolic-ref",
            "refs/remotes/origin/HEAD",
            "refs/remotes/origin/gone",
        )
        tools = _tools(make_tools, work)

        assert await _read(tools, "data.txt") == "upstream\n"


class TestLineEndings:
    """Reads at the ref render exactly as read_file renders the same bytes."""

    @pytest.mark.parametrize(
        "data",
        [b"a\r\nb\r\nc\r\nd\r\n", b"a\rb\rc\rd\r", b"a\r\nb\rc\nd"],
        ids=["crlf", "lone-cr", "mixed"],
    )
    async def test_same_rendering_as_read_file(
        self,
        tmp_path: Path,
        make_clone: MakeClone,
        make_tools: MakeTools,
        data: bytes,
    ) -> None:
        _upstream(make_clone, {"eol.txt": data})
        work = make_clone("work")
        local = tmp_path / "local"
        local.mkdir()
        (local / "eol.txt").write_bytes(data)
        tools = _tools(make_tools, work, read_max_lines=2)

        cases: list[tuple[int | None, int | None, bool | None]] = [
            (None, None, None),
            (2, 3, None),
            (2, 3, False),
        ]
        for start, end, numbers in cases:
            expected = read_file_util(
                "eol.txt",
                project_dir=local,
                start_line=start,
                end_line=end,
                with_line_numbers=numbers,
                max_lines=2,
            )
            actual = await _read(
                tools,
                "eol.txt",
                start_line=start,
                end_line=end,
                with_line_numbers=numbers,
            )
            assert actual == expected, (start, end, numbers)


class TestLocalFallback:
    """Folders that cannot be read at a ref are read locally."""

    @pytest.mark.parametrize(
        "build",
        [_plain_folder, _broken_git, _nested_in_checkout],
        ids=lambda build: build.__name__.lstrip("_"),
    )
    async def test_local_content_without_note(
        self, tmp_path: Path, make_tools: MakeTools, build: Callable[[Path], Path]
    ) -> None:
        tools = _tools(make_tools, build(tmp_path))

        assert await _read(tools, "file.txt") == "x\n"
        assert await _list(tools) == ["file.txt"]

    async def test_repo_without_origin_adds_fallback_note(
        self, tmp_path: Path, make_tools: MakeTools
    ) -> None:
        path = _init_repo(tmp_path / "repo")
        (path / "untracked.txt").write_text("u\n", encoding="utf-8")
        tools = _tools(make_tools, path)

        assert await _read(tools, "untracked.txt") == f"u\n{_FALLBACK}"
        listing = await _list(tools)
        assert listing[-1] == _FALLBACK
        assert sorted(listing[:-1]) == ["local.txt", "untracked.txt"]

    async def test_fallback_note_follows_warning_line(
        self, tmp_path: Path, make_tools: MakeTools
    ) -> None:
        path = _init_repo(tmp_path / "repo")
        (path / ".mcp-file-access").write_text("readonly /x\n", encoding="utf-8")
        tools = _tools(make_tools, path)

        listing = await _list(tools)
        assert listing[0].startswith("WARNING")
        assert listing[-1] == _FALLBACK
        assert "local.txt" in listing

    async def test_fallback_note_on_error(
        self, tmp_path: Path, make_tools: MakeTools
    ) -> None:
        tools = _tools(make_tools, _init_repo(tmp_path / "repo"))

        with pytest.raises(FileNotFoundError) as info:
            await _read(tools, "nope.txt")
        assert str(info.value) == f"File 'nope.txt' does not exist\n{_FALLBACK}"

    @pytest.mark.parametrize(
        "build",
        [_plain_folder, _broken_git, _nested_in_checkout, _repo_without_origin],
        ids=lambda build: build.__name__.lstrip("_"),
    )
    async def test_no_fetch_subprocess(
        self, tmp_path: Path, make_tools: MakeTools, build: Callable[[Path], Path]
    ) -> None:
        tools = _tools(make_tools, build(tmp_path), interval=15)

        with patch(_RUN_GIT_TARGET) as run_git:
            assert (await _read(tools, "file.txt")).startswith("x\n")
            assert "file.txt" in await _list(tools)
        run_git.assert_not_called()

    async def test_corrupt_default_ref_is_an_error(
        self, origin_clone: Path, make_tools: MakeTools
    ) -> None:
        ref_file = origin_clone / ".git" / "refs" / "remotes" / "origin" / "main"
        ref_file.parent.mkdir(parents=True, exist_ok=True)
        ref_file.write_text("1234567890" * 4 + "\n")
        tools = _tools(make_tools, origin_clone)

        with pytest.raises(ValueError, match="reference 'ref'"):
            await _read(tools, "README.md")
        with pytest.raises(ValueError, match="reference 'ref'"):
            await _list(tools)


@pytest.fixture
def ref_work(make_clone: MakeClone) -> Path:
    """Work clone whose origin/main holds a known tree, a symlink and a gitlink."""
    up = make_clone("up")
    _commit(
        up,
        {
            ".gitignore": b"secret.txt\n",
            "CLAUDE.md": b"# Claude\n",
            "secret.txt": b"tracked but ignored\n",
            "src/a.py": b"print('a')\n",
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


class TestReadsAtRef:
    """Errors, paths and tracked-only content at the ref."""

    async def test_not_found_names_path_ref_and_sha(
        self, ref_work: Path, make_tools: MakeTools
    ) -> None:
        tools = _tools(make_tools, ref_work)
        with pytest.raises(FileNotFoundError) as info:
            await _read(tools, "nope.txt")
        assert str(info.value) == (
            f"File 'nope.txt' is not in {_short_main(ref_work)} of reference 'ref'."
        )

    async def test_case_mismatch_names_correct_spelling(
        self, ref_work: Path, make_tools: MakeTools
    ) -> None:
        tools = _tools(make_tools, ref_work)
        with pytest.raises(FileNotFoundError, match="did you mean 'CLAUDE.md'"):
            await _read(tools, "claude.md")

    async def test_directory_is_not_a_file(
        self, ref_work: Path, make_tools: MakeTools
    ) -> None:
        tools = _tools(make_tools, ref_work)
        with pytest.raises(IsADirectoryError) as info:
            await _read(tools, "src")
        assert str(info.value) == "Path 'src' is not a file"

    async def test_symlink_and_gitlink(
        self, ref_work: Path, make_tools: MakeTools
    ) -> None:
        tools = _tools(make_tools, ref_work)
        listing = await _list(tools)
        assert "link" not in listing
        assert "sub" not in listing
        for path in ("link", "sub"):
            with pytest.raises(FileNotFoundError):
                await _read(tools, path)

    async def test_path_spellings_accepted(
        self, ref_work: Path, make_tools: MakeTools
    ) -> None:
        tools = _tools(make_tools, ref_work)
        for path in (str(ref_work / "src" / "a.py"), "src\\a.py", "./src/a.py"):
            assert await _read(tools, path) == "print('a')\n", path

    async def test_traversal_refused(
        self, ref_work: Path, make_tools: MakeTools
    ) -> None:
        tools = _tools(make_tools, ref_work)
        with pytest.raises(ValueError, match="traversal"):
            await _read(tools, "src/../z.txt")

    async def test_absolute_outside_refused(
        self, tmp_path: Path, ref_work: Path, make_tools: MakeTools
    ) -> None:
        (tmp_path / "outside.txt").write_text("OUTSIDE\n", encoding="utf-8")
        tools = _tools(make_tools, ref_work)
        with pytest.raises(ValueError, match="outside the project directory") as info:
            await _read(tools, str(tmp_path / "outside.txt"))
        assert "OUTSIDE" not in str(info.value)

    @pytest.mark.parametrize("path", [".git/config", ".GIT/config", ".git./config"])
    async def test_git_dir_refused(
        self, ref_work: Path, make_tools: MakeTools, path: str
    ) -> None:
        tools = _tools(make_tools, ref_work)
        with pytest.raises(ValueError, match="Security error") as info:
            await _read(tools, path)
        assert "repositoryformatversion" not in str(info.value)

    async def test_tracked_ignored_file_is_readable_and_listed(
        self, ref_work: Path, make_tools: MakeTools
    ) -> None:
        tools = _tools(make_tools, ref_work)
        assert await _read(tools, "secret.txt") == "tracked but ignored\n"
        assert "secret.txt" in await _list(tools)

    async def test_untracked_local_file_is_absent(
        self, ref_work: Path, make_tools: MakeTools
    ) -> None:
        (ref_work / "local_only.txt").write_text("local\n", encoding="utf-8")
        tools = _tools(make_tools, ref_work)
        assert "local_only.txt" not in await _list(tools)
        with pytest.raises(FileNotFoundError):
            await _read(tools, "local_only.txt")

    async def test_list_matches_ls_tree(
        self, ref_work: Path, make_tools: MakeTools
    ) -> None:
        tools = _tools(make_tools, ref_work)
        names = _git(
            ref_work, "ls-tree", "-r", "--name-only", "refs/remotes/origin/main"
        ).splitlines()
        assert await _list(tools) == [n for n in names if n not in {"link", "sub"}]


_SYMBOLS = "UPSTREAM_SYMBOL|LOCAL_SYMBOL"


class TestSearchUpstreamContentWins:
    """Search returns origin/main, whatever the checkout's state."""

    async def test_feature_branch(
        self, make_clone: MakeClone, make_tools: MakeTools
    ) -> None:
        _upstream(make_clone, {"up.py": b"UPSTREAM_SYMBOL\n"})
        work = make_clone("work")
        _git(work, "checkout", "-q", "-b", "feature")
        _commit(work, {"up.py": b"LOCAL_SYMBOL\n", "feat.py": b"LOCAL_SYMBOL\n"})
        tools = _tools(make_tools, work)

        result = await _search(tools, pattern=_SYMBOLS)
        assert result["details"] == [
            {"file": "up.py", "line": 1, "text": "UPSTREAM_SYMBOL"}
        ]
        assert "freshness" not in result

    async def test_dirty_working_tree(
        self, make_clone: MakeClone, make_tools: MakeTools
    ) -> None:
        _upstream(make_clone, {"up.py": b"UPSTREAM_SYMBOL\n"})
        work = make_clone("work")
        (work / "up.py").write_bytes(b"LOCAL_SYMBOL\n")
        (work / "untracked.py").write_bytes(b"LOCAL_SYMBOL\n")
        tools = _tools(make_tools, work)

        result = await _search(tools, pattern=_SYMBOLS)
        assert _hit_files(result) == ["up.py"]
        assert result["details"][0]["text"] == "UPSTREAM_SYMBOL"
        assert "freshness" not in result

    async def test_behind_origin(
        self, make_clone: MakeClone, make_tools: MakeTools
    ) -> None:
        work = make_clone("work")
        _upstream(make_clone, {"up.py": b"UPSTREAM_SYMBOL\n"})
        _git(work, "fetch", "-q", "origin")
        tools = _tools(make_tools, work)

        result = await _search(tools, pattern=_SYMBOLS)
        assert _hit_files(result) == ["up.py"]
        assert (await _search(tools, glob="*.py"))["files"] == ["up.py"]
        assert not (work / "up.py").exists()
        assert "freshness" not in result


@pytest.fixture
def hits_work(make_clone: MakeClone) -> Path:
    """Work clone whose origin/main holds several files containing ``hit``."""
    _upstream(
        make_clone,
        {
            "c.txt": b"hit c\n",
            "a/x.txt": b"hit x\n",
            "b.txt": b"hit b\n",
            "ctx.txt": b"one\ntwo\nthree\nfour\n",
            "src/Mod.py": b"print('mod')\n",
        },
    )
    return make_clone("work")


class TestSearchSemanticsAtRef:
    """Search at the ref behaves as the working-tree search does."""

    async def test_glob_case(self, hits_work: Path, make_tools: MakeTools) -> None:
        tools = _tools(make_tools, hits_work)

        assert (await _search(tools, glob="*.py"))["files"] == ["src/Mod.py"]
        expected = ["src/Mod.py"] if sys.platform == "win32" else []
        assert (await _search(tools, glob="SRC/mod.PY"))["files"] == expected

    async def test_glob_note(self, hits_work: Path, make_tools: MakeTools) -> None:
        tools = _tools(make_tools, hits_work)

        result = await _search(tools, glob="{a,b}.txt")
        assert result["files"] == []
        assert "Brace expansion is not supported" in result["glob_note"]

    async def test_glob_matching_nothing_by_construction(
        self, hits_work: Path, make_tools: MakeTools
    ) -> None:
        tools = _tools(make_tools, hits_work)

        with pytest.raises(ValueError, match="matches nothing by construction"):
            await _search(tools, glob="!x")

    async def test_regex_and_context_lines(
        self, hits_work: Path, make_tools: MakeTools
    ) -> None:
        tools = _tools(make_tools, hits_work)

        result = await _search(tools, pattern="^t.o$", context_lines=1)
        assert result["details"] == [
            {"file": "ctx.txt", "line": 2, "text": "one\ntwo\nthree"}
        ]

    async def test_combined_glob_and_pattern(
        self, hits_work: Path, make_tools: MakeTools
    ) -> None:
        tools = _tools(make_tools, hits_work)

        result = await _search(tools, glob="a/*", pattern="hit")
        assert _hit_files(result) == ["a/x.txt"]

    async def test_content_truncation_in_ls_tree_order(
        self, hits_work: Path, make_tools: MakeTools
    ) -> None:
        tools = _tools(make_tools, hits_work)
        order = [f for f in _ls_tree(hits_work) if f in {"a/x.txt", "b.txt", "c.txt"}]

        result = await _search(tools, pattern="hit", max_results=2)
        assert _hit_files(result) == order[:2]
        assert result["truncated"] is True
        assert result["total_matches"] == 3
        assert [m["file"] for m in result["matched_files"]] == order

    async def test_file_search_truncation_in_ls_tree_order(
        self, hits_work: Path, make_tools: MakeTools
    ) -> None:
        tools = _tools(make_tools, hits_work)
        order = [f for f in _ls_tree(hits_work) if f.endswith(".txt")]

        result = await _search(tools, glob="*.txt", max_results=2)
        assert result["files"] == order[:2]
        assert result["total_files"] == len(order)
        assert result["truncated"] is True


class TestSearchSkippedFilesAtRef:
    """Unreadable blobs are reported; binary blobs are skipped silently."""

    async def test_unreadable_blob_in_skipped_files(
        self, hits_work: Path, make_tools: MakeTools
    ) -> None:
        tools = _tools(make_tools, hits_work)
        original = RefSnapshot.read_bytes

        def failing(
            self: RefSnapshot, path: str, display_path: str | None = None
        ) -> bytes:
            if path == "b.txt":
                raise ValueError("cannot read")
            return original(self, path, display_path)

        with patch.object(RefSnapshot, "read_bytes", failing):
            result = await _search(tools, pattern="hit")
        assert result["skipped_files"] == ["b.txt"]
        assert sorted(_hit_files(result)) == ["a/x.txt", "c.txt"]

    async def test_binary_blob_skipped_silently(
        self, make_clone: MakeClone, make_tools: MakeTools
    ) -> None:
        _upstream(make_clone, {"bin.dat": b"\xff\xfehit\n", "text.txt": b"hit\n"})
        tools = _tools(make_tools, make_clone("work"))

        result = await _search(tools, pattern="hit")
        assert _hit_files(result) == ["text.txt"]
        assert "skipped_files" not in result

    async def test_missing_blob_object_in_skipped_files(
        self, make_clone: MakeClone, make_tools: MakeTools
    ) -> None:
        work = make_clone("work")
        _upstream(make_clone, {"gone.txt": b"gone\n", "kept.txt": b"kept\n"})
        _git(work, "config", "fetch.unpackLimit", "100000")
        _git(work, "config", "transfer.unpackLimit", "100000")
        _git(work, "fetch", "-q", "origin")
        blob = _git(work, "rev-parse", "refs/remotes/origin/main:gone.txt")
        loose = work / ".git" / "objects" / blob[:2] / blob[2:]
        if not loose.exists():
            pytest.skip("blob object stayed packed")
        os.chmod(loose, stat.S_IREAD | stat.S_IWRITE)
        loose.unlink()
        tools = _tools(make_tools, work)

        result = await _search(tools, pattern=".")
        assert result["skipped_files"] == ["gone.txt"]
        assert sorted(_hit_files(result)) == ["README.md", "kept.txt"]


class TestSearchAtRefTree:
    """Line numbers, link entries and tracked-only content at the ref."""

    @pytest.mark.parametrize(
        "data",
        [b"a\r\nb\r\nc\r\nd\r\n", b"a\rb\rc\rd\r", b"a\r\nb\rc\nd"],
        ids=["crlf", "lone-cr", "mixed"],
    )
    async def test_line_numbers_match_read(
        self, make_clone: MakeClone, make_tools: MakeTools, data: bytes
    ) -> None:
        _upstream(make_clone, {"eol.txt": data})
        tools = _tools(make_tools, make_clone("work"))

        for letter in "abcd":
            result = await _search(tools, glob="eol.txt", pattern=f"^{letter}$")
            [match] = result["details"]
            line = match["line"]
            read = await _read(
                tools,
                "eol.txt",
                start_line=line,
                end_line=line,
                with_line_numbers=False,
            )
            assert read.rstrip("\n") == letter, (letter, line)

    async def test_symlink_and_gitlink_absent(
        self, ref_work: Path, make_tools: MakeTools
    ) -> None:
        tools = _tools(make_tools, ref_work)

        files = (await _search(tools, glob="**/*"))["files"]
        assert "link" not in files
        assert "sub" not in files
        assert _hit_files(await _search(tools, pattern="^z$")) == ["z.txt"]

    async def test_tracked_ignored_file_found(
        self, ref_work: Path, make_tools: MakeTools
    ) -> None:
        tools = _tools(make_tools, ref_work)

        result = await _search(tools, pattern="tracked but ignored")
        assert _hit_files(result) == ["secret.txt"]

    async def test_untracked_local_file_absent(
        self, ref_work: Path, make_tools: MakeTools
    ) -> None:
        (ref_work / "local_only.txt").write_text("LOCAL_ONLY\n", encoding="utf-8")
        tools = _tools(make_tools, ref_work)

        assert (await _search(tools, pattern="LOCAL_ONLY"))["details"] == []
        assert (await _search(tools, glob="local_only.txt"))["files"] == []


class TestSearchLocalFallback:
    """Folders that cannot be searched at a ref are searched locally."""

    async def test_repo_without_origin_adds_fallback_note(
        self, tmp_path: Path, make_tools: MakeTools
    ) -> None:
        path = _init_repo(tmp_path / "repo")
        (path / "untracked.txt").write_text("u\n", encoding="utf-8")
        tools = _tools(make_tools, path)

        result = await _search(tools, glob="*.txt")
        assert sorted(result["files"]) == ["local.txt", "untracked.txt"]
        assert result["freshness"] == _FALLBACK

    async def test_plain_folder_has_no_freshness(
        self, tmp_path: Path, make_tools: MakeTools
    ) -> None:
        tools = _tools(make_tools, _plain_folder(tmp_path))

        result = await _search(tools, glob="*.txt")
        assert result == {
            "mode": "file_search",
            "files": ["file.txt"],
            "total_files": 1,
            "truncated": False,
        }


@patch(_FETCH_TARGET, new=MagicMock(return_value=FetchOutcome(True, "boom")))
class TestFetchFailureNotes:
    """A failed fetch reads the last-fetched state and says so."""

    async def test_read_uses_last_fetched_state(
        self, make_clone: MakeClone, make_tools: MakeTools
    ) -> None:
        work = make_clone("work")
        _upstream(make_clone, {"README.md": b"# Newer\n"})
        tools = _tools(make_tools, work, interval=15)

        note = f"[reference ref: fetch failed (boom) — read {_short_main(work)}]"
        assert await _read(tools, "README.md") == f"# Test Project\n{note}"
        assert (await _list(tools))[-1] == note

    async def test_newline_added_before_note(
        self, make_clone: MakeClone, make_tools: MakeTools
    ) -> None:
        _upstream(make_clone, {"bare.txt": b"no newline"})
        work = make_clone("work")
        tools = _tools(make_tools, work, interval=15)

        note = f"[reference ref: fetch failed (boom) — read {_short_main(work)}]"
        assert await _read(tools, "bare.txt") == f"no newline\n{note}"

    async def test_note_after_truncation_note(
        self, make_clone: MakeClone, make_tools: MakeTools
    ) -> None:
        _upstream(make_clone, {"three.txt": b"l1\nl2\nl3\n"})
        work = make_clone("work")
        tools = _tools(make_tools, work, interval=15, read_max_lines=1)

        note = f"[reference ref: fetch failed (boom) — read {_short_main(work)}]"
        assert await _read(tools, "three.txt") == (
            "l1\n"
            "[truncated: showing lines 1–1 of 3; continue with start_line=2, "
            f"end_line=2]\n{note}"
        )

    async def test_not_found_carries_note(
        self, origin_clone: Path, make_tools: MakeTools
    ) -> None:
        tools = _tools(make_tools, origin_clone, interval=15)
        where = _short_main(origin_clone)

        with pytest.raises(FileNotFoundError) as info:
            await _read(tools, "nope.txt")
        assert str(info.value) == (
            f"File 'nope.txt' is not in {where} of reference 'ref'.\n"
            f"[reference ref: fetch failed (boom) — read {where}]"
        )
        assert info.value.__context__ is None

    async def test_no_default_ref_gets_both_notes(
        self, tmp_path: Path, make_tools: MakeTools
    ) -> None:
        path = _init_repo(tmp_path / "repo")
        _git(path, "remote", "add", "origin", "https://example.invalid/x.git")
        tools = _tools(make_tools, path, interval=15)
        notes = f"[reference ref: fetch failed (boom)]\n{_FALLBACK}"

        assert await _read(tools, "local.txt") == f"local\n{notes}"
        assert (await _list(tools))[-1] == notes
        with pytest.raises(FileNotFoundError) as info:
            await _read(tools, "nope.txt")
        assert str(info.value) == f"File 'nope.txt' does not exist\n{notes}"

    async def test_search_carries_fetch_failure_note(
        self, origin_clone: Path, make_tools: MakeTools
    ) -> None:
        tools = _tools(make_tools, origin_clone, interval=15)
        note = (
            f"[reference ref: fetch failed (boom) — read {_short_main(origin_clone)}]"
        )

        result = await _search(tools, glob="*.md")
        assert result["files"] == ["README.md"]
        assert result["freshness"] == note

    async def test_search_no_default_ref_gets_both_notes(
        self, tmp_path: Path, make_tools: MakeTools
    ) -> None:
        path = _init_repo(tmp_path / "repo")
        _git(path, "remote", "add", "origin", "https://example.invalid/x.git")
        tools = _tools(make_tools, path, interval=15)

        result = await _search(tools, pattern="local")
        assert _hit_files(result) == ["local.txt"]
        assert result["freshness"] == (
            f"[reference ref: fetch failed (boom)]\n{_FALLBACK}"
        )


async def test_get_reference_projects_unchanged(
    origin_clone: Path, make_tools: MakeTools
) -> None:
    tools = make_tools(
        reference_projects={
            "ref": ReferenceProject(
                name="ref", path=origin_clone, url="https://github.com/o/ref"
            )
        }
    )
    assert tools["get_reference_projects"]() == {
        "count": 1,
        "projects": [{"name": "ref", "url": "https://github.com/o/ref"}],
        "usage": (
            "Pass a name as reference_name to the reference file tools, git(), "
            "and the GitHub read tools; issues can also be created, edited and "
            "commented on"
        ),
    }
