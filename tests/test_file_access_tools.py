"""Single-path tools enforce .mcp-file-access on top of the gitignore default."""

import inspect
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from mcp_workspace.file_tools.access_rules import ACCESS_RULES_FILE
from mcp_workspace.reference_projects import ReferenceProject
from mcp_workspace.toolset._context import WorkspaceContext
from mcp_workspace.toolset._github_write_helpers import check_body_target, resolve_body
from tests.conftest import ToolMap

ORIGINAL = "original\n"
ORIGINAL_BYTES = ORIGINAL.encode("utf-8")
GITIGNORE_REFUSAL = "is excluded by .gitignore rules"


def _project(root: Path, rules: str | None = None, gitignore: str = "") -> Path:
    """Build the fixture project: committed and ignored files, a scratch folder."""
    root.mkdir(parents=True, exist_ok=True)
    (root / ".gitignore").write_text(
        gitignore or "*.log\n.scratch/\n", encoding="utf-8"
    )
    for name in ("plain.txt", ".mcp.json", "app.log"):
        (root / name).write_bytes(ORIGINAL_BYTES)
    (root / ".scratch").mkdir(exist_ok=True)
    if rules is not None:
        (root / ACCESS_RULES_FILE).write_bytes(rules.encode("utf-8"))
    return root


async def _call(fn: Callable[..., Any], *args: Any) -> Any:
    """Call a tool, awaiting it when it is async."""
    result = fn(*args)
    if inspect.isawaitable(result):
        return await result
    return result


async def _write(tools: ToolMap, tool: str, path: str) -> Any:
    """Run one writing tool on path with arguments that succeed when allowed."""
    if tool == "save_file":
        return await _call(tools[tool], path, "new\n")
    if tool == "append_file":
        return await _call(tools[tool], path, "more\n")
    if tool == "edit_file":
        return await _call(tools[tool], path, "original", "edited")
    if tool == "move_file":
        return await _call(tools[tool], path, "moved.txt")
    return await _call(tools[tool], path)


WRITE_TOOLS = ["save_file", "append_file", "edit_file", "delete_this_file"]


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", WRITE_TOOLS)
@pytest.mark.parametrize("rule", [None, "read-only", "read-write"])
@pytest.mark.parametrize("path", ["plain.txt", "app.log"])
async def test_write_matrix(
    tmp_path: Path,
    make_tools: Callable[..., ToolMap],
    tool: str,
    rule: str | None,
    path: str,
) -> None:
    rules = None if rule is None else f"{rule} /{path}\n"
    root = _project(tmp_path / "proj", rules)
    tools = make_tools(root)

    if rule == "read-only":
        expected = (
            f"No write access to '{path}' (rule '/{path}' in {ACCESS_RULES_FILE})"
        )
        with pytest.raises(ValueError) as excinfo:
            await _write(tools, tool, path)
        assert str(excinfo.value) == expected
    elif rule is None and path == "app.log":
        with pytest.raises(ValueError, match=GITIGNORE_REFUSAL):
            await _write(tools, tool, path)
    else:
        await _write(tools, tool, path)
        return

    assert (root / path).read_bytes() == ORIGINAL_BYTES


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", [*WRITE_TOOLS, "move_file"])
async def test_logs_directory_rule_refuses_every_write(
    tmp_path: Path, make_tools: Callable[..., ToolMap], tool: str
) -> None:
    root = _project(tmp_path / "proj", "read-only /logs/\n", "*.log\nlogs/\n")
    (root / "logs").mkdir()
    (root / "logs" / "a.log").write_bytes(ORIGINAL_BYTES)
    tools = make_tools(root)

    with pytest.raises(ValueError) as excinfo:
        await _write(tools, tool, "logs/a.log")

    assert str(excinfo.value) == (
        f"No write access to 'logs/a.log' (rule '/logs/' in {ACCESS_RULES_FILE})"
    )
    assert (root / "logs" / "a.log").read_bytes() == ORIGINAL_BYTES
    assert not (root / "moved.txt").exists()
    assert tools["read_file"]("logs/a.log") == ORIGINAL


class TestReadFile:
    """read_file reads exposed ignored files and refuses hidden ones."""

    @pytest.mark.parametrize("level", ["read-only", "read-write"])
    def test_exposed_ignored_file_readable(
        self, tmp_path: Path, make_tools: Callable[..., ToolMap], level: str
    ) -> None:
        root = _project(tmp_path / "proj", f"{level} /app.log\n")
        assert make_tools(root)["read_file"]("app.log") == ORIGINAL

    def test_unexposed_ignored_file_refused(
        self, tmp_path: Path, make_tools: Callable[..., ToolMap]
    ) -> None:
        root = _project(tmp_path / "proj", "read-only /other.log\n")
        with pytest.raises(ValueError, match=GITIGNORE_REFUSAL):
            make_tools(root)["read_file"]("app.log")


class TestMoveFile:
    """move_file needs write access to source and destination."""

    def test_read_only_source_refused(
        self, tmp_path: Path, make_tools: Callable[..., ToolMap]
    ) -> None:
        root = _project(tmp_path / "proj", "read-only /plain.txt\n")
        with pytest.raises(ValueError, match="No write access to 'plain.txt'"):
            make_tools(root)["move_file"]("plain.txt", "other.txt")
        assert (root / "plain.txt").exists()
        assert not (root / "other.txt").exists()

    def test_read_only_destination_refused(
        self, tmp_path: Path, make_tools: Callable[..., ToolMap]
    ) -> None:
        root = _project(tmp_path / "proj", "read-only /target.txt\n")
        with pytest.raises(ValueError, match="No write access to 'target.txt'"):
            make_tools(root)["move_file"]("plain.txt", "target.txt")
        assert (root / "plain.txt").exists()
        assert not (root / "target.txt").exists()


def test_delete_directory_read_only_by_rule_refused(
    tmp_path: Path, make_tools: Callable[..., ToolMap]
) -> None:
    root = _project(tmp_path / "proj", "read-only /docs/\n")
    (root / "docs").mkdir()
    (root / "docs" / "a.md").write_bytes(ORIGINAL_BYTES)

    with pytest.raises(ValueError) as excinfo:
        make_tools(root)["delete_directory"]("docs", recursive=True)

    assert str(excinfo.value) == (
        f"No write access to 'docs' (rule '/docs/' in {ACCESS_RULES_FILE})"
    )
    assert (root / "docs" / "a.md").exists()


class TestRulesFile:
    """The rules file itself is read-only, also when it does not exist."""

    def test_save_refused_when_absent(
        self, tmp_path: Path, make_tools: Callable[..., ToolMap]
    ) -> None:
        root = _project(tmp_path / "proj")
        with pytest.raises(ValueError) as excinfo:
            make_tools(root)["save_file"](ACCESS_RULES_FILE, "read-write /app.log\n")
        assert str(excinfo.value) == (
            f"No write access to '{ACCESS_RULES_FILE}' (built-in)"
        )
        assert not (root / ACCESS_RULES_FILE).exists()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tool", WRITE_TOOLS)
    async def test_writes_refused_when_present(
        self, tmp_path: Path, make_tools: Callable[..., ToolMap], tool: str
    ) -> None:
        root = _project(tmp_path / "proj", ORIGINAL)
        with pytest.raises(ValueError, match=r"\(built-in\)"):
            await _write(make_tools(root), tool, ACCESS_RULES_FILE)
        assert (root / ACCESS_RULES_FILE).read_bytes() == ORIGINAL_BYTES


class TestSpellings:
    """Alternative spellings of a read-only path are refused too."""

    def test_trailing_dot_refused(
        self, tmp_path: Path, make_tools: Callable[..., ToolMap]
    ) -> None:
        root = _project(tmp_path / "proj", "read-only /.mcp.json\n")
        with pytest.raises(ValueError, match="No write access"):
            make_tools(root)["save_file"](".mcp.json.", "{}\n")
        assert (root / ".mcp.json").read_bytes() == ORIGINAL_BYTES

    @pytest.mark.skipif(sys.platform != "win32", reason="case-insensitive on win32")
    def test_other_case_refused(
        self, tmp_path: Path, make_tools: Callable[..., ToolMap]
    ) -> None:
        root = _project(tmp_path / "proj", "read-only /.mcp.json\n")
        with pytest.raises(ValueError, match="No write access"):
            make_tools(root)["save_file"](".MCP.json", "{}\n")
        assert (root / ".mcp.json").read_bytes() == ORIGINAL_BYTES

    def test_git_dir_stays_hidden_under_read_write_rule(
        self, tmp_path: Path, make_tools: Callable[..., ToolMap]
    ) -> None:
        root = _project(tmp_path / "proj", "read-write /.git/\n")
        (root / ".git").mkdir()
        (root / ".git" / "config").write_bytes(ORIGINAL_BYTES)
        with pytest.raises(ValueError, match=GITIGNORE_REFUSAL):
            make_tools(root)["save_file"](".git/config", "x\n")
        assert (root / ".git" / "config").read_bytes() == ORIGINAL_BYTES


class TestInvalidRulesFile:
    """An invalid rules file refuses writes and drops exposures."""

    RULES = "readonly /plain.txt\nread-only /app.log\n"

    def test_write_refused(
        self, tmp_path: Path, make_tools: Callable[..., ToolMap]
    ) -> None:
        root = _project(tmp_path / "proj", self.RULES)
        with pytest.raises(ValueError) as excinfo:
            make_tools(root)["save_file"]("plain.txt", "new\n")
        assert str(excinfo.value).startswith(
            f"No write access to 'plain.txt' ({ACCESS_RULES_FILE} is invalid: "
            "line 1: unknown level "
        )
        assert (root / "plain.txt").read_bytes() == ORIGINAL_BYTES

    def test_committed_file_still_readable(
        self, tmp_path: Path, make_tools: Callable[..., ToolMap]
    ) -> None:
        root = _project(tmp_path / "proj", self.RULES)
        assert make_tools(root)["read_file"]("plain.txt") == ORIGINAL

    def test_exposure_dropped(
        self, tmp_path: Path, make_tools: Callable[..., ToolMap]
    ) -> None:
        root = _project(tmp_path / "proj", self.RULES)
        with pytest.raises(ValueError, match=GITIGNORE_REFUSAL):
            make_tools(root)["read_file"]("app.log")


class TestBodyFile:
    """body_file reads under the read check and writes under the write check."""

    @staticmethod
    def _ctx(root: Path) -> WorkspaceContext:
        return WorkspaceContext(root, {}, None, None, False, True)

    def test_resolve_body_reads_exposed_ignored_file(self, tmp_path: Path) -> None:
        root = _project(tmp_path / "proj", "read-only /app.log\n")
        assert resolve_body(self._ctx(root), None, "app.log", False) == ORIGINAL

    def test_check_body_target_refuses_read_only(self, tmp_path: Path) -> None:
        root = _project(tmp_path / "proj", "read-only /.mcp.json\n")
        with pytest.raises(ValueError, match="No write access to '.mcp.json'"):
            check_body_target(self._ctx(root), ".mcp.json")

    def test_check_body_target_accepts_scratch(self, tmp_path: Path) -> None:
        root = _project(tmp_path / "proj", "read-write /.scratch/\n")
        abs_path, rel_path = check_body_target(self._ctx(root), ".scratch/body.md")
        assert rel_path == ".scratch/body.md"
        assert abs_path.resolve() == (root / ".scratch" / "body.md").resolve()


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["ro.log", "rw.log"])
async def test_read_reference_file_reads_exposed_ignored_file(
    tmp_path: Path, make_tools: Callable[..., ToolMap], name: str
) -> None:
    ref = tmp_path / "ref"
    ref.mkdir()
    (ref / ".gitignore").write_text("*.log\n", encoding="utf-8")
    (ref / ACCESS_RULES_FILE).write_text(
        "read-only /ro.log\nread-write /rw.log\n", encoding="utf-8"
    )
    for file_name in ("ro.log", "rw.log", "hidden.log"):
        (ref / file_name).write_bytes(ORIGINAL_BYTES)
    tools = make_tools(
        reference_projects={"ref": ReferenceProject(name="ref", path=ref)}
    )

    assert await tools["read_reference_file"]("ref", name) == ORIGINAL
    with pytest.raises(ValueError, match=GITIGNORE_REFUSAL):
        await tools["read_reference_file"]("ref", "hidden.log")
