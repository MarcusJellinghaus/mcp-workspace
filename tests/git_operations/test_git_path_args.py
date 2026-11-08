"""The git tool keeps path arguments inside the repository."""

import os
from pathlib import Path

import pytest
from git import Repo

from mcp_workspace.git_operations.arg_validation import validate_path_args
from mcp_workspace.git_operations.read_operations import (
    git,
    git_check_ignore,
    git_diff,
    git_log,
    git_show,
    git_status,
)

OUTSIDE_TEXT = "OUTSIDE-CONTENT"
SECRET_TEXT = "SECRET=1"
PATH_COMMANDS = ["log", "diff", "show", "status", "ls_tree", "ls_files", "check_ignore"]


@pytest.mark.parametrize("command", PATH_COMMANDS)
@pytest.mark.parametrize(
    "token",
    [
        "/etc/passwd",
        "C:\\Windows\\win.ini",
        "C:/Windows/win.ini",
        "C:secret",
        "\\\\server\\share\\file",
        "../outside",
        "..\\outside",
        "..",
        "sub/../../outside",
        "HEAD:../outside",
        "HEAD:/etc/passwd",
        ":(top)../outside",
        ":(glob)../**",
        ":!../outside",
        ":/../outside",
        ".git/config",
        ".GIT/config",
        ":(top).git/config",
        "",
    ],
)
def test_outside_paths_refused_as_argument_and_pathspec(
    command: str, token: str
) -> None:
    with pytest.raises(ValueError, match="stay inside the"):
        validate_path_args(command, [token], None)
    with pytest.raises(ValueError, match="stay inside the"):
        validate_path_args(command, [], [token])


@pytest.mark.parametrize("command", PATH_COMMANDS)
@pytest.mark.parametrize(
    "token",
    [
        "HEAD",
        "main",
        "origin/main",
        "abc1234",
        "main..HEAD",
        "main...HEAD",
        "HEAD~3",
        "HEAD^2",
        "HEAD^{tree}",
        "@{u}",
        "stash@{0}",
        "HEAD:src/file.py",
        ":0:src/file.py",
        "refs/remotes/origin/main",
        "v1.0..v2.0",
        "src/file.py",
        "./src/file.py",
        ".",
        ".github/workflows/ci.yml",
        ".gitignore",
        "*.py",
        ":(glob)src/**/*.py",
        ":(icase)readme.md",
        ":!docs",
        ":^docs",
        ":/src",
        ":/fix the ../ handling",
    ],
)
def test_refs_and_inside_paths_allowed(command: str, token: str) -> None:
    validate_path_args(command, [token], None)


@pytest.mark.parametrize(
    "args",
    [
        ["--grep", "../text"],
        ["--author", "/some/name"],
        ["--since", "../x"],
        ["-n", "5"],
    ],
)
def test_flag_values_are_not_paths(args: list[str]) -> None:
    validate_path_args("log", args, None)


@pytest.mark.parametrize("command", ["fetch", "rev_parse", "merge_base", "ls_remote"])
def test_commands_without_paths_are_not_checked(command: str) -> None:
    validate_path_args(command, ["refs/heads/x"], None)


@pytest.fixture
def repo_setup(
    git_repo_with_commit: tuple[Repo, Path],
) -> tuple[Repo, Path, Path, Path]:
    """Repository with a gitignored secret and two files outside it."""
    repo, project_dir = git_repo_with_commit
    (project_dir / ".gitignore").write_text(".env\n", encoding="utf-8")
    (project_dir / ".env").write_text(SECRET_TEXT + "\n", encoding="utf-8")
    repo.index.add([".gitignore"])
    repo.index.commit("add ignore rules")
    outside_a = project_dir.parent / "outside_a.txt"
    outside_b = project_dir.parent / "outside_b.txt"
    outside_a.write_text(OUTSIDE_TEXT + "-A\n", encoding="utf-8")
    outside_b.write_text(OUTSIDE_TEXT + "-B\n", encoding="utf-8")
    return repo, project_dir, outside_a, outside_b


def _refused_without_content(call: object, *args: object, **kwargs: object) -> None:
    """Assert a refusal that carries neither protected content."""
    with pytest.raises(ValueError) as excinfo:
        call(*args, **kwargs)  # type: ignore[operator]
    assert OUTSIDE_TEXT not in str(excinfo.value)
    assert SECRET_TEXT not in str(excinfo.value)


@pytest.mark.git_integration
class TestDiffStaysInRepository:
    """git diff reads neither outside files nor gitignored files."""

    @pytest.mark.parametrize("compact", [True, False])
    def test_two_outside_paths_as_args(
        self, repo_setup: tuple[Repo, Path, Path, Path], compact: bool
    ) -> None:
        _, project_dir, outside_a, outside_b = repo_setup
        _refused_without_content(
            git_diff,
            project_dir,
            args=[str(outside_a), str(outside_b)],
            compact=compact,
        )

    def test_outside_and_gitignored_as_args(
        self, repo_setup: tuple[Repo, Path, Path, Path]
    ) -> None:
        _, project_dir, outside_a, _ = repo_setup
        _refused_without_content(git_diff, project_dir, args=[str(outside_a), ".env"])

    def test_relative_outside_and_gitignored_as_args(
        self, repo_setup: tuple[Repo, Path, Path, Path]
    ) -> None:
        _, project_dir, outside_a, _ = repo_setup
        relative = os.path.relpath(outside_a, project_dir)
        _refused_without_content(git_diff, project_dir, args=[relative, ".env"])

    @pytest.mark.parametrize("compact", [True, False])
    def test_two_outside_paths_as_pathspec(
        self, repo_setup: tuple[Repo, Path, Path, Path], compact: bool
    ) -> None:
        _, project_dir, outside_a, outside_b = repo_setup
        _refused_without_content(
            git_diff,
            project_dir,
            pathspec=[str(outside_a), str(outside_b)],
            compact=compact,
        )

    def test_two_outside_paths_after_separator(
        self, repo_setup: tuple[Repo, Path, Path, Path]
    ) -> None:
        _, project_dir, outside_a, outside_b = repo_setup
        _refused_without_content(
            git_diff, project_dir, args=["--", str(outside_a), str(outside_b)]
        )

    def test_absolute_gitignored_path_in_repo_with_other_spelling(
        self, repo_setup: tuple[Repo, Path, Path, Path]
    ) -> None:
        _, project_dir, *_ = repo_setup
        spelled = str(project_dir).upper()
        _refused_without_content(
            git_diff, project_dir, args=[f"{spelled}/.env", f"{spelled}/README.md"]
        )

    def test_link_inside_repo_shows_no_outside_content(
        self, repo_setup: tuple[Repo, Path, Path, Path]
    ) -> None:
        _, project_dir, outside_a, _ = repo_setup
        try:
            os.symlink(outside_a, project_dir / "outlink")
        except OSError as exc:
            pytest.skip(f"symlinks unavailable: {exc}")
        output = git_diff(project_dir, args=["outlink", ".env"], compact=False)
        assert OUTSIDE_TEXT not in output
        assert SECRET_TEXT not in output

    def test_gitignored_files_inside_repo_show_no_content(
        self, repo_setup: tuple[Repo, Path, Path, Path]
    ) -> None:
        repo, project_dir, *_ = repo_setup
        tracked = str(next(iter(repo.head.commit.tree.blobs)).path)
        output = git_diff(project_dir, args=[".env", tracked], compact=False)
        assert SECRET_TEXT not in output
        output = git_diff(project_dir, pathspec=[".env"], compact=False)
        assert SECRET_TEXT not in output


@pytest.mark.git_integration
class TestOtherCommandsStayInRepository:
    """The other path-taking commands refuse before git runs."""

    def test_show_outside(self, repo_setup: tuple[Repo, Path, Path, Path]) -> None:
        _, project_dir, outside_a, _ = repo_setup
        _refused_without_content(git_show, project_dir, args=[str(outside_a)])
        _refused_without_content(git_show, project_dir, args=["HEAD:../outside_a.txt"])
        _refused_without_content(git_show, project_dir, pathspec=[str(outside_a)])

    def test_log_outside(self, repo_setup: tuple[Repo, Path, Path, Path]) -> None:
        _, project_dir, outside_a, _ = repo_setup
        _refused_without_content(git_log, project_dir, args=["-p", str(outside_a)])
        _refused_without_content(git_log, project_dir, pathspec=[str(outside_a)])

    def test_status_outside(self, repo_setup: tuple[Repo, Path, Path, Path]) -> None:
        _, project_dir, outside_a, _ = repo_setup
        _refused_without_content(git_status, project_dir, pathspec=[str(outside_a)])

    def test_check_ignore_outside(
        self, repo_setup: tuple[Repo, Path, Path, Path]
    ) -> None:
        _, project_dir, outside_a, _ = repo_setup
        _refused_without_content(
            git_check_ignore, project_dir, pathspec=[str(outside_a)]
        )

    @pytest.mark.parametrize("command", ["ls_tree", "ls_files"])
    def test_listing_outside(
        self, repo_setup: tuple[Repo, Path, Path, Path], command: str
    ) -> None:
        _, project_dir, outside_a, _ = repo_setup
        args = ["HEAD"] if command == "ls_tree" else []
        _refused_without_content(
            git, command, project_dir, args=args, pathspec=[str(outside_a)]
        )

    def test_show_gitignored_file_at_rev_has_no_content(
        self, repo_setup: tuple[Repo, Path, Path, Path]
    ) -> None:
        _, project_dir, *_ = repo_setup
        with pytest.raises(Exception) as excinfo:
            git_show(project_dir, args=["HEAD:.env"])
        assert SECRET_TEXT not in str(excinfo.value)


@pytest.mark.git_integration
class TestPathUseThatStaysAllowed:
    """Real callers keep working."""

    def test_diff_rev_and_stat(self, repo_setup: tuple[Repo, Path, Path, Path]) -> None:
        _, project_dir, *_ = repo_setup
        assert isinstance(git_diff(project_dir, ["HEAD", "--stat"]), str)

    def test_diff_range(self, repo_setup: tuple[Repo, Path, Path, Path]) -> None:
        _, project_dir, *_ = repo_setup
        assert isinstance(git_diff(project_dir, args=["HEAD~1...HEAD"]), str)

    def test_diff_pathspec(self, repo_setup: tuple[Repo, Path, Path, Path]) -> None:
        _, project_dir, *_ = repo_setup
        output = git_diff(
            project_dir, args=["HEAD~1"], pathspec=[".gitignore"], compact=False
        )
        assert "gitignore" in output

    def test_log_pathspec_and_magic(
        self, repo_setup: tuple[Repo, Path, Path, Path]
    ) -> None:
        _, project_dir, *_ = repo_setup
        assert "add ignore rules" in git_log(project_dir, pathspec=[".gitignore"])
        assert "add ignore rules" in git_log(
            project_dir, pathspec=[":(glob)**/.gitignore"]
        )

    def test_show_blob_at_rev(self, repo_setup: tuple[Repo, Path, Path, Path]) -> None:
        _, project_dir, *_ = repo_setup
        assert ".env" in git_show(project_dir, args=["HEAD:.gitignore"])

    def test_check_ignore_inside(
        self, repo_setup: tuple[Repo, Path, Path, Path]
    ) -> None:
        _, project_dir, *_ = repo_setup
        assert ".env" in git_check_ignore(project_dir, pathspec=[".env"])
        assert "No paths" in git_check_ignore(
            project_dir, pathspec=[".mcp-coder/rebase_sessions/probe"]
        )

    def test_ls_files_inside(self, repo_setup: tuple[Repo, Path, Path, Path]) -> None:
        _, project_dir, *_ = repo_setup
        assert ".gitignore" in git("ls_files", project_dir, pathspec=[".gitignore"])
