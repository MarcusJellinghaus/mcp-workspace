"""Per-command argument validation for read-only git operations.

Validates CLI flags against allowlists to prevent injection of
dangerous flags (e.g. --exec, --output).
"""

import re
from pathlib import PureWindowsPath

from mcp_workspace.utils.git_paths import is_path_in_git_dir

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
        "--numstat",
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

CHECK_IGNORE_ALLOWED_FLAGS: frozenset[str] = frozenset(
    {"-v", "--verbose", "-n", "--non-matching", "--no-index"}
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
    "check_ignore": CHECK_IGNORE_ALLOWED_FLAGS,
}

_SUPPORTS_PATHSPEC: frozenset[str] = frozenset(
    {"log", "diff", "show", "status", "ls_tree", "ls_files", "check_ignore"}
)

_REMOTE_COMMANDS: frozenset[str] = frozenset({"fetch", "ls_remote"})

_PATHSPEC_MAGIC = re.compile(r"^:(\([^)]*\)|[!^/]*)")
_PATH_SEPARATORS = re.compile(r"[\\/]")

_COUNT = re.compile(r"[0-9]*")
_SIMILARITY = re.compile(r"[0-9]*\.?[0-9]*%?")

# Short flags that take a value in the same argument, with the value's format.
# Every other short flag is a switch, and a cluster of them must all be listed.
_ATTACHED_VALUE_FLAGS: dict[str, dict[str, re.Pattern[str]]] = {
    "log": {"-n": _COUNT, "-U": _COUNT},
    "diff": {"-U": _COUNT, "-M": _SIMILARITY, "-C": _SIMILARITY},
    "show": {"-U": _COUNT, "-M": _SIMILARITY, "-C": _SIMILARITY},
    "status": {"-u": re.compile(r"(no|normal|all)?")},
}

# Flags that git lets take their value from the next argument, which is then
# not a ref or a path.
_SEPARATE_VALUE_FLAGS: dict[str, frozenset[str]] = {
    "log": frozenset(
        {
            "-n",
            "--max-count",
            "--skip",
            "--author",
            "--committer",
            "--grep",
            "--since",
            "--until",
            "--after",
            "--before",
        }
    ),
    "branch": frozenset({"--contains", "--merged", "--no-merged", "--sort"}),
    "ls_files": frozenset({"--exclude"}),
    "ls_remote": frozenset({"--sort"}),
    "fetch": frozenset({"--depth", "--shallow-since", "--shallow-exclude"}),
}

# With one of these, git branch treats other arguments as patterns to list.
# Without one, it treats them as names to create.
_BRANCH_LIST_MODE_FLAGS: frozenset[str] = frozenset(
    {"--list", "--contains", "--merged", "--no-merged"}
)


def _short_cluster_allowed(command: str, cluster: str) -> bool:
    """Check a short flag argument one letter at a time.

    Args:
        command: Git sub-command name.
        cluster: The argument without its leading ``-``, e.g. ``vv`` or ``n5``.

    Returns:
        True if every letter is an allowed flag, and any value attached to a
        value-taking flag has the expected format.
    """
    allowlist = _ALLOWLISTS[command]
    attached = _ATTACHED_VALUE_FLAGS.get(command, {})
    for index, letter in enumerate(cluster):
        flag = f"-{letter}"
        if flag not in allowlist:
            return False
        if flag in attached:
            return attached[flag].fullmatch(cluster[index + 1 :]) is not None
    return bool(cluster)


def _is_allowed_flag(command: str, arg: str) -> bool:
    """Check one flag argument against the command's allowlist.

    Args:
        command: Git sub-command name.
        arg: An argument starting with ``-``.

    Returns:
        True if the flag is allowed.
    """
    allowlist = _ALLOWLISTS[command]
    if arg.startswith("--"):
        return arg.split("=", 1)[0] in allowlist
    if arg[1:].isascii() and arg[1:].isdigit():
        return "-<int>" in allowlist
    return _short_cluster_allowed(command, arg[1:])


def positional_args(command: str, args: list[str]) -> list[str]:
    """Return the arguments that are neither flags nor the value of a flag.

    Args:
        command: Git sub-command name.
        args: CLI arguments, without any ``--`` separator.

    Returns:
        The refs, paths or other operands in *args*, in order.
    """
    separate_value_flags = _SEPARATE_VALUE_FLAGS.get(command, frozenset())
    positional: list[str] = []
    previous_takes_value = False
    for arg in args:
        if arg.startswith("-"):
            previous_takes_value = arg in separate_value_flags
            continue
        if not previous_takes_value:
            positional.append(arg)
        previous_takes_value = False
    return positional


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


def _leaves_repository(token: str) -> bool:
    """Check whether a path, pathspec or ``<rev>:<path>`` reaches outside the repo.

    The check is on the spelling only, which is what git itself uses to decide
    whether a path is inside the repository. An absolute path is always
    refused: git compares it with its own spelling of the repository path, so
    one that Python resolves inside the project can still be outside for git.

    Args:
        token: Argument or pathspec entry to check.

    Returns:
        True if the token is empty, absolute, has a drive, has a ``..``
        component, or names a ``.git`` entry.
    """
    if not token or PureWindowsPath(token).drive:
        return True
    for segment in _PATHSPEC_MAGIC.sub("", token, count=1).split(":"):
        if segment.startswith(("/", "\\")) or ".." in _PATH_SEPARATORS.split(segment):
            return True
        if is_path_in_git_dir(segment):
            return True
    return False


def validate_path_args(
    command: str, args: list[str], pathspec: list[str] | None
) -> None:
    """Refuse operands and pathspec entries that reach outside the repository.

    This also keeps ``git diff`` from comparing plain files: with two paths of
    which one is outside the repository, git does that even when they follow
    ``--``. Commands that take no paths are not checked.

    Args:
        command: Git sub-command name.
        args: CLI arguments, without any ``--`` separator.
        pathspec: Paths that follow ``--``.

    Raises:
        ValueError: If an operand or pathspec entry leaves the repository.
    """
    if command not in _SUPPORTS_PATHSPEC:
        return
    for token in [*positional_args(command, args), *(pathspec or [])]:
        if _leaves_repository(token):
            raise ValueError(
                f"git {command}: '{token}' is refused. Paths must stay inside the "
                "repository and be relative to it, and cannot name a .git entry."
            )


def validate_remote_args(command: str, args: list[str], remote_names: set[str]) -> None:
    """Refuse fetch and ls-remote operands other than configured remote names.

    Fetch refspecs may name what to fetch but not where to store it, so a fetch
    only updates remote-tracking refs and ``FETCH_HEAD``. Commands other than
    fetch and ls-remote are not checked.

    Args:
        command: Git sub-command name.
        args: CLI arguments.
        remote_names: Names of the remotes configured in the repository.

    Raises:
        ValueError: If the first operand is not a configured remote, or a fetch
            refspec could update a local ref.
    """
    if command not in _REMOTE_COMMANDS:
        return
    operands = positional_args(command, args)
    if not operands:
        return
    if operands[0] not in remote_names:
        raise ValueError(
            f"git {command}: '{operands[0]}' is refused. Only a configured remote "
            "name is accepted, not a URL or a path."
        )
    if command == "fetch":
        for refspec in operands[1:]:
            if ":" in refspec or refspec.startswith("+") or refspec == "tag":
                raise ValueError(
                    f"git fetch: refspec '{refspec}' is refused. Name the ref to "
                    "fetch, without a destination or a forced update."
                )


def validate_branch_has_read_flag(args: list[str]) -> None:
    """Raise ValueError unless the branch args can only list.

    Requires at least one allowed flag. A name alongside the flag is accepted
    only with a flag that puts git branch in list mode, because any other
    combination (``-v <name>``, ``--sort=x <name>``) creates a branch.

    Args:
        args: List of CLI arguments to check.

    Raises:
        ValueError: If no read-only flag is found, or a name could create a
            branch.
    """
    flags = [arg for arg in args if arg.startswith("-")]
    in_list_mode = any(
        flag.split("=", 1)[0] in _BRANCH_LIST_MODE_FLAGS for flag in flags
    )
    if not any(_is_allowed_flag("branch", flag) for flag in flags) or (
        positional_args("branch", args) and not in_list_mode
    ):
        msg = "git branch requires a read-only flag (e.g. --list, -a, --show-current)"
        raise ValueError(msg)


def validate_args(command: str, args: list[str]) -> None:
    """Validate args against per-command allowlist.

    Only flags (starting with ``-``) are checked here. Long flags match on
    the part before any ``=``. Short flags are checked letter by letter, and
    only flags that take a value may have one attached (``-n5``, ``-U3``).

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

    for arg in args:
        if not arg.startswith("-") or _is_allowed_flag(command, arg):
            continue

        msg = (
            f"Flag '{arg}' is not in the security allowlist for git_{command}. "
            f"If this flag should be supported, open an issue at "
            f"https://github.com/MarcusJellinghaus/mcp-workspace/issues"
        )
        raise ValueError(msg)
