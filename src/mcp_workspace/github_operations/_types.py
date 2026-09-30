"""Shared types for the verification module.

Extracted to break the circular import between ``verification.py`` and
``_permission_probes.py`` — both need ``CheckResult``, but ``verification.py``
also imports ``run_permission_probes`` from ``_permission_probes``.
"""

from typing import Literal, NotRequired, TypedDict


class CheckResult(TypedDict):
    """Result of a single verification check.

    ``ok`` is ``True`` for a verified positive, ``False`` for a verified
    negative, and ``None`` when the check could not be verified.
    """

    ok: bool | None
    value: str
    severity: Literal["error", "warning"]
    error: NotRequired[str]
    install_hint: NotRequired[str]
    token_source: NotRequired[Literal["env", "config"]]
    token_fingerprint: NotRequired[str]
