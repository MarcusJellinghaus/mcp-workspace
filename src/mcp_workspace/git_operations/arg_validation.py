"""Per-command argument validation for read-only git operations.

Validates CLI flags against allowlists to prevent injection of
dangerous flags (e.g. --exec, --output). Non-flag arguments (refs,
SHAs, ranges) pass through — git validates them.
"""

LOG_ALLOWED_FLAGS: frozenset[str] = frozenset(
    {
        "--oneline",
        "--format",
        "--pretty",
        "--abbrev-commit",
        "--no-abbrev-commit",
        "--date",
        "--author",
        "--committer",
        "--grep",
        "--invert-grep",
        "--all-match",
        "--since",
        "--until",
        "--after",
        "--before",
        "--all",
        "--branches",
        "--tags",
        "--remotes",
        "--merges",
        "--no-merges",
        "--first-parent",
        "--max-count",
        "-n",
        "--skip",
        "--reverse",
        "--stat",
        "--shortstat",
        "--name-only",
        "--name-status",
        "--no-patch",
        "--patch",
        "-p",
        "--graph",
        "--decorate",
        "--no-decorate",
        "--follow",
        "--diff-filter",
        "--unified",
        "-U",
        "--no-ext-diff",
        "--no-textconv",
        "-<int>",
    }
)

DIFF_ALLOWED_FLAGS: frozenset[str] = frozenset(
    {
        "--staged",
        "--cached",
        "--name-only",
        "--name-status",
        "--stat",
        "--shortstat",
        "--numstat",
        "--no-patch",
        "--patch",
        "-p",
        "--unified",
        "-U",
        "--diff-filter",
        "--no-prefix",
        "--word-diff",
        "--word-diff-regex",
        "--color-words",
        "--ignore-space-change",
        "-b",
        "--ignore-all-space",
        "-w",
        "--ignore-blank-lines",
        "--no-ext-diff",
        "--no-textconv",
        "--minimal",
        "--patience",
        "--histogram",
        "--diff-algorithm",
        "-M",
        "-C",
        "--find-renames",
        "--find-copies",
        "--relative",
        "-<int>",
    }
)

STATUS_ALLOWED_FLAGS: frozenset[str] = frozenset(
    {
        "--short",
        "-s",
        "--long",
        "--branch",
        "-b",
        "--porcelain",
        "--verbose",
        "-v",
        "--untracked-files",
        "-u",
        "--ignored",
        "--ignore-submodules",
        "--show-stash",
        "--ahead-behind",
        "--no-ahead-behind",
        "--renames",
        "--no-renames",
        "--find-renames",
        "-z",
        "--null",
        "--column",
        "--no-column",
    }
)

MERGE_BASE_ALLOWED_FLAGS: frozenset[str] = frozenset(
    {
        "--all",
        "-a",
        "--octopus",
        "--independent",
        "--is-ancestor",
        "--fork-point",
    }
)

FETCH_ALLOWED_FLAGS: frozenset[str] = frozenset(
    {
        "--all",
        "--prune",
        "--tags",
        "--no-tags",
        "--depth",
        "--shallow-since",
        "--shallow-exclude",
        "--force",
        "-f",
        "--verbose",
        "-v",
        "--quiet",
        "-q",
        "--dry-run",
        "-n",
    }
)

SHOW_ALLOWED_FLAGS: frozenset[str] = frozenset(
    {
        "--format",
        "--pretty",
        "--abbrev-commit",
        "--no-abbrev-commit",
        "--date",
        "--stat",
        "--shortstat",
        "--name-only",
        "--name-status",
        "--no-patch",
        "--patch",
        "-p",
        "--unified",
        "-U",
        "--diff-filter",
        "--no-ext-diff",
        "--no-textconv",
        "--oneline",
        "-M",
        "-C",
        "--find-renames",
        "--find-copies",
        "--color-words",
        "--word-diff",
        "-<int>",
    }
)

BRANCH_ALLOWED_FLAGS: frozenset[str] = frozenset(
    {
        "--list",
        "-a",
        "-r",
        "--contains",
        "--merged",
        "--no-merged",
        "--sort",
        "-v",
        "--show-current",
        "--no-color",
    }
)

REV_PARSE_ALLOWED_FLAGS: frozenset[str] = frozenset(
    {
        "--abbrev-ref",
        "--short",
        "--verify",
        "--symbolic",
        "--symbolic-full-name",
        "--show-toplevel",
        "--show-cdup",
        "--git-dir",
        "--is-inside-work-tree",
        "--is-bare-repository",
        "--show-prefix",
        "--show-superproject-working-tree",
    }
)

LS_TREE_ALLOWED_FLAGS: frozenset[str] = frozenset(
    {
        "-r",
        "-t",
        "-d",
        "--name-only",
        "--name-status",
        "--long",
        "-l",
        "--abbrev",
        "--full-name",
        "--full-tree",
    }
)

LS_FILES_ALLOWED_FLAGS: frozenset[str] = frozenset(
    {
        "--cached",
        "-c",
        "--deleted",
        "-d",
        "--modified",
        "-m",
        "--others",
        "-o",
        "--ignored",
        "-i",
        "--stage",
        "-s",
        "--unmerged",
        "-u",
        "--exclude",
        "--exclude-standard",
        "--error-unmatch",
        "--full-name",
        "--abbrev",
    }
)

LS_REMOTE_ALLOWED_FLAGS: frozenset[str] = frozenset(
    {
        "--heads",
        "--tags",
        "--refs",
        "--quiet",
        "-q",
        "--sort",
        "--get-url",
    }
)

_ALLOWLISTS: dict[str, frozenset[str]] = {
    "log": LOG_ALLOWED_FLAGS,
    "diff": DIFF_ALLOWED_FLAGS,
    "status": STATUS_ALLOWED_FLAGS,
    "merge_base": MERGE_BASE_ALLOWED_FLAGS,
    "fetch": FETCH_ALLOWED_FLAGS,
    "show": SHOW_ALLOWED_FLAGS,
    "branch": BRANCH_ALLOWED_FLAGS,
    "rev_parse": REV_PARSE_ALLOWED_FLAGS,
    "ls_tree": LS_TREE_ALLOWED_FLAGS,
    "ls_files": LS_FILES_ALLOWED_FLAGS,
    "ls_remote": LS_REMOTE_ALLOWED_FLAGS,
}

_SUPPORTS_PATHSPEC: frozenset[str] = frozenset(
    {"log", "diff", "show", "status", "ls_tree", "ls_files"}
)


def split_args_pathspec(
    command: str,
    args: list[str],
    pathspec: list[str] | None,
) -> tuple[list[str], list[str] | None]:
    """Split args on '--' for pathspec commands; route tail into pathspec.

    Returns (args, pathspec) unchanged for commands not in
    _SUPPORTS_PATHSPEC or when '--' is absent. For pathspec commands,
    splits on the first '--', routes the tail into pathspec, and
    raises ValueError on multi-'--' or conflict-with-explicit-pathspec.

    Args:
        command: Git sub-command name (e.g. "log", "diff").
        args: List of CLI arguments, possibly containing '--'.
        pathspec: Optional explicit pathspec parameter.

    Returns:
        Tuple of (args, pathspec) after splitting.

    Raises:
        ValueError: If multiple '--' tokens are present or the tail
            conflicts with an explicit pathspec parameter.
    """
    if command not in _SUPPORTS_PATHSPEC or "--" not in args:
        return args, pathspec
    idx = args.index("--")
    head, tail = args[:idx], args[idx + 1 :]
    if "--" in tail:
        raise ValueError("Multiple '--' tokens in args are not allowed.")
    if pathspec is not None and tail:
        raise ValueError(
            "Specify paths via either '--' in args or the 'pathspec' "
            "parameter, not both."
        )
    return head, (tail or pathspec)


def validate_branch_has_read_flag(args: list[str]) -> None:
    """Raise ValueError if no read-only flag is present in branch args.

    Checks against BRANCH_ALLOWED_FLAGS — every allowed flag is a read-only
    flag, so any allowed flag proves read-only intent.
    Prevents bare ``git branch <name>`` from creating branches.

    Args:
        args: List of CLI arguments to check.

    Raises:
        ValueError: If no read-only flag is found.
    """
    for arg in args:
        if not arg.startswith("-"):
            continue
        if arg in BRANCH_ALLOWED_FLAGS:
            return
        if "=" in arg:
            prefix = arg.split("=", 1)[0]
            if prefix in BRANCH_ALLOWED_FLAGS:
                return
    msg = "git branch requires a read-only flag (e.g. --list, -a, --show-current)"
    raise ValueError(msg)


def validate_args(command: str, args: list[str]) -> None:
    """Validate args against per-command allowlist.

    Non-flag arguments (refs, SHAs, ranges) pass through without
    validation — git validates them. Only flags (starting with ``-``)
    are checked.

    Args:
        command: Git sub-command name (e.g. "log", "diff").
        args: List of CLI arguments to validate.

    Raises:
        ValueError: If ``--`` is in args, command is unknown, or a
            flag is not in the allowlist.
    """
    if "--" in args:
        raise ValueError(f"git {command} does not accept '--'")

    if command not in _ALLOWLISTS:
        msg = f"Unknown command: '{command}'"
        raise ValueError(msg)

    allowlist = _ALLOWLISTS[command]

    for arg in args:
        if not arg.startswith("-"):
            continue

        # Exact match
        if arg in allowlist:
            continue

        # --flag=value: check prefix before "="
        if "=" in arg:
            prefix = arg.split("=", 1)[0]
            if prefix in allowlist:
                continue

        # Short flag with attached value (e.g. -n5): check first 2 chars
        if len(arg) > 2 and not arg.startswith("--"):
            short_prefix = arg[:2]
            if short_prefix in allowlist:
                continue

        # Bare numeric flag (e.g. -10): allowed if command opts in via "-<int>"
        if not arg.startswith("--") and arg[1:].isdigit() and "-<int>" in allowlist:
            continue

        msg = (
            f"Flag '{arg}' is not in the security allowlist for git_{command}. "
            f"If this flag should be supported, open an issue at "
            f"https://github.com/MarcusJellinghaus/mcp-workspace/issues"
        )
        raise ValueError(msg)
