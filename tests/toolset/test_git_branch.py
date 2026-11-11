"""Tests for the git_branch tool."""

import asyncio
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from git import Repo

from mcp_workspace.toolset import tool_specs

_HELPERS = "mcp_workspace.toolset._git_write_helpers"
_SHA = "0123456789abcdef0123456789abcdef01234567"
_OK = {"success": True, "error": None, "returncode": 0, "stderr": ""}


def _git_branch(project_dir: Path, **kwargs: Any) -> str:
    """Call the git_branch tool of a fresh tool set."""
    spec = {s.name: s for s in tool_specs(project_dir)}["git_branch"]
    result: str = asyncio.run(spec.fn(**kwargs))
    return result


@pytest.fixture
def lib() -> Iterator[dict[str, MagicMock]]:
    """Patch the library functions where the helper module imports them."""
    defaults: dict[str, Any] = {
        "is_valid_branch_name_strict": True,
        "operation_in_progress": None,
        "resolve_base_ref": None,
        "resolve_commit": _SHA,
        "switch_branch": _OK,
        "create_and_switch_branch": _OK,
    }
    patchers = {
        name: patch(f"{_HELPERS}.{name}", return_value=value)
        for name, value in defaults.items()
    }
    mocks = {name: p.start() for name, p in patchers.items()}
    yield mocks
    for p in patchers.values():
        p.stop()


def _no_mutation(lib: dict[str, MagicMock]) -> None:
    """Assert that neither branch mutation ran."""
    lib["switch_branch"].assert_not_called()
    lib["create_and_switch_branch"].assert_not_called()


class TestGitBranchUnit:
    """git_branch guardrails with the library patched."""

    def test_switch(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """create=False switches and reports the branch."""
        assert _git_branch(tmp_path, name="main") == "Switched to main"
        lib["switch_branch"].assert_called_once_with(tmp_path, "main")

    def test_invalid_name(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """A name git rejects is refused before any mutation."""
        lib["is_valid_branch_name_strict"].return_value = False

        result = _git_branch(tmp_path, name="a..b", create=True)

        assert result == "Error: invalid branch name: 'a..b'"
        _no_mutation(lib)

    def test_base_without_create(
        self, tmp_path: Path, lib: dict[str, MagicMock]
    ) -> None:
        """base needs create=True; nothing touches git."""
        result = _git_branch(tmp_path, name="feature", base="main")

        assert result == "Error: base requires create=True"
        for mock in lib.values():
            mock.assert_not_called()

    def test_invalid_base(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """An invalid base is refused with its own message."""
        lib["is_valid_branch_name_strict"].side_effect = lambda _d, n: n != "@{-1}"

        result = _git_branch(tmp_path, name="feature", create=True, base="@{-1}")

        assert result == "Error: invalid branch base: '@{-1}'"
        _no_mutation(lib)

    def test_unresolvable_base(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """A base that is no local branch or origin/<branch> is refused."""
        result = _git_branch(tmp_path, name="feature", create=True, base="v1.0")

        assert result == ("Error: base 'v1.0' is not a local branch or origin/<branch>")
        _no_mutation(lib)

    @pytest.mark.parametrize("op", ["rebase", "merge"])
    def test_operation_in_progress(
        self, tmp_path: Path, lib: dict[str, MagicMock], op: str
    ) -> None:
        """A stopped rebase or merge blocks both switch and create."""
        lib["operation_in_progress"].return_value = op

        for create in (False, True):
            result = _git_branch(tmp_path, name="feature", create=create)
            assert result == f"Error: a {op} is in progress; finish or abort it first"
        _no_mutation(lib)

    def test_create_when_origin_branch_exists(
        self, tmp_path: Path, lib: dict[str, MagicMock]
    ) -> None:
        """create=True for a name on origin points to create=False."""
        lib["resolve_base_ref"].side_effect = lambda _d, b: (
            "refs/remotes/origin/feature" if b == "origin/feature" else None
        )

        result = _git_branch(tmp_path, name="feature", create=True)

        assert result.startswith("Error: origin/feature already exists")
        assert "create=False" in result
        _no_mutation(lib)

    @pytest.mark.parametrize(
        "base, ref, no_track",
        [
            ("origin/main", "refs/remotes/origin/main", True),
            ("main", "refs/heads/main", False),
        ],
    )
    def test_create_from_base(
        self,
        tmp_path: Path,
        lib: dict[str, MagicMock],
        base: str,
        ref: str,
        no_track: bool,
    ) -> None:
        """A remote-tracking base gets --no-track, a local one does not."""
        lib["resolve_base_ref"].side_effect = lambda _d, b: ref if b == base else None

        result = _git_branch(tmp_path, name="feature", create=True, base=base)

        assert result == f"Created feature from {base} ({_SHA[:7]})"
        lib["create_and_switch_branch"].assert_called_once_with(
            tmp_path, "feature", ref, no_track=no_track
        )

    def test_create_from_head(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """Without base the branch starts at HEAD."""
        result = _git_branch(tmp_path, name="feature", create=True)

        assert result == f"Created feature from HEAD ({_SHA[:7]})"
        lib["create_and_switch_branch"].assert_called_once_with(
            tmp_path, "feature", None, no_track=False
        )

    def test_mutation_failure(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """A failed mutation reports the reason and git's stderr."""
        lib["switch_branch"].return_value = {
            "success": False,
            "error": "git checkout failed (exit 1)",
            "returncode": 1,
            "stderr": "error: pathspec\n",
        }

        result = _git_branch(tmp_path, name="feature")

        assert result == "Error: git checkout failed (exit 1)\nerror: pathspec"

    def test_library_exception(self, tmp_path: Path, lib: dict[str, MagicMock]) -> None:
        """An exception becomes an error string with credentials scrubbed."""
        lib["switch_branch"].side_effect = RuntimeError(
            "boom https://user:token@github.com/o/r"
        )

        result = _git_branch(tmp_path, name="feature")

        assert result == "Error: boom https://github.com/o/r"


def _current(project_dir: Path) -> str:
    """Return the checked-out branch name."""
    return Repo(project_dir).active_branch.name


def _upstream(project_dir: Path, name: str) -> str | None:
    """Return the upstream of a local branch as ``origin/<b>``, or None."""
    tracking = Repo(project_dir).branches[name].tracking_branch()
    return tracking.name if tracking is not None else None


@pytest.mark.git_integration
class TestGitBranchIntegration:
    """git_branch against a real clone."""

    @pytest.mark.parametrize("name", ["-x", "@{-1}", "a..b"])
    def test_invalid_name(self, origin_clone: Path, name: str) -> None:
        """git's own validation rejects option-like and shorthand names."""
        result = _git_branch(origin_clone, name=name, create=True)

        assert result == f"Error: invalid branch name: {name!r}"
        assert _current(origin_clone) == "main"

    def test_create_then_switch_back(self, origin_clone: Path) -> None:
        """Create from HEAD, then switch back to main."""
        head = Repo(origin_clone).head.commit.hexsha

        created = _git_branch(origin_clone, name="feature", create=True)
        assert created == f"Created feature from HEAD ({head[:7]})"
        assert _current(origin_clone) == "feature"

        assert _git_branch(origin_clone, name="main") == "Switched to main"
        assert _current(origin_clone) == "main"

    def test_switch_to_branch_only_on_origin(
        self, origin_clone: Path, make_clone: Callable[[str], Path]
    ) -> None:
        """A branch present only as origin/<name> becomes a tracking branch."""
        other = make_clone("other")
        Repo(other).git.push("origin", "main:refs/heads/remote-only")
        Repo(origin_clone).git.fetch("origin")

        result = _git_branch(origin_clone, name="remote-only")

        assert result == "Switched to remote-only"
        assert _upstream(origin_clone, "remote-only") == "origin/remote-only"

    def test_switch_typo(self, origin_clone: Path) -> None:
        """An unknown name is an error and creates nothing."""
        result = _git_branch(origin_clone, name="mian")

        assert result.startswith("Error: ")
        assert "run git fetch first" in result
        assert "mian" not in [b.name for b in Repo(origin_clone).branches]

    def test_create_from_origin_has_no_upstream(self, origin_clone: Path) -> None:
        """A branch created from origin/main does not track it."""
        result = _git_branch(
            origin_clone, name="feature", create=True, base="origin/main"
        )

        assert result.startswith("Created feature from origin/main (")
        assert _upstream(origin_clone, "feature") is None
