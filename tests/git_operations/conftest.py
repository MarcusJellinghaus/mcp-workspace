"""Shared test fixtures for git operations testing."""

from pathlib import Path

import pytest
from git import Repo


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
