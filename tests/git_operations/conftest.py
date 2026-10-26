"""Shared test fixtures for git operations testing."""

from pathlib import Path
from typing import Callable, Optional, Union

import pytest
from git import Repo

FileChanges = dict[str, Optional[Union[str, bytes]]]


def commit_files(repo: Repo, files: FileChanges, message: str) -> str:
    """Write (None = delete) files, stage everything and commit.

    Args:
        repo: Repository to commit in
        files: Repo-relative path -> text, bytes, or None to delete
        message: Commit message

    Returns:
        The full sha of the new commit.
    """
    root = Path(repo.working_dir)
    for name, content in files.items():
        path = root / name
        if content is None:
            path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_bytes(content.encode("utf-8"))
    repo.git.add("-A")
    repo.git.commit("-m", message)
    sha: str = repo.git.rev_parse("HEAD")
    return sha


@pytest.fixture
def make_conflict_repo(
    git_repo: tuple[Repo, Path],
) -> Callable[[FileChanges, FileChanges, FileChanges], tuple[Repo, Path]]:
    """Builder for two diverged branches, ``main`` and ``feature``.

    ``build(base, main_change, feature_change)`` commits ``base`` on ``main``,
    then ``main_change`` on ``main``, then ``feature_change`` on ``feature``
    (branched from ``base``), and leaves ``feature`` checked out.
    """
    repo, project_dir = git_repo
    repo.git.config("core.autocrlf", "false")

    def build(
        base: FileChanges, main_change: FileChanges, feature_change: FileChanges
    ) -> tuple[Repo, Path]:
        commit_files(repo, base, "base")
        repo.git.branch("-M", "main")
        repo.git.branch("feature")
        commit_files(repo, main_change, "main change")
        repo.git.checkout("feature")
        commit_files(repo, feature_change, "feature change")
        return repo, project_dir

    return build


@pytest.fixture
def git_repo(tmp_path: Path) -> tuple[Repo, Path]:
    """Create clean, empty git repository for testing.

    Args:
        tmp_path: Pytest temporary directory fixture

    Returns:
        tuple[Repo, Path]: Git repository object and path to project directory
    """
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()

    # Initialize git repository
    repo = Repo.init(project_dir)

    # Configure git user (required for commits)
    with repo.config_writer() as config:
        config.set_value("user", "name", "Test User")
        config.set_value("user", "email", "test@example.com")
        config.set_value("commit", "gpgsign", "false")
        config.set_value("tag", "gpgsign", "false")

    return repo, project_dir


@pytest.fixture
def git_repo_with_remote(tmp_path: Path) -> tuple[Repo, Path, Path]:
    """Create git repository with a bare remote origin.

    Args:
        tmp_path: Pytest temporary directory fixture

    Returns:
        tuple[Repo, Path, Path]: (repo, project_dir, bare_remote_dir)
    """
    # Create bare remote repository
    bare_remote_dir = tmp_path / "remote.git"
    bare_remote_dir.mkdir()
    Repo.init(bare_remote_dir, bare=True)

    # Create local project repository
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    repo = Repo.init(project_dir)

    # Configure git user
    with repo.config_writer() as config:
        config.set_value("user", "name", "Test User")
        config.set_value("user", "email", "test@example.com")
        config.set_value("commit", "gpgsign", "false")
        config.set_value("tag", "gpgsign", "false")

    # Create initial commit
    readme = project_dir / "README.md"
    readme.write_text("# Test Project")
    repo.index.add(["README.md"])
    repo.index.commit("Initial commit")

    # Rename default branch to 'main' for consistency across different Git configurations
    repo.git.branch("-M", "main")

    # Add bare repo as origin remote
    repo.create_remote("origin", str(bare_remote_dir))

    return repo, project_dir, bare_remote_dir


@pytest.fixture
def git_repo_with_commit(tmp_path: Path) -> tuple[Repo, Path]:
    """Create git repository with one initial commit.

    Args:
        tmp_path: Pytest temporary directory fixture

    Returns:
        tuple[Repo, Path]: Git repository object and path to project directory
    """
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()

    # Initialize git repository
    repo = Repo.init(project_dir)

    # Configure git user
    with repo.config_writer() as config:
        config.set_value("user", "name", "Test User")
        config.set_value("user", "email", "test@example.com")
        config.set_value("commit", "gpgsign", "false")
        config.set_value("tag", "gpgsign", "false")

    # Create initial commit
    readme = project_dir / "README.md"
    readme.write_text("# Test Project")
    repo.index.add(["README.md"])
    repo.index.commit("Initial commit")

    return repo, project_dir
