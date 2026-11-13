"""list_directory shows the paths .mcp-file-access exposes, with access suffixes."""

from collections.abc import Callable
from pathlib import Path

import pytest

from mcp_workspace.file_tools.access_rules import ACCESS_RULES_FILE
from tests.conftest import ToolMap

GITIGNORE_REFUSAL = "is excluded by .gitignore rules"
WARNING_PREFIX = f"WARNING: {ACCESS_RULES_FILE} is invalid"


def _project(root: Path, gitignore: str, rules: str | None, files: list[str]) -> Path:
    """Build a project with a .gitignore, an optional rules file and files."""
    root.mkdir(parents=True, exist_ok=True)
    (root / ".gitignore").write_text(gitignore, encoding="utf-8")
    if rules is not None:
        (root / ACCESS_RULES_FILE).write_text(rules, encoding="utf-8")
    for rel in files:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rel, encoding="utf-8")
    return root


@pytest.fixture
def suffix_tools(tmp_path: Path, make_tools: Callable[..., ToolMap]) -> ToolMap:
    """Tools on a project with a read-only and a read-write exposure."""
    root = _project(
        tmp_path / "proj",
        gitignore="uv.lock\n.scratch/\n",
        rules="read-only /uv.lock\nread-write /.scratch/\nread-only /.mcp.json\n",
        files=["uv.lock", ".scratch/p.py", ".mcp.json", "plain.txt"],
    )
    return make_tools(root)


def test_suffixes_mark_access_that_differs_from_default(
    suffix_tools: ToolMap,
) -> None:
    """Exposed and read-only files carry a suffix; unmatched files do not."""
    result = suffix_tools["list_directory"]()

    assert "uv.lock (read-only)" in result
    assert ".scratch/p.py (read-write, not committed)" in result
    assert ".mcp.json (read-only)" in result
    assert "plain.txt" in result
    assert ".gitignore" in result
    assert f"{ACCESS_RULES_FILE} (read-only)" in result


def test_dirs_only_has_no_suffixes(suffix_tools: ToolMap) -> None:
    """dirs_only output lists directories only, never marked."""
    assert suffix_tools["list_directory"](dirs_only=True) == [".scratch/"]


def test_collapsed_directory_counts_exposed_files_unmarked(
    tmp_path: Path, make_tools: Callable[..., ToolMap]
) -> None:
    """A collapsed directory line is unmarked and counts only exposed files."""
    kept = [f"data/run/keep{i:03}.tmp" for i in range(300)]
    dropped = [f"data/run/drop{i}.tmp" for i in range(5)]
    root = _project(
        tmp_path / "proj",
        gitignore="*.tmp\n",
        rules="read-only /data/run/keep*.tmp\n",
        files=kept + dropped,
    )

    result = make_tools(root)["list_directory"]()

    assert result == [
        "data/run/ (300 files)",
        ".gitignore",
        f"{ACCESS_RULES_FILE} (read-only)",
    ]


def test_hidden_directory_with_rule_lists_exposed_paths(
    tmp_path: Path, make_tools: Callable[..., ToolMap]
) -> None:
    """An ignored directory a rule exposes lists only what the walk reaches."""
    root = _project(
        tmp_path / "proj",
        gitignore="logs/\n",
        rules="read-only /logs/\n",
        files=["logs/a.log", "logs/sub/b.log", "plain.txt"],
    )

    result = make_tools(root)["list_directory"]("logs")

    assert result == ["logs/sub/b.log (read-only)", "logs/a.log (read-only)"]


def test_hidden_directory_without_rule_is_refused(
    tmp_path: Path, make_tools: Callable[..., ToolMap]
) -> None:
    """An ignored directory no rule exposes is refused without leaking names."""
    root = _project(
        tmp_path / "proj",
        gitignore="logs/\n",
        rules="read-only /uv.lock\n",
        files=["logs/a.log"],
    )

    with pytest.raises(ValueError, match=GITIGNORE_REFUSAL) as exc_info:
        make_tools(root)["list_directory"]("logs")

    assert "a.log" not in str(exc_info.value)


def test_nonexistent_ignored_directory_gets_gitignore_message(
    tmp_path: Path, make_tools: Callable[..., ToolMap]
) -> None:
    """A missing ignored directory does not reveal that it does not exist."""
    root = _project(tmp_path / "proj", gitignore="secret/\n", rules=None, files=[])

    with pytest.raises(ValueError, match=GITIGNORE_REFUSAL):
        make_tools(root)["list_directory"]("secret")


def test_git_directory_is_refused_despite_rule(
    tmp_path: Path, make_tools: Callable[..., ToolMap]
) -> None:
    """A read-write rule on .git/ does not make it listable."""
    root = _project(
        tmp_path / "proj",
        gitignore="",
        rules="read-write /.git/\n",
        files=[".git/HEAD"],
    )

    with pytest.raises(ValueError, match="inside a git directory"):
        make_tools(root)["list_directory"](".git")


def test_invalid_rules_file_warns_and_drops_suffixes(
    tmp_path: Path, make_tools: Callable[..., ToolMap]
) -> None:
    """An invalid rules file prepends a warning line and marks nothing."""
    root = _project(
        tmp_path / "proj",
        gitignore="uv.lock\n",
        rules="readonly /uv.lock\nread-only /.mcp.json\n",
        files=["uv.lock", ".mcp.json", "plain.txt"],
    )

    result = make_tools(root)["list_directory"]()

    assert result[0].startswith(WARNING_PREFIX)
    assert sorted(result[1:]) == sorted(
        [".gitignore", ".mcp.json", ACCESS_RULES_FILE, "plain.txt"]
    )


def test_invalid_rules_file_warning_not_counted_in_cap(
    tmp_path: Path, make_tools: Callable[..., ToolMap]
) -> None:
    """The warning line comes on top of the 250 lines and the truncation line."""
    root = _project(
        tmp_path / "proj",
        gitignore="",
        rules="readonly /x\n",
        files=[f"f{i:03}.txt" for i in range(300)],
    )

    result = make_tools(root)["list_directory"]()

    assert len(result) == 252
    assert result[0].startswith(WARNING_PREFIX)
    assert not any(line.startswith("WARNING") for line in result[1:])
    assert result[-1].startswith("... and ")


def test_file_path_is_refused_as_file(
    tmp_path: Path, make_tools: Callable[..., ToolMap]
) -> None:
    """A readable file path gets the 'is a file' error."""
    root = _project(tmp_path / "proj", gitignore="", rules=None, files=["a.txt"])

    with pytest.raises(ValueError, match="is a file"):
        make_tools(root)["list_directory"]("a.txt")


def test_hidden_file_path_gets_gitignore_message(
    tmp_path: Path, make_tools: Callable[..., ToolMap]
) -> None:
    """A hidden file path is refused as hidden, not reported as a file."""
    root = _project(
        tmp_path / "proj", gitignore="secret.txt\n", rules=None, files=["secret.txt"]
    )

    with pytest.raises(ValueError, match=GITIGNORE_REFUSAL):
        make_tools(root)["list_directory"]("secret.txt")
