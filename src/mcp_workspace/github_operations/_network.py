"""Network diagnostics for GitHub API connectivity failures.

When a GitHub API call finally fails because the API host is unreachable, emit a
single WARNING line that reveals the resolved API URL, the Python proxy
configuration (host:port), PAC presence and a fix hint — once per process.

This module **owns** the ``requests.exceptions`` gating: call sites only need one
unconditional ``maybe_log_network_diagnostics(exc, api_base_url)`` line in their
existing generic ``except Exception`` branch and do **not** import ``requests``.
"""

import logging
import os
import socket
import sys
from urllib.parse import urlsplit
from urllib.request import getproxies, proxy_bypass

from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import Timeout as RequestsTimeout

logger = logging.getLogger(__name__)

# Once-per-process guard for the diagnostics WARNING line.
_LOGGED: bool = False


def _tcp_probe(host: str) -> str:
    """Probe a direct TCP connection to ``host:443`` with a 3s timeout.

    Ignores proxies on purpose — it answers "is the host reachable from this
    Python process at all?". Returns one of ``ok``/``refused``/``timeout``/
    ``dns_error``.

    Note:
        Catch order matters: ``socket.gaierror`` (DNS) is an ``OSError`` subclass
        and must be caught before ``OSError``.
    """
    try:
        socket.create_connection((host, 443), timeout=3).close()
        return "ok"
    except socket.gaierror:
        return "dns_error"
    except (socket.timeout, TimeoutError):
        return "timeout"
    except ConnectionRefusedError:
        return "refused"
    except OSError:
        return "refused"


def _proxy_host_port(url: str) -> str:
    """Reduce a proxy URL to ``host:port``, dropping any ``user:pass@`` prefix."""
    parts = urlsplit(url)
    return f"{parts.hostname}:{parts.port}"


def _read_pac_autoconfig_url() -> str | None:
    """Return ``"present"`` if a Windows PAC AutoConfigURL is configured, else None.

    ``winreg`` is imported lazily inside the win32 branch so a top-level import
    does not break non-Windows platforms at import time.
    """
    if sys.platform != "win32":
        return None
    import winreg  # pylint: disable=import-outside-toplevel

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AutoConfigURL")
        if value:
            return "present"
        return None
    except OSError:
        return None


def _collect_network_diagnostics(api_base_url: str) -> dict[str, str]:
    """Gather network diagnostics for an unreachable GitHub API host.

    Args:
        api_base_url: The API base URL the failing call targeted.

    Returns:
        Mapping with keys ``api_base_url``, ``host`` (API hostname parsed from
        ``api_base_url`` — same value used for the TCP probe), ``python_proxies``
        (comma-joined ``host:port`` or ``"none"``), ``proxy_env`` (comma-joined
        env-var names or ``"none"``), ``pac`` (``"present"``/``"absent"``) and
        ``tcp_probe`` (``ok``/``refused``/``timeout``/``dns_error``).
    """
    host = urlsplit(api_base_url).hostname or ""
    proxies = {
        scheme: _proxy_host_port(url)
        for scheme, url in getproxies().items()
        if scheme in ("http", "https")
    }
    python_proxies = ",".join(proxies.values()) or "none"
    present_names = [
        name
        for name in ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY")
        if name in os.environ or name.lower() in os.environ
    ]
    proxy_env = ",".join(present_names) or "none"
    pac = _read_pac_autoconfig_url() or "absent"
    return {
        "api_base_url": api_base_url,
        "host": host,
        "python_proxies": python_proxies,
        "proxy_env": proxy_env,
        "pac": pac,
        "tcp_probe": _tcp_probe(host),
    }


def has_applicable_proxy(api_base_url: str) -> bool:
    """True if an http/https proxy is configured AND the host is not NO_PROXY-bypassed.

    The direct TCP probe ignores proxies, but ``requests``/PyGithub honour
    ``HTTPS_PROXY``. So an unreachable-host short-circuit must be gated on there
    being *no* applicable proxy — otherwise a user who set ``HTTPS_PROXY`` (the
    tool's own fix hint) would still see a stale "unreachable".

    Args:
        api_base_url: The API base URL whose host the proxy gate applies to.

    Returns:
        True when an http/https proxy is configured and ``NO_PROXY`` does not
        bypass the host parsed from ``api_base_url``; False otherwise.
    """
    proxies = getproxies()
    if not ({"http", "https"} & proxies.keys()):
        return False
    host = urlsplit(api_base_url).hostname or ""
    # proxy_bypass honours NO_PROXY: truthy means the host should bypass proxies.
    return not proxy_bypass(host)


def maybe_log_network_diagnostics(exc: BaseException, api_base_url: str) -> None:
    """Log network diagnostics once if ``exc`` is a connection/timeout error.

    No-ops for any exception that is not a ``requests`` ConnectionError/Timeout,
    and only the first qualifying call in a process emits the WARNING line.

    Args:
        exc: The exception caught at the call site.
        api_base_url: The API base URL the failing call targeted.
    """
    global _LOGGED  # pylint: disable=global-statement
    if not isinstance(exc, (RequestsConnectionError, RequestsTimeout)):
        return
    if _LOGGED:
        return
    diag = _collect_network_diagnostics(api_base_url)
    logger.warning(
        "GitHub API host unreachable: %s ; hint: if your browser uses a PAC "
        "proxy, set HTTPS_PROXY",
        diag,
    )
    _LOGGED = True


def _reset_network_diagnostics_guard() -> None:
    """Reset the once-per-process guard (test-only)."""
    global _LOGGED  # pylint: disable=global-statement
    _LOGGED = False
