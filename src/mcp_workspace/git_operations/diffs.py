"""Git diff operations for generating change summaries."""

from pathlib import Path

from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError

from .branch_queries import branch_exists, get_current_branch_name, remote_branch_exists
from .core import PLACEHOLDER_HASH, logger, safe_repo_context
from .repository_status import is_git_repository


def get_git_diff_for_commit(project_dir: Path) -> str | None:
    """Generate comprehensive git diff without modifying repository state.

    Shows staged, unstaged, and untracked files in unified diff format
    suitable for LLM analysis and commit message generation.

    Args:
        project_dir: Path to the project directory containing git repository

    Returns:
        str: Unified diff format with sections for staged changes, unstaged
             changes, and untracked files. Each section uses format:
             === SECTION NAME ===
             [diff content]

             Returns empty string if no changes detected.
        None: If error occurs (invalid repository, git command failure, etc.)

    Example:
        >>> diff_output = get_git_diff_for_commit(Path("/path/to/repo"))
        >>> if diff_output is not None:
        ...     print("Changes detected" if diff_output else "No changes")

    Note:
        - Uses read-only git operations, never modifies repository state
        - Binary files handled naturally by git (shows "Binary files differ")
        - Continues processing even if individual git operations fail
        - Empty repositories (no commits) supported
    """
    logger.debug("Generating git diff for: %s", project_dir)

    if not is_git_repository(project_dir):
        logger.error("Not a git repository: %s", project_dir)
        return None

    try:
        with safe_repo_context(project_dir) as repo:
            # Simple check for empty repository (KISS approach)
            has_commits = True
            try:
                list(repo.iter_commits(max_count=1))
            except (GitCommandError, ValueError):
                has_commits = False
                logger.debug("Empty repository detected, showing untracked files only")

            # Generate diff sections with individual error handling
            staged_diff = ""
            unstaged_diff = ""

            if has_commits:
                try:
                    staged_diff = repo.git.diff(
                        "--cached", "--unified=5", "--no-prefix"
                    )
                except GitCommandError as e:
                    logger.warning("Failed to get staged diff: %s", e)

                try:
                    unstaged_diff = repo.git.diff("--unified=5", "--no-prefix")
                except GitCommandError as e:
                    logger.warning("Failed to get unstaged diff: %s", e)

            # Always try to get untracked files
            untracked_diff = _generate_untracked_diff(repo, project_dir)

            return _format_diff_sections(staged_diff, unstaged_diff, untracked_diff)

    except (InvalidGitRepositoryError, GitCommandError) as e:
        logger.error("Git error generating diff: %s", e)
        return None
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.error("Unexpected error generating diff: %s", e)
        return None


def get_branch_diff(
    project_dir: Path,
    base_branch: str | None = None,
    exclude_paths: list[str] | None = None,
    ansi: bool = False,
) -> str:
    """Generate git diff between current branch and base branch.

    Args:
        project_dir: Path to the project directory containing git repository
        base_branch: Base branch to compare against. If None, returns empty
            string with error log. Callers should use detect_base_branch()
            to determine the base branch before calling this function.
        exclude_paths: List of paths to exclude from diff (e.g., ['pr_info/', '*.log'])
        ansi: If True, prepend --color=always and --color-moved=dimmed-zebra to diff
            args so that ANSI colour codes are preserved in the output.
            Default False preserves existing behaviour.

    Returns:
        Git diff string between base branch and current HEAD, or empty string on error

    Note:
        - Uses three-dot notation (base...HEAD) to show changes on current branch
        - If base_branch doesn't exist locally but exists on origin,
          falls back to using origin/{base_branch} for comparison.
        - Returns empty string for any error conditions (invalid repo, missing branch, etc.)
        - Uses unified diff format with 5 lines of context
    """
    logger.debug(
        "Getting branch diff for %s (base: %s, excludes: %s)",
        project_dir,
        base_branch,
        exclude_paths,
    )

    # Validate repository
    if not is_git_repository(project_dir):
        logger.error("Directory %s is not a git repository", project_dir)
        return ""

    # Require explicit base branch - no auto-detection
    if base_branch is None:
        logger.error(
            "base_branch is required. Use detect_base_branch() from "
            "workflow_utils.base_branch to determine the base branch."
        )
        return ""

    try:
        with safe_repo_context(project_dir) as repo:
            # Get current branch for validation
            current_branch = get_current_branch_name(project_dir)
            if current_branch is None:
                logger.error("Could not determine current branch")
                return ""

            # Check if current branch is the base branch
            if current_branch == base_branch:
                logger.debug("Current branch is the base branch, no diff to show")
                return ""

            # Verify base branch exists (local or remote)
            if not branch_exists(project_dir, base_branch):
                # Try remote ref as fallback
                if remote_branch_exists(project_dir, base_branch):
                    logger.debug(
                        "Local branch '%s' not found, using remote ref 'origin/%s'",
                        base_branch,
                        base_branch,
                    )
                    base_branch = f"origin/{base_branch}"
                else:
                    logger.error(
                        "Base branch '%s' does not exist locally or on remote",
                        base_branch,
                    )
                    return ""

            # Build git diff command
            if exclude_paths:
                # When using exclusions, we need to construct the command differently
                # git diff base...HEAD -- . ':!excluded_path'
                diff_args = [
                    "-M",
                    "-C90%",
                    f"{base_branch}...HEAD",
                    "--unified=5",
                    "--no-prefix",
                    "--",
                    ".",
                ]
                for path in exclude_paths:
                    # Use pathspec magic to exclude paths
                    diff_args.append(f":!{path}")
            else:
                # Simple diff without exclusions
                diff_args = [
                    "-M",
                    "-C90%",
                    f"{base_branch}...HEAD",
                    "--unified=5",
                    "--no-prefix",
                ]

            # Prepend ANSI colour flags when requested
            if ansi:
                diff_args = [
                    "--color=always",
                    "--color-moved=dimmed-zebra",
                ] + diff_args

            # Execute git diff; on non-Windows set LC_ALL so git outputs UTF-8.
            # Use custom_environment() to pass the variable only to the git
            # subprocess, without touching the current process environment.
            import os

            if os.name != "nt":
                with repo.git.custom_environment(LC_ALL="C.UTF-8"):
                    diff_output = repo.git.diff(*diff_args)
            else:
                diff_output = repo.git.diff(*diff_args)

            logger.debug(
                "Generated diff between %s and %s (%d bytes)",
                base_branch,
                current_branch,
                len(diff_output),
            )

            return str(diff_output)

    except GitCommandError as e:
        logger.error("Git command error generating diff: %s", e)
        return ""
    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.error("Unexpected error generating diff: %s", e)
        return ""


def _generate_untracked_diff(repo: Repo, project_dir: Path) -> str:
    """Generate diff for untracked files by creating synthetic diff output.

    Returns:
        Synthetic diff string for untracked files, or empty string if none.
    """
    try:
        untracked_files = repo.untracked_files
        if not untracked_files:
            return ""

        untracked_diffs = []
        for file_path in untracked_files:
            try:
                # Read the file content
                full_path = project_dir / file_path
                if full_path.exists() and full_path.is_file():
                    # Create a synthetic diff that looks like git's output
                    try:
                        content = full_path.read_text(encoding="utf-8")
                        lines = content.splitlines()

                        # Create git-style diff header
                        diff_lines = [
                            f"diff --git {file_path} {file_path}",
                            "new file mode 100644",
                            f"index 0000000..{PLACEHOLDER_HASH}",
                            "--- /dev/null",
                            f"+++ {file_path}",
                            "@@ -0,0 +1," + str(len(lines)) + " @@",
                        ]

                        # Add file content with + prefix
                        for line in lines:
                            diff_lines.append("+" + line)

                        untracked_diffs.append("\n".join(diff_lines))
                    except UnicodeDecodeError:
                        # Handle binary files
                        diff_lines = [
                            f"diff --git {file_path} {file_path}",
                            "new file mode 100644",
                            f"index 0000000..{PLACEHOLDER_HASH}",
                            "Binary files /dev/null and " + file_path + " differ",
                        ]
                        untracked_diffs.append("\n".join(diff_lines))
            except (
                Exception
            ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
                # Skip individual files that can't be processed
                logger.debug(
                    "Skipping untracked file that couldn't be processed: %s - %s",
                    file_path,
                    e,
                )
                continue

        return "\n".join(untracked_diffs)

    except (
        Exception
    ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
        logger.warning("Error generating untracked file diff: %s", e)
        return ""


def _format_diff_sections(
    staged_diff: str, unstaged_diff: str, untracked_diff: str
) -> str:
    """Format diff sections with appropriate headers.

    Returns:
        Combined diff string with section headers.
    """
    sections = []

    if staged_diff.strip():
        sections.append(f"=== STAGED CHANGES ===\n{staged_diff}")

    if unstaged_diff.strip():
        sections.append(f"=== UNSTAGED CHANGES ===\n{unstaged_diff}")

    if untracked_diff.strip():
        sections.append(f"=== UNTRACKED FILES ===\n{untracked_diff}")

    return "\n\n".join(sections)
