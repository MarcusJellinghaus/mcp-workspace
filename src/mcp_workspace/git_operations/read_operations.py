"""Read-only git operations: log, diff, status, merge-base, and more.

Thin wrappers around GitPython that validate arguments against
security allowlists, inject safety flags, and apply output
filtering/truncation.  The unified :func:`git` dispatcher routes
to all 11 supported sub-commands.
"""

import logging
from pathlib import Path
from typing import Optional

from git.exc import GitCommandError

from .arg_validation import (
    _SUPPORTS_PATHSPEC,
    split_args_pathspec,
    validate_args,
    validate_branch_has_read_flag,
)
from .compact_diffs import render_compact_diff
from .core import safe_repo_context
from .output_filtering import filter_diff_output, filter_log_output, truncate_output

logger = logging.getLogger(__name__)

# Hardcoded safety flags — defense-in-depth against external program execution
_SAFETY_FLAGS: list[str] = ["--no-ext-diff", "--no-textconv"]


def _run_simple_command(
    git_method: str,
    project_dir: Path,
    command: str,
    args: list[str],
    pathspec: Optional[list[str]],
    max_lines: int,
    no_output_message: str = "No output.",
    use_safety_flags: bool = True,
) -> str:
    """Run a simple git command with validation, safety flags, and truncation.

    Generic helper for commands that follow the validate→execute→truncate
    pattern (fetch, rev_parse, ls_tree, ls_files, ls_remote).

    Args:
        git_method: GitPython method name (e.g. ``"fetch"``, ``"ls_tree"``).
        project_dir: Path to the git repository.
        command: Git sub-command name for allowlist lookup.
        args: CLI arguments (validated against allowlist).
        pathspec: Optional file paths appended after ``--``.
        max_lines: Maximum output lines before truncation.
        no_output_message: Message returned when output is empty.
        use_safety_flags: Inject ``--no-ext-diff --no-textconv`` flags.

    Returns:
        Command output (truncated) or *no_output_message*.

    Raises:
        ValueError: If any flag in *args* is not in the allowlist.
    """
    args, pathspec = split_args_pathspec(command, args, pathspec)
    validate_args(command, args)

    cmd_args = (list(_SAFETY_FLAGS) if use_safety_flags else []) + args
    if pathspec:
        cmd_args += ["--"] + pathspec

    with safe_repo_context(project_dir) as repo:
        output: str = getattr(repo.git, git_method)(*cmd_args)

    if not output:
        return no_output_message

    return truncate_output(output, max_lines)


def git_log(
    project_dir: Path,
    args: Optional[list[str]] = None,
    pathspec: Optional[list[str]] = None,
    search: Optional[str] = None,
    max_lines: int = 50,
) -> str:
    """Run ``git log`` with validated arguments.

    Args:
        project_dir: Path to the git repository.
        args: Optional CLI flags (validated against allowlist).
        pathspec: Optional file paths to restrict log scope.
        search: Optional regex to filter output (case-insensitive).
        max_lines: Maximum output lines before truncation.

    Returns:
        Filtered/truncated log output, or a descriptive message.

    Raises:
        ValueError: If any flag in *args* is not in the allowlist.
    """
    safe_args = args or []
    safe_args, pathspec = split_args_pathspec("log", safe_args, pathspec)
    validate_args("log", safe_args)

    cmd_args = list(_SAFETY_FLAGS) + safe_args
    if pathspec:
        cmd_args += ["--"] + pathspec

    with safe_repo_context(project_dir) as repo:
        try:
            output: str = repo.git.log(*cmd_args)
        except GitCommandError as exc:
            if "does not have any commits yet" in str(exc):
                return "No commits found."
            raise

    if not output:
        return "No commits found."

    if search:
        output = filter_log_output(output, search)

    return truncate_output(output, max_lines)


def git_diff(
    project_dir: Path,
    args: Optional[list[str]] = None,
    pathspec: Optional[list[str]] = None,
    search: Optional[str] = None,
    context: int = 3,
    max_lines: int = 100,
    compact: bool = True,
) -> str:
    """Run ``git diff`` with validated arguments.

    Args:
        project_dir: Path to the git repository.
        args: Optional CLI flags (validated against allowlist).
        pathspec: Optional file paths to restrict diff scope.
        search: Optional regex to filter output (case-insensitive).
        context: Lines of context around search matches.
        max_lines: Maximum output lines before truncation.
        compact: If True, apply compact diff rendering (default).

    Returns:
        Filtered/truncated diff output, or a descriptive message.

    Raises:
        ValueError: If any flag in *args* is not in the allowlist.
    """
    user_args = args or []
    user_args, pathspec = split_args_pathspec("diff", user_args, pathspec)
    validate_args("diff", user_args)

    with safe_repo_context(project_dir) as repo:
        if compact:
            # Strip color-related args; --color-words is incompatible with
            # ANSI-based move detection used by compact mode.
            final_args = [a for a in user_args if not a.startswith("--color")]
            # Inject move/copy detection flags
            final_args = ["-M", "-C90%"] + final_args
            base_args = list(_SAFETY_FLAGS) + final_args
            if pathspec:
                base_args += ["--"] + pathspec

            plain: str = repo.git.diff(*base_args)
            if not plain:
                return "No changes found"

            ansi: str = repo.git.diff(
                "--color=always", "--color-moved=dimmed-zebra", *base_args
            )
            output = render_compact_diff(plain, ansi)

            # Add stats header if compaction reduced line count
            plain_count = len(plain.splitlines())
            compact_count = len(output.splitlines()) if output else 0
            if output and compact_count < plain_count:
                pct = round((1 - compact_count / plain_count) * 100)
                suppressed = plain_count - compact_count
                header = (
                    f"# Compact diff: {plain_count} → {compact_count} lines "
                    f"({pct}% reduction, {suppressed} lines suppressed)"
                )
                output = header + "\n" + output
        else:
            cmd_args = list(_SAFETY_FLAGS) + user_args
            if pathspec:
                cmd_args += ["--"] + pathspec
            output = repo.git.diff(*cmd_args)

    if not output:
        return "No changes found"

    if search:
        output = filter_diff_output(output, search, context)

    return truncate_output(output, max_lines)


def git_status(
    project_dir: Path,
    args: Optional[list[str]] = None,
    max_lines: int = 200,
    pathspec: Optional[list[str]] = None,
) -> str:
    """Run ``git status`` with validated arguments.

    Args:
        project_dir: Path to the git repository.
        args: Optional CLI flags (validated against allowlist).
        max_lines: Maximum output lines before truncation.
        pathspec: Optional file paths to restrict scope.

    Returns:
        Status output, or a descriptive message if clean.

    Raises:
        ValueError: If any flag in *args* is not in the allowlist.
    """
    safe_args = args or []
    safe_args, pathspec = split_args_pathspec("status", safe_args, pathspec)
    validate_args("status", safe_args)

    cmd_args = list(safe_args)
    if pathspec:
        cmd_args += ["--"] + pathspec

    with safe_repo_context(project_dir) as repo:
        output: str = repo.git.status(*cmd_args)

    if not output:
        return "No changes found"

    return truncate_output(output, max_lines)


def git_merge_base(
    project_dir: Path,
    args: Optional[list[str]] = None,
) -> str:
    """Run ``git merge-base`` with validated arguments.

    Args:
        project_dir: Path to the git repository.
        args: Optional CLI flags and refs (validated against allowlist).

    Returns:
        Merge-base SHA, ``"true"``/``"false"`` for ``--is-ancestor``,
        or a descriptive message.

    Raises:
        ValueError: If any flag in *args* is not in the allowlist.
    """
    safe_args = args or []
    validate_args("merge_base", safe_args)

    with safe_repo_context(project_dir) as repo:
        try:
            output: str = repo.git.merge_base(*safe_args)
        except GitCommandError as exc:
            # --is-ancestor: exit code 1 means "not ancestor"
            if "--is-ancestor" in safe_args and exc.status == 1:
                return "false"
            raise

    # --is-ancestor with exit code 0 means "is ancestor" (no stdout)
    if "--is-ancestor" in safe_args:
        return "true"

    if not output:
        return "No common ancestor found"

    return output


def git_show(
    project_dir: Path,
    args: Optional[list[str]] = None,
    pathspec: Optional[list[str]] = None,
    search: Optional[str] = None,
    context: int = 3,
    max_lines: int = 100,
    compact: bool = True,
) -> str:
    """Run ``git show`` with validated arguments.

    Supports compact diff rendering (like ``git_diff``) by default.
    When a colon pattern is detected (e.g. ``HEAD:file.txt``), compact
    rendering is skipped because the output is file content, not a diff.

    Args:
        project_dir: Path to the git repository.
        args: Optional CLI flags (validated against allowlist).
        pathspec: Optional file paths to restrict scope.
        search: Optional regex to filter output (case-insensitive).
        context: Lines of context around search matches.
        max_lines: Maximum output lines before truncation.
        compact: If True, apply compact diff rendering (default).

    Returns:
        Filtered/truncated show output, or a descriptive message.

    Raises:
        ValueError: If any flag in *args* is not in the allowlist.
    """
    user_args = args or []
    user_args, pathspec = split_args_pathspec("show", user_args, pathspec)
    validate_args("show", user_args)

    # Detect colon pattern (e.g. HEAD:README.md) — file content, not diff
    has_colon = any(":" in a and not a.startswith("-") for a in user_args)

    with safe_repo_context(project_dir) as repo:
        if compact and not has_colon:
            final_args = [a for a in user_args if not a.startswith("--color")]
            final_args = ["-M", "-C90%"] + final_args
            base_args = list(_SAFETY_FLAGS) + final_args
            if pathspec:
                base_args += ["--"] + pathspec

            plain: str = repo.git.show(*base_args)
            if not plain:
                return "No output."

            ansi: str = repo.git.show(
                "--color=always", "--color-moved=dimmed-zebra", *base_args
            )
            output = render_compact_diff(plain, ansi)
            if not output:
                output = plain  # Fall back when no diff hunks (e.g. --no-patch)

            plain_count = len(plain.splitlines())
            compact_count = len(output.splitlines()) if output else 0
            if output and compact_count < plain_count:
                pct = round((1 - compact_count / plain_count) * 100)
                suppressed = plain_count - compact_count
                header = (
                    f"# Compact diff: {plain_count} → {compact_count} lines "
                    f"({pct}% reduction, {suppressed} lines suppressed)"
                )
                output = header + "\n" + output
        else:
            cmd_args = list(_SAFETY_FLAGS) + user_args
            if pathspec:
                cmd_args += ["--"] + pathspec
            output = repo.git.show(*cmd_args)

    if not output:
        return "No output."

    if search:
        output = filter_diff_output(output, search, context)

    return truncate_output(output, max_lines)


def git_branch(
    project_dir: Path,
    args: Optional[list[str]] = None,
    max_lines: int = 100,
) -> str:
    """Run ``git branch`` with validated arguments (read-only only).

    Requires at least one read-only flag to prevent accidental branch
    creation.

    Args:
        project_dir: Path to the git repository.
        args: Optional CLI flags (validated against allowlist).
        max_lines: Maximum output lines before truncation.

    Returns:
        Branch listing or current branch name.

    Raises:
        ValueError: If any flag is not allowed or no read-only flag present.
    """
    safe_args = args or []
    validate_args("branch", safe_args)
    validate_branch_has_read_flag(safe_args)

    with safe_repo_context(project_dir) as repo:
        output: str = repo.git.branch(*safe_args)

    if not output:
        return "No branches found."

    return truncate_output(output, max_lines)


# ---------------------------------------------------------------------------
# Unified git() dispatcher
# ---------------------------------------------------------------------------

_DEFAULT_MAX_LINES: dict[str, int] = {
    "log": 50,
    "diff": 100,
    "status": 200,
}

_SUPPORTS_SEARCH: frozenset[str] = frozenset({"log", "diff", "show"})
_SUPPORTS_COMPACT: frozenset[str] = frozenset({"diff", "show"})
_SUPPORTS_CONTEXT: frozenset[str] = frozenset({"diff", "show"})


def git(
    command: str,
    project_dir: Path,
    args: Optional[list[str]] = None,
    pathspec: Optional[list[str]] = None,
    search: Optional[str] = None,
    context: int = 3,
    max_lines: Optional[int] = None,
    compact: bool = True,
) -> str:
    """Unified dispatcher for read-only git commands.

    Routes *command* to the appropriate handler function, applying
    per-command ``max_lines`` defaults and generating soft warnings
    when non-default parameter values are passed for commands that
    do not support them.

    Args:
        command: Git sub-command name (e.g. ``"log"``, ``"diff"``).
        project_dir: Path to the git repository.
        args: Optional CLI flags (validated per command).
        pathspec: Optional file paths appended after ``--``.
        search: Optional regex to filter output.
        context: Lines of context around search matches.
        max_lines: Maximum output lines.  Per-command default when *None*.
        compact: If True, apply compact diff rendering where supported.

    Returns:
        Command output with optional warning prefix.

    Raises:
        ValueError: If *command* is not recognised.
    """
    resolved_max_lines = (
        max_lines if max_lines is not None else _DEFAULT_MAX_LINES.get(command, 100)
    )
    safe_args = args  # keep None propagation to individual handlers
    list_args = args or []  # coerced to list for _run_simple_command

    # --- soft warnings for unsupported non-default params ----------------
    warnings: list[str] = []
    if not compact and command not in _SUPPORTS_COMPACT:
        warnings.append(
            f"⚠ 'compact' is not supported for git {command} and was ignored."
        )
    if context != 3 and command not in _SUPPORTS_CONTEXT:
        warnings.append(
            f"⚠ 'context' is not supported for git {command} and was ignored."
        )
    if search is not None and command not in _SUPPORTS_SEARCH:
        warnings.append(
            f"⚠ 'search' is not supported for git {command} and was ignored."
        )
    if pathspec is not None and command not in _SUPPORTS_PATHSPEC:
        warnings.append(
            f"⚠ 'pathspec' is not supported for git {command} and was ignored."
        )

    # --- dispatch --------------------------------------------------------
    handlers: dict[str, object] = {
        "log": lambda: git_log(
            project_dir, safe_args, pathspec, search, resolved_max_lines
        ),
        "diff": lambda: git_diff(
            project_dir,
            safe_args,
            pathspec,
            search,
            context,
            resolved_max_lines,
            compact,
        ),
        "status": lambda: git_status(
            project_dir, safe_args, resolved_max_lines, pathspec
        ),
        "merge_base": lambda: git_merge_base(project_dir, safe_args),
        "show": lambda: git_show(
            project_dir,
            safe_args,
            pathspec,
            search,
            context,
            resolved_max_lines,
            compact,
        ),
        "branch": lambda: git_branch(project_dir, safe_args, resolved_max_lines),
        "fetch": lambda: _run_simple_command(
            "fetch",
            project_dir,
            "fetch",
            list_args,
            None,
            resolved_max_lines,
            "Fetch complete (no output).",
            use_safety_flags=False,
        ),
        "rev_parse": lambda: _run_simple_command(
            "rev_parse",
            project_dir,
            "rev_parse",
            list_args,
            None,
            resolved_max_lines,
            use_safety_flags=False,
        ),
        "ls_tree": lambda: _run_simple_command(
            "ls_tree",
            project_dir,
            "ls_tree",
            list_args,
            pathspec,
            resolved_max_lines,
            use_safety_flags=False,
        ),
        "ls_files": lambda: _run_simple_command(
            "ls_files",
            project_dir,
            "ls_files",
            list_args,
            pathspec,
            resolved_max_lines,
            use_safety_flags=False,
        ),
        "ls_remote": lambda: _run_simple_command(
            "ls_remote",
            project_dir,
            "ls_remote",
            list_args,
            None,
            resolved_max_lines,
            use_safety_flags=False,
        ),
    }

    handler = handlers.get(command)
    if handler is None:
        raise ValueError(f"Unknown git command: '{command}'")

    output: str = handler()  # type: ignore[operator]

    if warnings:
        prefix = "\n".join(warnings) + "\n\n"
        return prefix + output

    return output
