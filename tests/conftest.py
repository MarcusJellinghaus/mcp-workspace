"""Test configuration and shared fixtures."""

import contextlib
import os
import shutil
import tempfile
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any, TypedDict, TypeVar

import git
import pytest

from mcp_workspace import config
from mcp_workspace.config import get_github_token, get_test_repo_url
from mcp_workspace.github_operations import clear_repository_cache
from mcp_workspace.toolset import tool_specs

ToolMap = dict[str, Callable[..., Any]]

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


@pytest.fixture
def make_tools(project_dir: Path) -> Callable[..., ToolMap]:
    """Build tools via tool_specs; returns {name: fn}."""

    def _make(root: Path | None = None, **settings: Any) -> ToolMap:
        return {s.name: s.fn for s in tool_specs(root or project_dir, **settings)}

    return _make


@pytest.fixture
def tools(make_tools: Callable[..., ToolMap]) -> ToolMap:
    """Tools bound to the project_dir fixture with default settings."""
    return make_tools()


@pytest.fixture(autouse=True)
def setup_and_cleanup() -> Generator[None, None, None]:
    """
    Fixture to set up and clean up test environment.

    Tests use isolated tmp_path directories via the project_dir fixture,
    so no shared-state cleanup is needed here.
    """
    yield


@pytest.fixture(autouse=True)
def _empty_trusted_commenters(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests from reading the real ``~/.mcp_coder/config.toml`` allowlist."""
    monkeypatch.setattr("mcp_workspace.config.get_trusted_commenters", frozenset)


@pytest.fixture(autouse=True)
def _no_read_max_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests from reading the real ``[mcp_workspace] read_max_lines``."""
    monkeypatch.setattr("mcp_workspace.config.get_read_max_lines", lambda: None)


@pytest.fixture(autouse=True)
def _empty_enterprise_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests from reading the real ``[github] enterprise_hosts`` list."""
    monkeypatch.setattr("mcp_workspace.config.get_enterprise_hosts", frozenset)


@pytest.fixture(autouse=True)
def _reset_repository_cache() -> Generator[None, None, None]:
    """Clear the per-process repository cache for test isolation."""
    clear_repository_cache()
    yield
    clear_repository_cache()


@pytest.fixture(autouse=True)
def _traffic_log_off(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Keep tests from reading the real traffic-log config or writing log files."""
    original = config.get_traffic_log_dir
    original.cache_clear()
    monkeypatch.setattr("mcp_workspace.config.get_traffic_log_dir", lambda: None)
    yield
    original.cache_clear()


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
            "Test repo URL not configured (set GITHUB_TEST_REPO_URL or config file)"
        )

    # Clone the actual test repository
    git_dir = tmp_path / "test_repo"
    try:
        repo = git.Repo.clone_from(test_repo_url, git_dir)
        repo.git.fetch("origin")
        try:
            repo.git.checkout("main")
        except Exception:  # pylint: disable=broad-exception-caught
            with contextlib.suppress(Exception):
                repo.git.checkout("master")
    except Exception as e:  # pylint: disable=broad-exception-caught
        pytest.skip(f"Could not clone test repository {test_repo_url}: {e}")

    setup: GitHubTestSetup = {
        "github_token": github_token,
        "test_repo_url": test_repo_url,
        "project_dir": git_dir,
    }
    yield setup


def _configure_test_repo(repo: git.Repo) -> None:
    """Set the commit identity and disable signing for a test repository."""
    with repo.config_writer() as cfg:
        cfg.set_value("user", "name", "Test User")
        cfg.set_value("user", "email", "test@example.com")
        cfg.set_value("commit", "gpgsign", "false")
        cfg.set_value("tag", "gpgsign", "false")


@pytest.fixture
def _origin_remote(tmp_path: Path) -> Path:
    """Bare ``origin.git`` (HEAD -> ``refs/heads/main``) with one commit on main."""
    origin = tmp_path / "origin.git"
    bare = git.Repo.init(origin, bare=True)
    bare.git.symbolic_ref("HEAD", "refs/heads/main")

    seed = git.Repo.init(tmp_path / "seed")
    _configure_test_repo(seed)
    (tmp_path / "seed" / "README.md").write_text("# Test Project\n")
    seed.index.add(["README.md"])
    seed.index.commit("Initial commit")
    seed.git.branch("-M", "main")
    seed.git.push(str(origin), "refs/heads/main:refs/heads/main")
    return origin


@pytest.fixture
def make_clone(tmp_path: Path, _origin_remote: Path) -> Callable[[str], Path]:
    """Factory for further configured clones of the shared origin.

    ``make_clone(name)`` runs a real ``git clone`` into ``tmp_path / name``.
    """

    def _make(name: str) -> Path:
        clone_dir = tmp_path / name
        _configure_test_repo(git.Repo.clone_from(str(_origin_remote), clone_dir))
        return clone_dir

    return _make


@pytest.fixture
def origin_clone(make_clone: Callable[[str], Path]) -> Path:
    """Fresh clone ``work/`` of a bare origin; has ``origin/HEAD``, no new fetch."""
    return make_clone("work")


T = TypeVar("T")


def create_github_manager(manager_class: type[T], github_setup: GitHubTestSetup) -> T:
    """Create a GitHub manager instance using real configuration."""
    return manager_class(github_setup["project_dir"])  # type: ignore[call-arg]
