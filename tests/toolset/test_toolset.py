"""Acceptance tests for the exported workspace toolset."""

import asyncio
import inspect
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pydantic
import pytest
from mcp_coder_utils.tool_spec import ToolSpec

from mcp_workspace.file_tools import DEFAULT_READ_MAX_LINES
from mcp_workspace.reference_projects import ReferenceProject
from mcp_workspace.toolset import tool_specs
from mcp_workspace.toolset._context import WorkspaceContext

# Every exported tool: name -> (group, read_only).
EXPECTED: dict[str, tuple[str, bool]] = {
    "read_file": ("workspace.read", True),
    "list_directory": ("workspace.read", True),
    "search_files": ("workspace.read", True),
    "save_file": ("workspace.write", False),
    "edit_file": ("workspace.write", False),
    "append_file": ("workspace.write", False),
    "delete_this_file": ("workspace.delete", False),
    "delete_directory": ("workspace.delete", False),
    "move_file": ("workspace.move", False),
    "get_reference_projects": ("workspace.reference", True),
    "read_reference_file": ("workspace.reference", True),
    "list_reference_directory": ("workspace.reference", True),
    "search_reference_files": ("workspace.reference", True),
    "git": ("workspace.git", True),
    "git_branch": ("workspace.git", False),
    "git_branch_delete": ("workspace.git", False),
    "github_issue_view": ("workspace.github", True),
    "github_issue_list": ("workspace.github", True),
    "github_pr_view": ("workspace.github", True),
    "github_search": ("workspace.github", True),
    "github_label_list": ("workspace.github", True),
    "github_subissue_list": ("workspace.github", True),
    "github_issue_create": ("workspace.github", False),
    "github_issue_edit": ("workspace.github", False),
    "github_issue_set_status": ("workspace.github", False),
    "github_issue_comment": ("workspace.github", False),
    "github_review_comment_reply": ("workspace.github", False),
    "github_review_thread_resolve": ("workspace.github", False),
    "github_subissue_add": ("workspace.github", False),
    "github_subissue_remove": ("workspace.github", False),
    "github_pr_create": ("workspace.github", False),
    "check_file_size": ("workspace.checks", True),
    "check_branch_status": ("workspace.checks", True),
    "get_base_branch": ("workspace.checks", True),
}

ASYNC_TOOLS = {
    "edit_file",
    "git",
    "git_branch",
    "git_branch_delete",
    "check_branch_status",
    "read_reference_file",
    "list_reference_directory",
    "search_reference_files",
}

OUTSIDE_TEXT = "OUTSIDE=1\n"
SECRET_TEXT = "SECRET=1\n"


def _specs(root: Path, **settings: Any) -> dict[str, ToolSpec]:
    """Return the specs of one factory call by name."""
    return {s.name: s for s in tool_specs(root, **settings)}


def _call(spec: ToolSpec, **kwargs: Any) -> Any:
    """Call a sync or async tool and return its result."""
    if inspect.iscoroutinefunction(spec.fn):
        return asyncio.run(spec.fn(**kwargs))
    return spec.fn(**kwargs)


def test_groups_and_read_only_match_table(tmp_path: Path) -> None:
    specs = _specs(tmp_path)

    assert {n: (s.group, s.read_only) for n, s in specs.items()} == EXPECTED
    for name, spec in specs.items():
        assert inspect.iscoroutinefunction(spec.fn) is (name in ASYNC_TOOLS), name


def test_read_and_write_tools_work_on_temp_project(tmp_path: Path) -> None:
    specs = _specs(tmp_path)

    assert _call(specs["save_file"], file_path="f.txt", content="hello\n") is True
    assert _call(specs["append_file"], file_path="f.txt", content="world\n") is True
    _call(specs["edit_file"], file_path="f.txt", old_string="world", new_string="there")

    assert (tmp_path / "f.txt").read_text(encoding="utf-8") == "hello\nthere\n"
    assert _call(specs["read_file"], file_path="f.txt") == "hello\nthere\n"
    assert "f.txt" in _call(specs["list_directory"])
    found = _call(specs["search_files"], pattern="there")
    assert [(d["file"], d["text"]) for d in found["details"]] == [("f.txt", "there")]


@pytest.mark.parametrize(
    "tool, kwargs",
    [
        ("read_file", {"file_path": "../outside.txt"}),
        ("list_directory", {"path": ".."}),
        ("save_file", {"file_path": "../outside.txt", "content": "changed"}),
        ("save_file", {"file_path": "../new.txt", "content": "changed"}),
        ("append_file", {"file_path": "../outside.txt", "content": "changed"}),
        (
            "edit_file",
            {"file_path": "../outside.txt", "old_string": "OUT", "new_string": "x"},
        ),
    ],
)
def test_read_write_tools_refuse_outside_paths(
    tmp_path: Path, tool: str, kwargs: dict[str, Any]
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text(OUTSIDE_TEXT, encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        _call(_specs(root)[tool], **kwargs)

    assert OUTSIDE_TEXT.strip() not in str(excinfo.value)
    assert outside.read_text(encoding="utf-8") == OUTSIDE_TEXT
    assert not (tmp_path / "new.txt").exists()


@pytest.mark.parametrize(
    "tool, kwargs",
    [
        ("read_file", {"file_path": "secret.txt"}),
        ("save_file", {"file_path": "secret.txt", "content": "changed"}),
        ("append_file", {"file_path": "secret.txt", "content": "changed"}),
        (
            "edit_file",
            {"file_path": "secret.txt", "old_string": "SECRET", "new_string": "x"},
        ),
    ],
)
def test_read_write_tools_refuse_gitignored_paths(
    tmp_path: Path, tool: str, kwargs: dict[str, Any]
) -> None:
    (tmp_path / ".gitignore").write_text("secret.txt\n", encoding="utf-8")
    secret = tmp_path / "secret.txt"
    secret.write_text(SECRET_TEXT, encoding="utf-8")
    specs = _specs(tmp_path)

    with pytest.raises(ValueError, match="excluded by .gitignore"):
        _call(specs[tool], **kwargs)

    assert secret.read_text(encoding="utf-8") == SECRET_TEXT
    assert _call(specs["search_files"], pattern="SECRET")["details"] == []


def test_two_factories_do_not_interfere(tmp_path: Path) -> None:
    root_a, root_b = tmp_path / "a", tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    a = _specs(root_a, read_max_lines=2)
    b = _specs(root_b)
    five_lines = "".join(f"line {n}\n" for n in range(1, 6))

    _call(a["save_file"], file_path="f.txt", content=five_lines)

    assert (root_a / "f.txt").is_file()
    assert not (root_b / "f.txt").exists()

    (root_b / "f.txt").write_text(five_lines, encoding="utf-8")
    read_a = _call(a["read_file"], file_path="f.txt")
    read_b = _call(b["read_file"], file_path="f.txt")
    assert read_a.startswith("line 1\nline 2\n[truncated:")
    assert "line 3" not in read_a
    assert read_b == five_lines


def test_two_factories_have_separate_file_locks(tmp_path: Path) -> None:
    contexts: list[WorkspaceContext] = []

    def _record(**kwargs: Any) -> WorkspaceContext:
        ctx = WorkspaceContext(**kwargs)
        contexts.append(ctx)
        return ctx

    roots = [tmp_path / "a", tmp_path / "b"]
    with patch("mcp_workspace.toolset.WorkspaceContext", side_effect=_record):
        factories = [_specs(root) for root in roots]

    for root, specs in zip(roots, factories, strict=True):
        root.mkdir()
        (root / "f.txt").write_text("old\n", encoding="utf-8")
        _call(specs["edit_file"], file_path="f.txt", old_string="old", new_string="new")

    assert len(contexts) == 2
    assert contexts[0].file_locks is not contexts[1].file_locks
    for root, ctx in zip(roots, contexts, strict=True):
        assert list(ctx.file_locks) == [str((root / "f.txt").resolve())]


def test_read_file_default_truncates_at_default_read_max_lines(
    tmp_path: Path,
) -> None:
    total = DEFAULT_READ_MAX_LINES + 5
    text = "".join(f"line {n}\n" for n in range(1, total + 1))
    (tmp_path / "big.txt").write_text(text, encoding="utf-8")

    result = _call(_specs(tmp_path)["read_file"], file_path="big.txt")

    assert f"line {DEFAULT_READ_MAX_LINES}\n" in result
    assert f"line {DEFAULT_READ_MAX_LINES + 1}\n" not in result
    assert f"start_line={DEFAULT_READ_MAX_LINES + 1}" in result


@pytest.mark.asyncio
async def test_read_reference_file_default_truncates(tmp_path: Path) -> None:
    ref_dir = tmp_path / "ref"
    ref_dir.mkdir()
    total = DEFAULT_READ_MAX_LINES + 5
    text = "".join(f"line {n}\n" for n in range(1, total + 1))
    (ref_dir / "big.txt").write_text(text, encoding="utf-8")
    specs = _specs(
        tmp_path,
        reference_projects={"ref": ReferenceProject(name="ref", path=ref_dir)},
    )

    with patch(
        "mcp_workspace.toolset.reference.ensure_available",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await specs["read_reference_file"].fn(
            reference_name="ref", file_path="big.txt"
        )

    assert f"line {DEFAULT_READ_MAX_LINES}\n" in result
    assert f"line {DEFAULT_READ_MAX_LINES + 1}\n" not in result
    assert f"start_line={DEFAULT_READ_MAX_LINES + 1}" in result


def test_args_model_with_required_args_only(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("content\n", encoding="utf-8")
    specs = _specs(tmp_path)

    read = specs["read_file"]
    model = read.args_model.model_validate({"file_path": "f.txt"})
    assert read.fn(**model.model_dump(exclude_unset=True)) == "content\n"

    search = specs["search_files"]
    model = search.args_model.model_validate({"glob": "*.txt"})
    assert search.fn(**model.model_dump(exclude_unset=True))["files"] == ["f.txt"]


@pytest.mark.parametrize("arguments", [{}, {"file_path": "f.txt", "start_line": "abc"}])
def test_args_model_rejects_invalid_arguments(
    tmp_path: Path, arguments: dict[str, Any]
) -> None:
    read = _specs(tmp_path)["read_file"]

    with pytest.raises(pydantic.ValidationError):
        read.args_model.model_validate(arguments)
