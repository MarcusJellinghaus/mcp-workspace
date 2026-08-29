"""Parent branch detection via merge-base analysis."""

# Maximum commits between merge-base and current HEAD to consider
# the candidate as the parent branch. Higher values are more permissive but
# risk selecting wrong branches; lower values may miss valid parents that
# have moved forward since branching.
from pathlib import Path
from typing import Optional

from git import Commit
from git.exc import GitCommandError, InvalidGitRepositoryError

from .branch_queries import get_default_branch_name
from .core import logger, safe_repo_context
from .repository_status import is_git_repository

MERGE_BASE_DISTANCE_THRESHOLD = 20


def detect_parent_branch_via_merge_base(
    project_dir: Path,
    current_branch: str,
    distance_threshold: int = MERGE_BASE_DISTANCE_THRESHOLD,
) -> Optional[str]:
    """Detect parent branch using git merge-base.

    For each local and remote branch (candidate), find the merge-base with
    current branch. The parent is the branch whose merge-base is closest to
    the current HEAD (smallest distance).

    Args:
        project_dir: Path to git repository
        current_branch: Current branch name
        distance_threshold: Maximum commits between merge-base and current
            HEAD to consider the candidate as the parent branch.
            Defaults to MERGE_BASE_DISTANCE_THRESHOLD (20).

    Returns:
        Branch name (unprefixed) if a single parent can be determined, None if:
        - no candidate is within the distance threshold
        - the current branch is the default branch (nothing to detect)
        - two or more distinct non-default branches tie at the minimum distance
          (ambiguous)

        Callers such as detect_base_branch treat every None the same way and
        fall back to the default branch.
    """
    logger.debug(
        "Detecting parent branch for '%s' via merge-base (threshold=%d)",
        current_branch,
        distance_threshold,
    )

    if not is_git_repository(project_dir):
        logger.debug("Not a git repository: %s", project_dir)
        return None

    try:
        with safe_repo_context(project_dir) as repo:
            # Get current branch commit
            try:
                current_commit = repo.heads[current_branch].commit
            except (IndexError, KeyError) as e:
                logger.debug(
                    "Failed to get commit for branch '%s': %s", current_branch, e
                )
                return None

            default_branch = get_default_branch_name(project_dir)

            if default_branch is not None and current_branch == default_branch:
                logger.debug(
                    "Current branch '%s' is the default branch - no parent branch",
                    current_branch,
                )
                return None

            # Collect candidates. Local and remote refs of the same branch are
            # BOTH scored: they point at different commits when the local ref is
            # stale, and the stale one is not the answer (issue #265).
            candidates: list[tuple[str, str, Commit]] = [
                (head.name, head.name, head.commit)
                for head in repo.heads
                if head.name != current_branch
            ]
            try:
                if "origin" in [r.name for r in repo.remotes]:
                    for ref in repo.remotes.origin.refs:
                        branch_name = ref.name.replace("origin/", "", 1)
                        if branch_name in (current_branch, "HEAD"):
                            continue
                        candidates.append((branch_name, ref.name, ref.commit))
            except (
                Exception
            ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
                logger.debug("Error collecting remote branches: %s", e)

            # Branch name -> smallest distance across that branch's refs. Keying
            # by NAME collapses the local/remote pair of one branch into a single
            # entry, so it can never look like a tie.
            best: dict[str, int] = {}
            for branch_name, ref_name, candidate_commit in candidates:
                try:
                    merge_base_list = repo.merge_base(current_commit, candidate_commit)
                    if not merge_base_list:
                        logger.debug("No merge-base found for '%s'", ref_name)
                        continue

                    merge_base = merge_base_list[0]
                    # Count commits from merge-base to current HEAD
                    distance = sum(
                        1
                        for _ in repo.iter_commits(
                            f"{merge_base.hexsha}..{current_commit.hexsha}"
                        )
                    )
                    logger.debug(
                        "Candidate '%s': merge-base distance = %d", ref_name, distance
                    )

                    if distance > distance_threshold:
                        continue
                    if branch_name not in best or distance < best[branch_name]:
                        best[branch_name] = distance

                except GitCommandError as e:
                    logger.debug("Git error checking '%s': %s", ref_name, e)
                    continue

            if not best:
                logger.debug("No candidate branches found within threshold")
                return None

            minimum = min(best.values())
            winners = sorted(name for name, dist in best.items() if dist == minimum)

            if default_branch in winners:
                winner = default_branch
            elif len(winners) == 1:
                winner = winners[0]
            else:
                logger.debug(
                    "Ambiguous parent branch: %s tied at distance %d", winners, minimum
                )
                return None

            logger.debug(
                "Detected parent branch from merge-base: '%s' (distance=%d)",
                winner,
                minimum,
            )
            return winner

    except InvalidGitRepositoryError:
        logger.debug("Invalid git repository: %s", project_dir)
        return None
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.debug("Failed to detect parent branch: %s", e)
        return None
