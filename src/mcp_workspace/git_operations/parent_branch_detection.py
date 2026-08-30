"""Parent branch detection via merge-base analysis."""

# Maximum commits between merge-base and current HEAD to consider
# the candidate as the parent branch. Higher values are more permissive but
# risk selecting wrong branches; lower values may miss valid parents that
# have moved forward since branching.
from pathlib import Path
from typing import Optional

from git import Commit, RemoteReference, Repo
from git.exc import GitCommandError, InvalidGitRepositoryError

from .branch_queries import get_default_branch_name
from .core import logger, safe_repo_context
from .repository_status import is_git_repository

MERGE_BASE_DISTANCE_THRESHOLD = 20


def _merge_base_distance(
    repo: Repo, current_commit: Commit, candidate_commit: Commit, ref_name: str
) -> Optional[int]:
    """Count the commits between merge-base(HEAD, candidate) and HEAD.

    Args:
        repo: Open repository
        current_commit: Commit of the current branch
        candidate_commit: Commit of the candidate ref
        ref_name: Candidate ref name, for logging only

    Returns:
        Distance in commits, or None if there is no merge-base or git fails.
    """
    try:
        merge_base_list = repo.merge_base(current_commit, candidate_commit)
        if not merge_base_list:
            logger.debug("No merge-base found for '%s'", ref_name)
            return None

        merge_base = merge_base_list[0]
        distance = sum(
            1
            for _ in repo.iter_commits(f"{merge_base.hexsha}..{current_commit.hexsha}")
        )
        logger.debug("Candidate '%s': merge-base distance = %d", ref_name, distance)
        return distance

    except GitCommandError as e:
        logger.debug("Git error checking '%s': %s", ref_name, e)
        return None


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
        - the current branch is the default branch (nothing to detect); when no
          default branch can be resolved, this check is skipped and a candidate
          may be returned even on the trunk
        - two or more distinct non-default branches tie at the minimum distance
          (ambiguous), unless no default branch can be resolved at all, in
          which case the first tied name is returned rather than leaving the
          caller with no fallback either

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
            candidates: list[tuple[str, str, Commit]] = []
            for head in repo.heads:
                if head.name == current_branch:
                    continue
                try:
                    candidates.append((head.name, head.name, head.commit))
                except (
                    Exception
                ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
                    # One unreadable ref must not cost us every other candidate.
                    logger.debug("Error reading local branch '%s': %s", head.name, e)
            remote_refs: list[RemoteReference] = []
            try:
                if "origin" in [r.name for r in repo.remotes]:
                    remote_refs = list(repo.remotes.origin.refs)
            except (
                Exception
            ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
                logger.debug("Error listing remote branches: %s", e)
            for ref in remote_refs:
                try:
                    branch_name = ref.name.replace("origin/", "", 1)
                    if branch_name in (current_branch, "HEAD"):
                        continue
                    candidates.append((branch_name, ref.name, ref.commit))
                except (
                    Exception
                ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
                    # One unreadable ref must not cost us every other candidate.
                    logger.debug("Error reading remote branch: %s", e)

            # Branch name -> smallest distance across that branch's refs. Keying
            # by NAME collapses the local/remote pair of one branch into a single
            # entry, so it can never look like a tie.
            best: dict[str, int] = {}
            # Commit sha -> distance (None = unscorable). Local and remote refs
            # of one branch normally point at the same commit, and that commit
            # only has to be walked once; they are still scored separately when
            # they actually differ, which is the case issue #265 is about.
            distance_by_commit: dict[str, Optional[int]] = {}
            for branch_name, ref_name, candidate_commit in candidates:
                sha = candidate_commit.hexsha
                if sha not in distance_by_commit:
                    distance_by_commit[sha] = _merge_base_distance(
                        repo, current_commit, candidate_commit, ref_name
                    )

                distance = distance_by_commit[sha]
                if distance is None or distance > distance_threshold:
                    continue
                if branch_name not in best or distance < best[branch_name]:
                    best[branch_name] = distance

            if not best:
                logger.debug("No candidate branches found within threshold")
                return None

            minimum = min(best.values())
            winners = sorted(name for name, dist in best.items() if dist == minimum)

            if default_branch is not None and default_branch in winners:
                winner = default_branch
            elif len(winners) == 1:
                winner = winners[0]
            elif default_branch is None:
                # Returning None here would cascade: the caller's fallback is
                # the default branch, which does not resolve either, so the
                # base would end up "unknown". winners is sorted, so picking
                # the first is at least deterministic.
                logger.debug(
                    "Ambiguous parent branch %s at distance %d and no default "
                    "branch to fall back on - picking '%s'",
                    winners,
                    minimum,
                    winners[0],
                )
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
