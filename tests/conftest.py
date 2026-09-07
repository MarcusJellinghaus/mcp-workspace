"""Test configuration and shared fixtures."""

import os
import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any, Type, TypeVar, cast

import git
import pytest

from mcp_workspace.config import get_github_token, get_test_repo_url

# Python path is now configured via pytest configuration in pyproject.toml

# Set up the project directory for testing
PROJECT_DIR = Path(os.path.abspath(os.path.dirname(__file__)))

# Test constants
TEST_DIR = Path("testdata/test_file_tools")
TEST_FILE = TEST_DIR / "test_file.txt"
TEST_CONTENT = "This is test content."


def _symlinks_supported() -> bool:
    """Check whether this platform lets us create symlinks.

    Both link kinds are probed: on Windows a directory symlink is a distinct
    object kind and can be refused separately from a file symlink.

    Returns:
        True if both a file and a directory symlink could be created.
    """
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "target"
        target.touch()
        dir_target = Path(tmp) / "dir_target"
        dir_target.mkdir()
        try:
            (Path(tmp) / "link").symlink_to(target)
            (Path(tmp) / "dir_link").symlink_to(dir_target, target_is_directory=True)
        except (OSError, NotImplementedError):
            return False
    return True


requires_symlinks = pytest.mark.skipif(
    not _symlinks_supported(),
    reason="symlink creation not permitted on this platform",
)


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Fixture to provide an isolated project directory for each test.

    Uses pytest's tmp_path to ensure tests don't interfere with each other
    when running in parallel with -n auto.
    """
    # Copy reference test data (read-only files like indent_testing_data.txt)
    testdata_src = PROJECT_DIR / "testdata"
    if testdata_src.exists():
        shutil.copytree(testdata_src, tmp_path / "testdata")

    # Ensure test file tools directory exists
    (tmp_path / TEST_DIR).mkdir(parents=True, exist_ok=True)

    return tmp_path


@pytest.fixture(autouse=True)
def setup_and_cleanup() -> Generator[None, None, None]:
    """
    Fixture to set up and clean up test environment.

    Tests use isolated tmp_path directories via the project_dir fixture,
    so no shared-state cleanup is needed here.
    """
    yield


try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict


class GitHubTestSetup(TypedDict):
    """Configuration data for GitHub integration tests."""

    github_token: str
    test_repo_url: str
    project_dir: Path


@pytest.fixture
def github_test_setup(tmp_path: Path) -> Generator[GitHubTestSetup, None, None]:
    """Provide shared GitHub test configuration and repository setup.

    Validates GitHub configuration and gracefully skips when missing.
    """
    github_token = get_github_token()
    test_repo_url = get_test_repo_url()

    if not github_token:
        pytest.skip("GitHub token not configured (set GITHUB_TOKEN or config file)")

    if not test_repo_url:
        pytest.skip(
            "Test repo URL not configured " "(set GITHUB_TEST_REPO_URL or config file)"
        )

    # Clone the actual test repository
    git_dir = tmp_path / "test_repo"
    try:
        repo = git.Repo.clone_from(test_repo_url, git_dir)
        repo.git.fetch("origin")
        try:
            repo.git.checkout("main")
        except Exception:  # pylint: disable=broad-exception-caught
            try:
                repo.git.checkout("master")
            except Exception:  # pylint: disable=broad-exception-caught
                pass
    except Exception as e:  # pylint: disable=broad-exception-caught
        pytest.skip(f"Could not clone test repository {test_repo_url}: {e}")

    setup: GitHubTestSetup = {
        "github_token": github_token,
        "test_repo_url": test_repo_url,
        "project_dir": git_dir,
    }
    yield setup


T = TypeVar("T")


def create_github_manager(manager_class: Type[T], github_setup: GitHubTestSetup) -> T:
    """Create a GitHub manager instance using real configuration."""
    return manager_class(github_setup["project_dir"])  # type: ignore[call-arg]
