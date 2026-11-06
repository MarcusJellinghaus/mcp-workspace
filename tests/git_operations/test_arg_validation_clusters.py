"""Short flag clusters are checked character by character for every subcommand."""

from pathlib import Path

import pytest
from git import Repo

from mcp_workspace.git_operations.arg_validation import (
    _ALLOWLISTS,
    validate_args,
    validate_branch_has_read_flag,
)
from mcp_workspace.git_operations.read_operations import git

_LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _short_flags(command: str) -> list[str]:
    return sorted(
        flag for flag in _ALLOWLISTS[command] if len(flag) == 2 and flag[1].isalpha()
    )


def _cluster_cases() -> list[tuple[str, str]]:
    """Every allowed short flag followed by every letter not allowed for its command."""
    return [
        (command, f"{flag}{letter}")
        for command, allowlist in _ALLOWLISTS.items()
        for flag in _short_flags(command)
        for letter in _LETTERS
        if f"-{letter}" not in allowlist
    ]


@pytest.mark.parametrize("command, cluster", _cluster_cases())
def test_cluster_with_unlisted_letter_refused(command: str, cluster: str) -> None:
    with pytest.raises(ValueError, match="not in the security allowlist"):
        validate_args(command, [cluster])


@pytest.mark.parametrize(
    "command, arg",
    [
        ("branch", "-vD"),
        ("branch", "-vd"),
        ("branch", "-vm"),
        ("branch", "-aM"),
        ("branch", "-rc"),
        ("log", "-pO/some/file"),
        ("log", "-p--output=out.txt"),
        ("diff", "-p--output=out.txt"),
        ("diff", "-bO/some/file"),
        ("fetch", "-vf"),
        ("fetch", "-vu"),
        ("fetch", "-qk"),
        ("status", "-sq"),
        ("ls_files", "-cf"),
        ("log", "-n-5"),
        ("log", "-nX"),
        ("diff", "-Ufoo"),
        ("diff", "-M/some/file"),
        ("status", "-uX"),
        ("log", "-n=5"),
        ("log", "-<int>"),
        ("log", "-"),
    ],
)
def test_refused_short_forms(command: str, arg: str) -> None:
    with pytest.raises(ValueError, match="not in the security allowlist"):
        validate_args(command, [arg])


@pytest.mark.parametrize(
    "command, arg",
    [
        ("log", "-n5"),
        ("log", "-n"),
        ("log", "-10"),
        ("log", "-U3"),
        ("log", "-pU3"),
        ("log", "-pn5"),
        ("diff", "-U3"),
        ("diff", "-U0"),
        ("diff", "-M90%"),
        ("diff", "-C90%"),
        ("diff", "-M"),
        ("diff", "-wb"),
        ("diff", "-5"),
        ("show", "-U3"),
        ("show", "-M50"),
        ("status", "-s"),
        ("status", "-sb"),
        ("status", "-uno"),
        ("status", "-uall"),
        ("status", "-unormal"),
        ("status", "-z"),
        ("branch", "-vv"),
        ("branch", "-av"),
        ("branch", "-rv"),
        ("fetch", "-v"),
        ("fetch", "-q"),
        ("ls_tree", "-rt"),
        ("ls_files", "-cd"),
        ("check_ignore", "-vn"),
        ("merge_base", "-a"),
    ],
)
def test_short_forms_in_use_stay_allowed(command: str, arg: str) -> None:
    validate_args(command, [arg])


@pytest.mark.parametrize(
    "args",
    [
        ["-v", "name"],
        ["--no-color", "name"],
        ["--sort=refname", "name"],
        ["--show-current", "name"],
        ["-a", "name"],
        ["-D", "name"],
        ["-vD", "name"],
        ["-vD"],
        ["-m", "a", "b"],
        ["name"],
        [],
    ],
)
def test_branch_refuses_args_that_do_not_list(args: list[str]) -> None:
    with pytest.raises(ValueError, match="read-only flag"):
        validate_branch_has_read_flag(args)


@pytest.mark.parametrize(
    "args",
    [
        ["--list"],
        ["--list", "feat*"],
        ["-a", "--list", "feat*"],
        ["-vv"],
        ["-a", "-v"],
        ["-r"],
        ["--show-current"],
        ["--contains", "HEAD"],
        ["-a", "--contains", "abc123"],
        ["--merged", "main"],
        ["--no-merged", "main"],
        ["--sort", "refname"],
        ["--sort=-committerdate"],
    ],
)
def test_branch_keeps_listing_args(args: list[str]) -> None:
    validate_args("branch", args)
    validate_branch_has_read_flag(args)


@pytest.mark.git_integration
class TestBranchAgainstRealRepo:
    """Refused branch calls leave the refs as they were."""

    @pytest.mark.parametrize(
        "args",
        [
            ["-v", "-vD", "victim"],
            ["-vD", "victim"],
            ["-vd", "victim"],
            ["-vm", "victim", "renamed"],
            ["-v", "created"],
            ["--no-color", "created"],
            ["--sort=refname", "created"],
        ],
    )
    def test_refused_without_changing_refs(
        self, git_repo_with_commit: tuple[Repo, Path], args: list[str]
    ) -> None:
        repo, project_dir = git_repo_with_commit
        repo.create_head("victim")
        before = sorted(head.name for head in repo.heads)
        with pytest.raises(ValueError):
            git("branch", project_dir, args=args)
        assert sorted(head.name for head in repo.heads) == before

    @pytest.mark.parametrize(
        "args, expected",
        [
            (["--list"], "victim"),
            (["--list", "vic*"], "victim"),
            (["-vv"], "victim"),
            (["-a"], "victim"),
            (["--contains", "HEAD"], "victim"),
            (["--merged", "HEAD"], "victim"),
            (["--sort=-refname"], "victim"),
        ],
    )
    def test_listing_still_works(
        self,
        git_repo_with_commit: tuple[Repo, Path],
        args: list[str],
        expected: str,
    ) -> None:
        repo, project_dir = git_repo_with_commit
        repo.create_head("victim")
        assert expected in git("branch", project_dir, args=args)

    def test_show_current_still_works(
        self, git_repo_with_commit: tuple[Repo, Path]
    ) -> None:
        repo, project_dir = git_repo_with_commit
        assert git("branch", project_dir, args=["--show-current"]) == (
            repo.active_branch.name
        )


@pytest.mark.git_integration
class TestFlagsInUseAgainstRealRepo:
    """The forms real callers use still reach git and succeed."""

    @pytest.mark.parametrize(
        "command, args",
        [
            ("log", ["-n5"]),
            ("log", ["-1", "--oneline"]),
            ("log", ["-n", "1"]),
            ("log", ["--grep", "nothing-matches-this"]),
            ("diff", ["-U3"]),
            ("diff", ["HEAD", "--stat"]),
            ("diff", ["--cached"]),
            ("diff", ["HEAD...HEAD"]),
            ("show", ["-U1", "HEAD"]),
            ("status", ["-sb"]),
            ("status", ["-uno"]),
            ("rev_parse", ["HEAD"]),
            ("rev_parse", ["--verify", "HEAD"]),
            ("merge_base", ["--is-ancestor", "HEAD", "HEAD"]),
            ("ls_tree", ["-r", "HEAD"]),
            ("ls_files", ["-cd"]),
        ],
    )
    def test_succeeds(
        self,
        git_repo_with_commit: tuple[Repo, Path],
        command: str,
        args: list[str],
    ) -> None:
        _, project_dir = git_repo_with_commit
        assert isinstance(git(command, project_dir, args=args), str)


@pytest.mark.git_integration
@pytest.mark.parametrize(
    "command, args",
    [
        ("diff", ["--output=out.txt"]),
        ("diff", ["--output", "out.txt"]),
        ("log", ["--output=out.txt"]),
        ("show", ["--output=out.txt"]),
        ("diff", ["--ext-diff"]),
        ("log", ["--ext-diff"]),
        ("show", ["--ext-diff"]),
        ("diff", ["--textconv"]),
        ("log", ["--textconv"]),
        ("show", ["--textconv"]),
        ("diff", ["--no-index"]),
        ("fetch", ["--upload-pack=prog"]),
        ("fetch", ["--upload-pack", "prog"]),
        ("fetch", ["--refmap=x"]),
        ("fetch", ["--recurse-submodules"]),
        ("fetch", ["-u"]),
        ("fetch", ["--update-head-ok"]),
        ("ls_remote", ["--upload-pack=prog"]),
        ("log", ["-c"]),
        ("diff", ["-c"]),
        ("show", ["-c"]),
        ("status", ["-c"]),
        ("log", ["--exec=prog"]),
        ("rev_parse", ["--git-path", "config"]),
        ("ls_files", ["--exclude-from=x"]),
        ("ls_files", ["-X", "x"]),
        ("log", ["--end-of-options"]),
    ],
)
def test_flags_with_external_effects_refused_on_real_repo(
    git_repo_with_commit: tuple[Repo, Path], command: str, args: list[str]
) -> None:
    _, project_dir = git_repo_with_commit
    before = sorted(p.name for p in project_dir.iterdir())
    with pytest.raises(ValueError, match="not in the security allowlist"):
        git(command, project_dir, args=args)
    assert sorted(p.name for p in project_dir.iterdir()) == before


@pytest.mark.parametrize("command", ["tag", "remote", "stash", "push", "config"])
def test_other_subcommands_refused(command: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown git command"):
        git(command, tmp_path, args=["-d", "x"])
