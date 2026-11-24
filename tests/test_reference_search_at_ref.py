"""The reference search tool searches at origin/<default>; fetch-failure notes."""

import os
import stat
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mcp_workspace.git_operations.origin_fetch import FetchOutcome
from mcp_workspace.git_operations.ref_snapshot import RefSnapshot
from tests._reference_at_ref_helpers import (
    FALLBACK_NOTE,
    MakeClone,
    MakeTools,
    commit_files,
    git_cmd,
    hit_files,
    init_repo,
    list_ref,
    ls_tree,
    make_ref_work,
    plain_folder,
    push_upstream,
    read_ref,
    ref_tools,
    search_ref,
    short_main,
)

pytestmark = [pytest.mark.git_integration, pytest.mark.asyncio]

_FETCH_TARGET = "mcp_workspace.git_operations.origin_fetch.fetch_origin"
_SYMBOLS = "UPSTREAM_SYMBOL|LOCAL_SYMBOL"


@pytest.fixture
def ref_work(make_clone: MakeClone) -> Path:
    """Work clone whose origin/main holds a known tree, a symlink and a gitlink."""
    return make_ref_work(make_clone)


class TestSearchUpstreamContentWins:
    """Search returns origin/main, whatever the checkout's state."""

    async def test_feature_branch(
        self, make_clone: MakeClone, make_tools: MakeTools
    ) -> None:
        push_upstream(make_clone, {"up.py": b"UPSTREAM_SYMBOL\n"})
        work = make_clone("work")
        git_cmd(work, "checkout", "-q", "-b", "feature")
        commit_files(work, {"up.py": b"LOCAL_SYMBOL\n", "feat.py": b"LOCAL_SYMBOL\n"})
        tools = ref_tools(make_tools, work)

        result = await search_ref(tools, pattern=_SYMBOLS)
        assert result["details"] == [
            {"file": "up.py", "line": 1, "text": "UPSTREAM_SYMBOL"}
        ]
        assert "freshness" not in result

    async def test_dirty_working_tree(
        self, make_clone: MakeClone, make_tools: MakeTools
    ) -> None:
        push_upstream(make_clone, {"up.py": b"UPSTREAM_SYMBOL\n"})
        work = make_clone("work")
        (work / "up.py").write_bytes(b"LOCAL_SYMBOL\n")
        (work / "untracked.py").write_bytes(b"LOCAL_SYMBOL\n")
        tools = ref_tools(make_tools, work)

        result = await search_ref(tools, pattern=_SYMBOLS)
        assert hit_files(result) == ["up.py"]
        assert result["details"][0]["text"] == "UPSTREAM_SYMBOL"
        assert "freshness" not in result

    async def test_behind_origin(
        self, make_clone: MakeClone, make_tools: MakeTools
    ) -> None:
        work = make_clone("work")
        push_upstream(make_clone, {"up.py": b"UPSTREAM_SYMBOL\n"})
        git_cmd(work, "fetch", "-q", "origin")
        tools = ref_tools(make_tools, work)

        result = await search_ref(tools, pattern=_SYMBOLS)
        assert hit_files(result) == ["up.py"]
        assert (await search_ref(tools, glob="*.py"))["files"] == ["up.py"]
        assert not (work / "up.py").exists()
        assert "freshness" not in result


@pytest.fixture
def hits_work(make_clone: MakeClone) -> Path:
    """Work clone whose origin/main holds several files containing ``hit``."""
    push_upstream(
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
        tools = ref_tools(make_tools, hits_work)

        assert (await search_ref(tools, glob="*.py"))["files"] == ["src/Mod.py"]
        expected = ["src/Mod.py"] if sys.platform == "win32" else []
        assert (await search_ref(tools, glob="SRC/mod.PY"))["files"] == expected

    async def test_glob_note(self, hits_work: Path, make_tools: MakeTools) -> None:
        tools = ref_tools(make_tools, hits_work)

        result = await search_ref(tools, glob="{a,b}.txt")
        assert result["files"] == []
        assert "Brace expansion is not supported" in result["glob_note"]

    async def test_glob_matching_nothing_by_construction(
        self, hits_work: Path, make_tools: MakeTools
    ) -> None:
        tools = ref_tools(make_tools, hits_work)

        with pytest.raises(ValueError, match="matches nothing by construction"):
            await search_ref(tools, glob="!x")

    async def test_regex_and_context_lines(
        self, hits_work: Path, make_tools: MakeTools
    ) -> None:
        tools = ref_tools(make_tools, hits_work)

        result = await search_ref(tools, pattern="^t.o$", context_lines=1)
        assert result["details"] == [
            {"file": "ctx.txt", "line": 2, "text": "one\ntwo\nthree"}
        ]

    async def test_combined_glob_and_pattern(
        self, hits_work: Path, make_tools: MakeTools
    ) -> None:
        tools = ref_tools(make_tools, hits_work)

        result = await search_ref(tools, glob="a/*", pattern="hit")
        assert hit_files(result) == ["a/x.txt"]

    async def test_content_truncation_in_ls_tree_order(
        self, hits_work: Path, make_tools: MakeTools
    ) -> None:
        tools = ref_tools(make_tools, hits_work)
        order = [f for f in ls_tree(hits_work) if f in {"a/x.txt", "b.txt", "c.txt"}]

        result = await search_ref(tools, pattern="hit", max_results=2)
        assert hit_files(result) == order[:2]
        assert result["truncated"] is True
        assert result["total_matches"] == 3
        assert [m["file"] for m in result["matched_files"]] == order

    async def test_file_search_truncation_in_ls_tree_order(
        self, hits_work: Path, make_tools: MakeTools
    ) -> None:
        tools = ref_tools(make_tools, hits_work)
        order = [f for f in ls_tree(hits_work) if f.endswith(".txt")]

        result = await search_ref(tools, glob="*.txt", max_results=2)
        assert result["files"] == order[:2]
        assert result["total_files"] == len(order)
        assert result["truncated"] is True


class TestSearchSkippedFilesAtRef:
    """Unreadable blobs are reported; binary blobs are skipped silently."""

    async def test_unreadable_blob_in_skipped_files(
        self, hits_work: Path, make_tools: MakeTools
    ) -> None:
        tools = ref_tools(make_tools, hits_work)
        original = RefSnapshot.read_bytes

        def failing(
            self: RefSnapshot, path: str, display_path: str | None = None
        ) -> bytes:
            if path == "b.txt":
                raise ValueError("cannot read")
            return original(self, path, display_path)

        with patch.object(RefSnapshot, "read_bytes", failing):
            result = await search_ref(tools, pattern="hit")
        assert result["skipped_files"] == ["b.txt"]
        assert sorted(hit_files(result)) == ["a/x.txt", "c.txt"]

    async def test_binary_blob_skipped_silently(
        self, make_clone: MakeClone, make_tools: MakeTools
    ) -> None:
        push_upstream(make_clone, {"bin.dat": b"\xff\xfehit\n", "text.txt": b"hit\n"})
        tools = ref_tools(make_tools, make_clone("work"))

        result = await search_ref(tools, pattern="hit")
        assert hit_files(result) == ["text.txt"]
        assert "skipped_files" not in result

    async def test_missing_blob_object_in_skipped_files(
        self, make_clone: MakeClone, make_tools: MakeTools
    ) -> None:
        work = make_clone("work")
        push_upstream(make_clone, {"gone.txt": b"gone\n", "kept.txt": b"kept\n"})
        git_cmd(work, "config", "fetch.unpackLimit", "100000")
        git_cmd(work, "config", "transfer.unpackLimit", "100000")
        git_cmd(work, "fetch", "-q", "origin")
        blob = git_cmd(work, "rev-parse", "refs/remotes/origin/main:gone.txt")
        loose = work / ".git" / "objects" / blob[:2] / blob[2:]
        if not loose.exists():
            pytest.skip("blob object stayed packed")
        os.chmod(loose, stat.S_IREAD | stat.S_IWRITE)
        loose.unlink()
        tools = ref_tools(make_tools, work)

        result = await search_ref(tools, pattern=".")
        assert result["skipped_files"] == ["gone.txt"]
        assert sorted(hit_files(result)) == ["README.md", "kept.txt"]


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
        push_upstream(make_clone, {"eol.txt": data})
        tools = ref_tools(make_tools, make_clone("work"))

        for letter in "abcd":
            result = await search_ref(tools, glob="eol.txt", pattern=f"^{letter}$")
            [match] = result["details"]
            line = match["line"]
            read = await read_ref(
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
        tools = ref_tools(make_tools, ref_work)

        files = (await search_ref(tools, glob="**/*"))["files"]
        assert "link" not in files
        assert "sub" not in files
        assert hit_files(await search_ref(tools, pattern="^z$")) == ["z.txt"]

    async def test_tracked_ignored_file_found(
        self, ref_work: Path, make_tools: MakeTools
    ) -> None:
        tools = ref_tools(make_tools, ref_work)

        result = await search_ref(tools, pattern="tracked but ignored")
        assert hit_files(result) == ["secret.txt"]

    async def test_untracked_local_file_absent(
        self, ref_work: Path, make_tools: MakeTools
    ) -> None:
        (ref_work / "local_only.txt").write_text("LOCAL_ONLY\n", encoding="utf-8")
        tools = ref_tools(make_tools, ref_work)

        assert (await search_ref(tools, pattern="LOCAL_ONLY"))["details"] == []
        assert (await search_ref(tools, glob="local_only.txt"))["files"] == []


class TestSearchLocalFallback:
    """Folders that cannot be searched at a ref are searched locally."""

    async def test_repo_without_origin_adds_fallback_note(
        self, tmp_path: Path, make_tools: MakeTools
    ) -> None:
        path = init_repo(tmp_path / "repo")
        (path / "untracked.txt").write_text("u\n", encoding="utf-8")
        tools = ref_tools(make_tools, path)

        result = await search_ref(tools, glob="*.txt")
        assert sorted(result["files"]) == ["local.txt", "untracked.txt"]
        assert result["freshness"] == FALLBACK_NOTE

    async def test_plain_folder_has_no_freshness(
        self, tmp_path: Path, make_tools: MakeTools
    ) -> None:
        tools = ref_tools(make_tools, plain_folder(tmp_path))

        result = await search_ref(tools, glob="*.txt")
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
        push_upstream(make_clone, {"README.md": b"# Newer\n"})
        tools = ref_tools(make_tools, work, interval=15)

        note = f"[reference ref: fetch failed (boom) — read {short_main(work)}]"
        assert await read_ref(tools, "README.md") == f"# Test Project\n{note}"
        assert (await list_ref(tools))[-1] == note

    async def test_newline_added_before_note(
        self, make_clone: MakeClone, make_tools: MakeTools
    ) -> None:
        push_upstream(make_clone, {"bare.txt": b"no newline"})
        work = make_clone("work")
        tools = ref_tools(make_tools, work, interval=15)

        note = f"[reference ref: fetch failed (boom) — read {short_main(work)}]"
        assert await read_ref(tools, "bare.txt") == f"no newline\n{note}"

    async def test_note_after_truncation_note(
        self, make_clone: MakeClone, make_tools: MakeTools
    ) -> None:
        push_upstream(make_clone, {"three.txt": b"l1\nl2\nl3\n"})
        work = make_clone("work")
        tools = ref_tools(make_tools, work, interval=15, read_max_lines=1)

        note = f"[reference ref: fetch failed (boom) — read {short_main(work)}]"
        assert await read_ref(tools, "three.txt") == (
            "l1\n"
            "[truncated: showing lines 1–1 of 3; continue with start_line=2, "
            f"end_line=2]\n{note}"
        )

    async def test_not_found_carries_note(
        self, origin_clone: Path, make_tools: MakeTools
    ) -> None:
        tools = ref_tools(make_tools, origin_clone, interval=15)
        where = short_main(origin_clone)

        with pytest.raises(FileNotFoundError) as info:
            await read_ref(tools, "nope.txt")
        assert str(info.value) == (
            f"File 'nope.txt' is not in {where} of reference 'ref'.\n"
            f"[reference ref: fetch failed (boom) — read {where}]"
        )
        assert info.value.__context__ is None

    async def test_no_default_ref_gets_both_notes(
        self, tmp_path: Path, make_tools: MakeTools
    ) -> None:
        path = init_repo(tmp_path / "repo")
        git_cmd(path, "remote", "add", "origin", "https://example.invalid/x.git")
        tools = ref_tools(make_tools, path, interval=15)
        notes = f"[reference ref: fetch failed (boom)]\n{FALLBACK_NOTE}"

        assert await read_ref(tools, "local.txt") == f"local\n{notes}"
        assert (await list_ref(tools))[-1] == notes
        with pytest.raises(FileNotFoundError) as info:
            await read_ref(tools, "nope.txt")
        assert str(info.value) == f"File 'nope.txt' does not exist\n{notes}"

    async def test_search_carries_fetch_failure_note(
        self, origin_clone: Path, make_tools: MakeTools
    ) -> None:
        tools = ref_tools(make_tools, origin_clone, interval=15)
        note = f"[reference ref: fetch failed (boom) — read {short_main(origin_clone)}]"

        result = await search_ref(tools, glob="*.md")
        assert result["files"] == ["README.md"]
        assert result["freshness"] == note

    async def test_search_no_default_ref_gets_both_notes(
        self, tmp_path: Path, make_tools: MakeTools
    ) -> None:
        path = init_repo(tmp_path / "repo")
        git_cmd(path, "remote", "add", "origin", "https://example.invalid/x.git")
        tools = ref_tools(make_tools, path, interval=15)

        result = await search_ref(tools, pattern="local")
        assert hit_files(result) == ["local.txt"]
        assert result["freshness"] == (
            f"[reference ref: fetch failed (boom)]\n{FALLBACK_NOTE}"
        )
