"""The reference file tools read and list at origin/<default>."""

from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_workspace.file_tools import read_file as read_file_util
from mcp_workspace.reference_projects import ReferenceProject
from tests._reference_at_ref_helpers import (
    FALLBACK_NOTE,
    MakeClone,
    MakeTools,
    broken_git,
    commit_files,
    git_cmd,
    init_repo,
    list_ref,
    make_ref_work,
    nested_in_checkout,
    plain_folder,
    push_upstream,
    read_ref,
    ref_tools,
    repo_without_origin,
    short_main,
)

pytestmark = [pytest.mark.git_integration, pytest.mark.asyncio]

_RUN_GIT_TARGET = "mcp_workspace.git_operations.origin_fetch.run_git_timed"


class TestUpstreamContentWins:
    """Read and list return origin/main, whatever the checkout's state."""

    async def test_feature_branch(
        self, make_clone: MakeClone, make_tools: MakeTools
    ) -> None:
        push_upstream(make_clone, {"data.txt": b"upstream\n"})
        work = make_clone("work")
        git_cmd(work, "checkout", "-q", "-b", "feature")
        commit_files(work, {"data.txt": b"feature\n", "feature.txt": b"f\n"})
        tools = ref_tools(make_tools, work)

        assert await read_ref(tools, "data.txt") == "upstream\n"
        listing = await list_ref(tools)
        assert "data.txt" in listing
        assert "feature.txt" not in listing
        assert not any(entry.startswith("[reference") for entry in listing)

    async def test_dirty_working_tree(
        self, make_clone: MakeClone, make_tools: MakeTools
    ) -> None:
        push_upstream(make_clone, {"data.txt": b"upstream\n"})
        work = make_clone("work")
        (work / "data.txt").write_bytes(b"dirty\n")
        (work / "untracked.txt").write_bytes(b"untracked\n")
        tools = ref_tools(make_tools, work)

        assert await read_ref(tools, "data.txt") == "upstream\n"
        listing = await list_ref(tools)
        assert sorted(listing) == ["README.md", "data.txt"]

    async def test_behind_origin_after_manual_fetch(
        self, make_clone: MakeClone, make_tools: MakeTools
    ) -> None:
        work = make_clone("work")
        push_upstream(make_clone, {"data.txt": b"newer\n"})
        git_cmd(work, "fetch", "-q", "origin")
        tools = ref_tools(make_tools, work)

        assert await read_ref(tools, "data.txt") == "newer\n"
        assert sorted(await list_ref(tools)) == ["README.md", "data.txt"]
        assert not (work / "data.txt").exists()

    async def test_behind_origin_auto_fetches(
        self, make_clone: MakeClone, make_tools: MakeTools
    ) -> None:
        """With interval 15 and no manual fetch, the first read fetches."""
        work = make_clone("work")
        push_upstream(make_clone, {"data.txt": b"newer\n"})
        tools = ref_tools(make_tools, work, interval=15)

        assert await read_ref(tools, "data.txt") == "newer\n"

    async def test_dangling_origin_head_reads_origin_main(
        self, make_clone: MakeClone, make_tools: MakeTools
    ) -> None:
        push_upstream(make_clone, {"data.txt": b"upstream\n"})
        work = make_clone("work")
        git_cmd(
            work,
            "symbolic-ref",
            "refs/remotes/origin/HEAD",
            "refs/remotes/origin/gone",
        )
        tools = ref_tools(make_tools, work)

        assert await read_ref(tools, "data.txt") == "upstream\n"


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
        push_upstream(make_clone, {"eol.txt": data})
        work = make_clone("work")
        local = tmp_path / "local"
        local.mkdir()
        (local / "eol.txt").write_bytes(data)
        tools = ref_tools(make_tools, work, read_max_lines=2)

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
            actual = await read_ref(
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
        [plain_folder, broken_git, nested_in_checkout],
        ids=lambda build: build.__name__,
    )
    async def test_local_content_without_note(
        self, tmp_path: Path, make_tools: MakeTools, build: Callable[[Path], Path]
    ) -> None:
        tools = ref_tools(make_tools, build(tmp_path))

        assert await read_ref(tools, "file.txt") == "x\n"
        assert await list_ref(tools) == ["file.txt"]

    async def test_repo_without_origin_adds_fallback_note(
        self, tmp_path: Path, make_tools: MakeTools
    ) -> None:
        path = init_repo(tmp_path / "repo")
        (path / "untracked.txt").write_text("u\n", encoding="utf-8")
        tools = ref_tools(make_tools, path)

        assert await read_ref(tools, "untracked.txt") == f"u\n{FALLBACK_NOTE}"
        listing = await list_ref(tools)
        assert listing[-1] == FALLBACK_NOTE
        assert sorted(listing[:-1]) == ["local.txt", "untracked.txt"]

    async def test_fallback_note_follows_warning_line(
        self, tmp_path: Path, make_tools: MakeTools
    ) -> None:
        path = init_repo(tmp_path / "repo")
        (path / ".mcp-file-access").write_text("readonly /x\n", encoding="utf-8")
        tools = ref_tools(make_tools, path)

        listing = await list_ref(tools)
        assert listing[0].startswith("WARNING")
        assert listing[-1] == FALLBACK_NOTE
        assert "local.txt" in listing

    async def test_fallback_note_on_error(
        self, tmp_path: Path, make_tools: MakeTools
    ) -> None:
        tools = ref_tools(make_tools, init_repo(tmp_path / "repo"))

        with pytest.raises(FileNotFoundError) as info:
            await read_ref(tools, "nope.txt")
        assert str(info.value) == f"File 'nope.txt' does not exist\n{FALLBACK_NOTE}"

    @pytest.mark.parametrize(
        "build",
        [plain_folder, broken_git, nested_in_checkout, repo_without_origin],
        ids=lambda build: build.__name__,
    )
    async def test_no_fetch_subprocess(
        self, tmp_path: Path, make_tools: MakeTools, build: Callable[[Path], Path]
    ) -> None:
        tools = ref_tools(make_tools, build(tmp_path), interval=15)

        with patch(_RUN_GIT_TARGET) as run_git:
            assert (await read_ref(tools, "file.txt")).startswith("x\n")
            assert "file.txt" in await list_ref(tools)
        run_git.assert_not_called()

    async def test_corrupt_default_ref_is_an_error(
        self, origin_clone: Path, make_tools: MakeTools
    ) -> None:
        ref_file = origin_clone / ".git" / "refs" / "remotes" / "origin" / "main"
        ref_file.parent.mkdir(parents=True, exist_ok=True)
        ref_file.write_text("1234567890" * 4 + "\n")
        tools = ref_tools(make_tools, origin_clone)

        with pytest.raises(ValueError, match="reference 'ref'"):
            await read_ref(tools, "README.md")
        with pytest.raises(ValueError, match="reference 'ref'"):
            await list_ref(tools)


@pytest.fixture
def ref_work(make_clone: MakeClone) -> Path:
    """Work clone whose origin/main holds a known tree, a symlink and a gitlink."""
    return make_ref_work(make_clone)


class TestReadsAtRef:
    """Errors, paths and tracked-only content at the ref."""

    async def test_not_found_names_path_ref_and_sha(
        self, ref_work: Path, make_tools: MakeTools
    ) -> None:
        tools = ref_tools(make_tools, ref_work)
        with pytest.raises(FileNotFoundError) as info:
            await read_ref(tools, "nope.txt")
        assert str(info.value) == (
            f"File 'nope.txt' is not in {short_main(ref_work)} of reference 'ref'."
        )

    async def test_case_mismatch_names_correct_spelling(
        self, ref_work: Path, make_tools: MakeTools
    ) -> None:
        tools = ref_tools(make_tools, ref_work)
        with pytest.raises(FileNotFoundError, match="did you mean 'CLAUDE.md'"):
            await read_ref(tools, "claude.md")

    async def test_directory_is_not_a_file(
        self, ref_work: Path, make_tools: MakeTools
    ) -> None:
        tools = ref_tools(make_tools, ref_work)
        with pytest.raises(IsADirectoryError) as info:
            await read_ref(tools, "src")
        assert str(info.value) == "Path 'src' is not a file"

    async def test_symlink_and_gitlink(
        self, ref_work: Path, make_tools: MakeTools
    ) -> None:
        tools = ref_tools(make_tools, ref_work)
        listing = await list_ref(tools)
        assert "link" not in listing
        assert "sub" not in listing
        for path in ("link", "sub"):
            with pytest.raises(FileNotFoundError):
                await read_ref(tools, path)

    async def test_path_spellings_accepted(
        self, ref_work: Path, make_tools: MakeTools
    ) -> None:
        tools = ref_tools(make_tools, ref_work)
        for path in (str(ref_work / "src" / "a.py"), "src\\a.py", "./src/a.py"):
            assert await read_ref(tools, path) == "print('a')\n", path

    async def test_traversal_refused(
        self, ref_work: Path, make_tools: MakeTools
    ) -> None:
        tools = ref_tools(make_tools, ref_work)
        with pytest.raises(ValueError, match="traversal"):
            await read_ref(tools, "src/../z.txt")

    async def test_absolute_outside_refused(
        self, tmp_path: Path, ref_work: Path, make_tools: MakeTools
    ) -> None:
        (tmp_path / "outside.txt").write_text("OUTSIDE\n", encoding="utf-8")
        tools = ref_tools(make_tools, ref_work)
        with pytest.raises(ValueError, match="outside the project directory") as info:
            await read_ref(tools, str(tmp_path / "outside.txt"))
        assert "OUTSIDE" not in str(info.value)

    @pytest.mark.parametrize("path", [".git/config", ".GIT/config", ".git./config"])
    async def test_git_dir_refused(
        self, ref_work: Path, make_tools: MakeTools, path: str
    ) -> None:
        tools = ref_tools(make_tools, ref_work)
        with pytest.raises(ValueError, match="Security error") as info:
            await read_ref(tools, path)
        assert "repositoryformatversion" not in str(info.value)

    async def test_tracked_ignored_file_is_readable_and_listed(
        self, ref_work: Path, make_tools: MakeTools
    ) -> None:
        tools = ref_tools(make_tools, ref_work)
        assert await read_ref(tools, "secret.txt") == "tracked but ignored\n"
        assert "secret.txt" in await list_ref(tools)

    async def test_untracked_local_file_is_absent(
        self, ref_work: Path, make_tools: MakeTools
    ) -> None:
        (ref_work / "local_only.txt").write_text("local\n", encoding="utf-8")
        tools = ref_tools(make_tools, ref_work)
        assert "local_only.txt" not in await list_ref(tools)
        with pytest.raises(FileNotFoundError):
            await read_ref(tools, "local_only.txt")

    async def test_list_matches_ls_tree(
        self, ref_work: Path, make_tools: MakeTools
    ) -> None:
        tools = ref_tools(make_tools, ref_work)
        names = git_cmd(
            ref_work, "ls-tree", "-r", "--name-only", "refs/remotes/origin/main"
        ).splitlines()
        assert await list_ref(tools) == [n for n in names if n not in {"link", "sub"}]


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
