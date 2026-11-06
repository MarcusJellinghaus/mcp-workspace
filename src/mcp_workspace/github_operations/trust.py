"""Commenter trust rule for PR/issue feedback shown to agents.

Imports only ``typing`` so it stays cheap to import.
"""

TRUSTED_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


def normalize_author_association(value: object) -> str | None:
    """Return ``value`` if it is a string, else None.

    Args:
        value: Raw ``author_association`` from PyGithub or GraphQL.

    Returns:
        The association string, or None for any non-string value.
    """
    return value if isinstance(value, str) else None


def is_trusted_author(
    login: str | None, association: str | None, trusted: frozenset[str]
) -> bool:
    """Decide whether an author's text may be shown to the agent.

    Args:
        login: GitHub login of the author; None or "" for ghost users.
        association: GitHub ``author_association`` relative to the repo.
        trusted: Lowercased allowlist of logins from ``get_trusted_commenters``.

    Returns:
        True for OWNER/MEMBER/COLLABORATOR or an allowlisted login.
    """
    if association in TRUSTED_ASSOCIATIONS:
        return True
    if not login:
        return False
    return login.lower() in trusted
