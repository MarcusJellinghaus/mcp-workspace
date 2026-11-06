"""Path spelling rules shared by the file tools and the git tool."""

import re

_SEPARATORS = re.compile(r"[\\/]")


def _canonical_component(name: str) -> str:
    """Reduce a path component to the name Windows would open for it.

    Windows ignores trailing dots and spaces and treats ``name:stream`` as a
    stream of ``name``. Elsewhere these are distinct names, but none of them is
    a name a project needs alongside the original, so the rule is the same on
    every OS and can be tested on any of them.

    Args:
        name: A single path component.

    Returns:
        The component without a stream suffix or trailing dots and spaces; the
        component unchanged when nothing else would remain.
    """
    return name.split(":", 1)[0].rstrip(". ") or name


def canonical_spelling(path: str) -> str:
    """Rewrite a path to forward slashes with canonical components.

    Returns:
        The path with each component reduced by ``_canonical_component``.
    """
    return "/".join(_canonical_component(part) for part in _SEPARATORS.split(path))


def is_path_in_git_dir(path: str) -> bool:
    """Check whether a path names a ``.git`` entry or anything below one.

    Compares casefolded canonical components, so it also covers the spellings a
    case-insensitive filesystem or Windows resolves to the same entry. Names
    that only start with ``.git``, such as ``.github``, do not match.

    Returns:
        True if any component of the path is a spelling of ``.git``.
    """
    return any(
        _canonical_component(part).casefold() == ".git"
        for part in _SEPARATORS.split(path)
    )
