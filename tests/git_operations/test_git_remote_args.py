"""Fetch and ls-remote only reach configured remotes, and only update tracking refs."""

from pathlib import Path

import pytest
from git import Repo

from mcp_workspace.git_operations.arg_validation import validate_remote_args
from mcp_workspace.git_operations.read_operations import git

REMOTES = {"origin", "upstream"}


@pytest.mark.parametrize("command", ["fetch", "ls_remote"])
@pytest.mark.parametrize(
    "args",
    [
        ["https://example.invalid/repo.git"],
        ["git@example.invalid:repo.git"],
        ["ssh://example.invalid/repo.git"],
        ["ext::sh -c true"],
        ["file:///some/repo"],
        ["../other-repo"],
        ["/some/repo"],
        ["C:\\some\\repo"],
        ["not-a-remote"],
        ["ORIGIN"],
        ["--tags", "https://example.invalid/repo.git"],
    ],
)
def test_only_configured_remotes_accepted(command: str, args: list[str]) -> None:
    with pytest.raises(ValueError, match="configured remote"):
        validate_remote_args(command, args, REMOTES)


@pytest.mark.parametrize(
    "args",
    [
        ["origin", "main:main"],
        ["origin", "+main:main"],
        ["origin", "+main"],
        ["origin", "refs/heads/*:refs/heads/*"],
        ["origin", ":main"],
        ["origin", "tag", "v1"],
        ["+main:main"],
    ],
)
def test_fetch_refspecs_that_update_local_refs_refused(args: list[str]) -> None:
    with pytest.raises(ValueError):
        validate_remote_args("fetch", args, REMOTES)


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["origin"],
        ["upstream"],
        ["--all"],
        ["--prune"],
        ["--prune", "origin"],
        ["--tags", "origin"],
        ["origin", "main"],
        ["origin", "refs/pull/1/head"],
        ["-v", "origin", "main"],
        ["--depth", "1", "origin"],
        ["--depth=1", "origin"],
    ],
)
def test_fetch_uses_in_practice_accepted(args: list[str]) -> None:
    validate_remote_args("fetch", args, REMOTES)


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["origin"],
        ["--heads", "origin"],
        ["--heads", "origin", "feature/x"],
        ["--heads", "origin", "refs/heads/feature/x"],
        ["--tags", "origin", "v*"],
        ["--get-url", "origin"],
        ["--sort=version:refname", "origin"],
    ],
)
def test_ls_remote_uses_in_practice_accepted(args: list[str]) -> None:
    validate_remote_args("ls_remote", args, REMOTES)


@pytest.mark.parametrize("command", ["log", "diff", "branch", "rev_parse"])
def test_other_commands_are_not_checked(command: str) -> None:
    validate_remote_args(command, ["anything"], REMOTES)


@pytest.fixture(name="repos")
def repos_fixture(
    git_repo_with_remote: tuple[Repo, Path, Path], tmp_path: Path
) -> tuple[Repo, Path, Path]:
    """Repository with origin, plus an unrelated repository outside the project."""
    repo, project_dir, _ = git_repo_with_remote
    repo.git.push("origin", "main")
    repo.git.branch("victim")
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    other = Repo.init(other_dir)
    with other.config_writer() as config:
        config.set_value("user", "name", "Test User")
        config.set_value("user", "email", "test@example.com")
        config.set_value("commit", "gpgsign", "false")
    (other_dir / "other.txt").write_text("other", encoding="utf-8")
    other.index.add(["other.txt"])
    other.index.commit("other history")
    other.git.branch("-M", "main")
    return repo, project_dir, other_dir


def _refs(repo: Repo) -> dict[str, str]:
    return {ref.path: ref.commit.hexsha for ref in repo.references}


@pytest.mark.git_integration
class TestFetchAgainstRealRepos:
    """Refused fetches leave refs as they were; plain fetches still work."""

    @pytest.mark.parametrize(
        "args_template",
        [
            ["-f", "{other}", "+main:victim"],
            ["{other}", "main:victim"],
            ["{other}", "+main:victim"],
            ["{other}"],
            ["--force", "origin", "+main:victim"],
            ["-vf", "origin", "+main:victim"],
            ["origin", "+main:victim"],
            ["origin", "main:created"],
        ],
    )
    def test_refused_without_changing_refs(
        self, repos: tuple[Repo, Path, Path], args_template: list[str]
    ) -> None:
        repo, project_dir, other_dir = repos
        before = _refs(repo)
        args = [arg.format(other=other_dir) for arg in args_template]
        with pytest.raises(ValueError):
            git("fetch", project_dir, args=args)
        assert _refs(repo) == before
        assert not (project_dir / ".git" / "FETCH_HEAD").exists()

    @pytest.mark.parametrize(
        "args",
        [
            None,
            ["origin"],
            ["--prune", "origin"],
            ["--all"],
            ["origin", "main"],
            ["--dry-run", "origin"],
        ],
    )
    def test_fetch_from_origin_still_works(
        self, repos: tuple[Repo, Path, Path], args: list[str] | None
    ) -> None:
        repo, project_dir, _ = repos
        local_before = repo.heads.main.commit.hexsha
        assert isinstance(git("fetch", project_dir, args=args), str)
        assert repo.heads.main.commit.hexsha == local_before


@pytest.mark.git_integration
class TestLsRemoteAgainstRealRepos:
    """ls-remote refuses other locations and works on origin."""

    def test_outside_repo_refused(self, repos: tuple[Repo, Path, Path]) -> None:
        _, project_dir, other_dir = repos
        with pytest.raises(ValueError, match="configured remote"):
            git("ls_remote", project_dir, args=[str(other_dir)])
        with pytest.raises(ValueError, match="configured remote"):
            git("ls_remote", project_dir, args=["--get-url", str(other_dir)])

    def test_origin_heads(self, repos: tuple[Repo, Path, Path]) -> None:
        _, project_dir, _ = repos
        output = git("ls_remote", project_dir, args=["--heads", "origin", "main"])
        assert "refs/heads/main" in output

    def test_origin_get_url(self, repos: tuple[Repo, Path, Path]) -> None:
        repo, project_dir, _ = repos
        output = git("ls_remote", project_dir, args=["--get-url", "origin"])
        assert output == repo.remotes.origin.url

    def test_default_remote(self, repos: tuple[Repo, Path, Path]) -> None:
        _, project_dir, _ = repos
        assert "refs/heads/main" in git("ls_remote", project_dir)
