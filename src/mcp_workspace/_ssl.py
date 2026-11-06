"""Truststore activation helper.

Activates the OS certificate store via the optional ``truststore`` package so
PyGithub (via ``requests``/``urllib3``) honors corporate-proxy CA bundles.

Library safety: :func:`ensure_truststore` MUST NOT be called at import time.
``truststore.inject_into_ssl()`` is a global monkeypatch on
``ssl.SSLContext``; activation is the application entry point's decision,
not this module's.
"""

import logging

logger = logging.getLogger(__name__)

_activated: bool = False


def ensure_truststore() -> None:
    """Activate ``truststore`` if available, idempotently.

    Safe to call multiple times: subsequent calls are no-ops once activation
    has succeeded. No-op (with a warning) when ``truststore`` cannot be
    imported. Failures during ``inject_into_ssl()`` are logged as warnings
    and swallowed so a corporate-proxy misconfiguration does not crash the
    server -- PyGithub falls back to certifi.
    """
    global _activated  # pylint: disable=global-statement  # once-only activation flag
    if _activated:
        return
    try:
        import truststore  # pylint: disable=import-outside-toplevel
    except ImportError:
        logger.warning("truststore not installed; skipping OS trust-store activation")
        return
    try:
        truststore.inject_into_ssl()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning(
            "truststore.inject_into_ssl() failed: %s; falling back to certifi",
            exc,
        )
        return
    _activated = True
    logger.debug("truststore activated: using OS certificate store")
