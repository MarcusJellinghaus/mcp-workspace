"""Real-git regression tests for parent branch detection (issue #265).

Complements the mock-based tests in test_parent_branch_detection.py: the
defects fixed in #265 are ref topology, which mocks cannot express.
"""

from pathlib import Path

import pytest
from git import Repo

from mcp_workspace.git_operations.base_branch import detect_base_branch
from mcp_workspace.git_operations.parent_branch_detection import (
    detect_parent_branch_via_merge_base,
)

pytestmark = pytest.mark.git_integration


def _commit(repo: Repo, project_dir: Path, filename: str) -> str:
    """Create and commit a file; return the new commit sha."""
    (project_dir / filename).write_text(filename)
    repo.index.add([filename])
    return str(repo.index.commit(f"Add {filename}").hexsha)


def test_stale_local_main_does_not_shadow_origin_main(
    git_repo_with_remote: tuple[Repo, Path, Path],
) -> None:
    """A stale local 'main' must not stop origin/main from being scored."""
    repo, project_dir, _bare_remote = git_repo_with_remote

    sha_a = str(repo.head.commit.hexsha)  # A: initial commit on main
    _commit(repo, project_dir, "b.txt")  # B on main
    repo.git.push("-u", "origin", "main")  # origin/main = B

    repo.git.checkout("-b", "other")  # unrelated branch off B
    _commit(repo, project_dir, "o1.txt")
    repo.git.push("-u", "origin", "other")

    repo.git.checkout("main")
    repo.git.checkout("-b", "feature")  # feature off B
    _commit(repo, project_dir, "f1.txt")
    _commit(repo, project_dir, "f2.txt")

    repo.git.branch("-D", "other")  # only origin/other remains
    repo.git.branch("-f", "main", sha_a)  # local main falls behind by one

    # Distances to feature HEAD: local main (A) = 3, origin/main (B) = 2,
    # origin/other (B) = 2. The old dedupe never scored origin/main, so
    # "other" won at 2. origin/main ties at 2 and wins on the default-branch
    # tiebreak.
    assert detect_parent_branch_via_merge_base(project_dir, "feature") == "main"


def test_feature_branch_off_current_main_detects_main(
    git_repo_with_remote: tuple[Repo, Path, Path],
) -> None:
    """Common case still works: local and remote main agree."""
    repo, project_dir, _bare_remote = git_repo_with_remote

    repo.git.push("-u", "origin", "main")
    repo.git.checkout("-b", "feature")
    _commit(repo, project_dir, "f1.txt")

    assert detect_parent_branch_via_merge_base(project_dir, "feature") == "main"


def test_returns_none_on_the_default_branch(
    git_repo_with_remote: tuple[Repo, Path, Path],
) -> None:
    """On 'main' there is no parent branch to detect."""
    repo, project_dir, _bare_remote = git_repo_with_remote

    repo.git.push("-u", "origin", "main")
    repo.git.checkout("-b", "feature")
    _commit(repo, project_dir, "f1.txt")
    repo.git.push("-u", "origin", "feature")
    repo.git.checkout("main")

    # Old behaviour: 'feature' ties at distance 0 and wins on enumeration order.
    assert detect_parent_branch_via_merge_base(project_dir, "main") is None
    # The caller's existing fallback supplies the default branch.
    assert detect_base_branch(project_dir, current_branch="main") == "main"


def test_returns_none_when_two_branches_tie(
    git_repo_with_remote: tuple[Repo, Path, Path],
) -> None:
    """Two distinct non-default names at the minimum distance: no answer."""
    repo, project_dir, _bare_remote = git_repo_with_remote

    sha_a = str(repo.head.commit.hexsha)
    repo.git.push("-u", "origin", "main")  # origin/main = A
    sha_b = _commit(repo, project_dir, "b.txt")  # local main = B, not pushed

    repo.git.checkout("-b", "x", sha_b)
    _commit(repo, project_dir, "x1.txt")
    repo.git.checkout("-b", "y", sha_b)
    _commit(repo, project_dir, "y1.txt")
    repo.git.checkout("-b", "feature", sha_b)
    _commit(repo, project_dir, "f1.txt")
    repo.git.branch("-f", "main", sha_a)

    # Distances to feature HEAD: x = 1, y = 1, main (local and remote, both A) = 2.
    assert detect_parent_branch_via_merge_base(project_dir, "feature") is None
    # Caller falls back to the default branch rather than picking x or y.
    assert detect_base_branch(project_dir, current_branch="feature") == "main"


def test_local_and_remote_ref_of_one_branch_are_not_a_tie(
    git_repo_with_remote: tuple[Repo, Path, Path],
) -> None:
    """A branch scored twice (local + remote) must not trigger the tie fallback."""
    repo, project_dir, _bare_remote = git_repo_with_remote

    repo.git.push("-u", "origin", "main")
    repo.git.checkout("-b", "develop")
    _commit(repo, project_dir, "d1.txt")
    repo.git.push("-u", "origin", "develop")  # local develop == origin/develop
    repo.git.checkout("-b", "feature")
    _commit(repo, project_dir, "f1.txt")

    # 'develop' is scored twice at distance 1; 'main' twice at distance 2.
    assert detect_parent_branch_via_merge_base(project_dir, "feature") == "develop"
