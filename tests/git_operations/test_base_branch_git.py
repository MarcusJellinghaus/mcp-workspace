"""Real-git regression tests for base branch detection (issue #269).

A merge-base winner whose branch was deleted on origin must be discarded, so
detection falls back to the default branch instead of naming a branch that is
gone. The topology involved is ref state, which mocks cannot express.
"""

from pathlib import Path

import pytest
from git import Repo

from mcp_workspace.git_operations.base_branch import detect_base_branch

pytestmark = pytest.mark.git_integration


def _commit(repo: Repo, project_dir: Path, filename: str) -> str:
    """Create and commit a file; return the new commit sha."""
    (project_dir / filename).write_text(filename)
    repo.index.add([filename])
    return str(repo.index.commit(f"Add {filename}").hexsha)


def _stack_on_feature_a(
    repo: Repo, project_dir: Path, push_feature_a: bool = True
) -> None:
    """Push main, branch feature-A off it, stack feature-B on feature-A.

    Leaves HEAD on feature-B. Merge-base scoring elects 'feature-A' at
    distance 1 over 'main' at distance 2.
    """
    repo.git.push("-u", "origin", "main")
    repo.git.checkout("-b", "feature-A")
    _commit(repo, project_dir, "a1.txt")
    if push_feature_a:
        repo.git.push("-u", "origin", "feature-A")
    repo.git.checkout("-b", "feature-B")
    _commit(repo, project_dir, "b1.txt")


def test_winner_deleted_upstream_falls_back_to_default_branch(
    git_repo_with_remote: tuple[Repo, Path, Path],
) -> None:
    """A winner deleted on origin is discarded in favour of the default branch."""
    repo, project_dir, bare_remote_dir = git_repo_with_remote

    _stack_on_feature_a(repo, project_dir)
    # Delete on origin without fetching, so the local origin/feature-A ref
    # survives exactly as it does after a merged PR is deleted on GitHub.
    Repo(bare_remote_dir).delete_head("feature-A", force=True)

    assert detect_base_branch(project_dir, current_branch="feature-B") == "main"


def test_winner_still_on_origin_is_kept(
    git_repo_with_remote: tuple[Repo, Path, Path],
) -> None:
    """A winner that origin still lists is returned unchanged."""
    repo, project_dir, _bare_remote_dir = git_repo_with_remote

    _stack_on_feature_a(repo, project_dir)

    assert detect_base_branch(project_dir, current_branch="feature-B") == "feature-A"


def test_never_pushed_winner_is_kept(
    git_repo_with_remote: tuple[Repo, Path, Path],
) -> None:
    """A local-only winner was never on origin, so it cannot be gone from it."""
    repo, project_dir, _bare_remote_dir = git_repo_with_remote

    _stack_on_feature_a(repo, project_dir, push_feature_a=False)

    assert detect_base_branch(project_dir, current_branch="feature-B") == "feature-A"


def test_unreachable_origin_keeps_the_winner(
    git_repo_with_remote: tuple[Repo, Path, Path],
    tmp_path: Path,
) -> None:
    """An unanswerable origin must never rewrite a correct base to the default."""
    repo, project_dir, _bare_remote_dir = git_repo_with_remote

    _stack_on_feature_a(repo, project_dir)
    # origin/feature-A stays intact locally while ls-remote fails immediately.
    repo.git.remote("set-url", "origin", str(tmp_path / "gone.git"))

    assert detect_base_branch(project_dir, current_branch="feature-B") == "feature-A"
