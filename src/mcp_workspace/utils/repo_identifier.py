"""Repository identifier with hostname support for GitHub Enterprise.

Provides RepoIdentifier dataclass that handles both github.com and
GitHub Enterprise (GHE) URLs, plus hostname_to_api_base_url() helper.
"""

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def hostname_to_api_base_url(hostname: str) -> str:
    """Convert a git hostname to the corresponding GitHub API base URL.

    Three hostname patterns are recognized (case-insensitive on input;
    GHES fallback preserves original casing in the URL):

    - ``github.com`` -> ``https://api.github.com``
    - ``*.ghe.com`` (GHE Cloud with data residency) ->
      ``https://api.<tenant>.ghe.com``
    - Any other host (GHES / GitHub Enterprise Server) ->
      ``https://<host>/api/v3``

    Args:
        hostname: Git host (e.g., "github.com", "tenant.ghe.com",
            or "ghe.corp.com")

    Returns:
        API base URL for use with PyGithub
    """
    h = hostname.lower()
    if h == "github.com":
        url = "https://api.github.com"
        logger.debug(
            "hostname_to_api_base_url input=%s normalized=%s branch=github.com url=%s",
            hostname,
            h,
            url,
        )
        return url
    if h.endswith(".ghe.com"):
        url = f"https://api.{h}"
        logger.debug(
            "hostname_to_api_base_url input=%s normalized=%s branch=ghe.com url=%s",
            hostname,
            h,
            url,
        )
        return url
    url = f"https://{hostname}/api/v3"
    logger.debug(
        "hostname_to_api_base_url input=%s normalized=%s branch=ghes-fallback url=%s",
        hostname,
        h,
        url,
    )
    return url


@dataclass
class RepoIdentifier:
    """Repository identifier with owner, repo name, and hostname.

    Provides a single source of truth for repository identifier parsing.
    Use factory methods to create instances from different input formats.

    Attributes:
        owner: Repository owner (e.g., "MarcusJellinghaus")
        repo_name: Repository name (e.g., "mcp_coder")
        hostname: Git host (e.g., "github.com" or "ghe.corp.com")

    Properties:
        full_name: Returns "owner/repo" format
        cache_safe_name: Returns "hostname_owner_repo" format for filenames
        https_url: Returns "https://hostname/owner/repo" format
        api_base_url: Returns API base URL for PyGithub
    """

    owner: str
    repo_name: str
    hostname: str = "github.com"

    @property
    def full_name(self) -> str:
        """Return repository in 'owner/repo' format."""
        return f"{self.owner}/{self.repo_name}"

    @property
    def cache_safe_name(self) -> str:
        """Return repository in 'hostname_owner_repo' format (safe for filenames)."""
        safe_hostname = self.hostname.replace(".", "_")
        return f"{safe_hostname}_{self.owner}_{self.repo_name}"

    @property
    def https_url(self) -> str:
        """Return repository HTTPS URL."""
        return f"https://{self.hostname}/{self.owner}/{self.repo_name}"

    @property
    def api_base_url(self) -> str:
        """Return API base URL for PyGithub."""
        return hostname_to_api_base_url(self.hostname)

    @property
    def web_host(self) -> str | None:
        """Web origin for fine-grained PAT settings URL.

        Mirrors the three-branch host resolution in
        :func:`hostname_to_api_base_url` but without the ``api.`` subdomain
        or ``/api/v3`` suffix.

        Returns:
            ``"https://github.com"`` for ``github.com``;
            ``"https://<host>"`` for ``*.ghe.com`` (no ``api.`` prefix);
            ``None`` for any other host (GHES has no fine-grained PAT
            settings page).
        """
        h = self.hostname.lower()
        if h == "github.com":
            url: str | None = "https://github.com"
            logger.debug(
                "web_host input=%s normalized=%s branch=github.com url=%s",
                self.hostname,
                h,
                url,
            )
            return url
        if h.endswith(".ghe.com"):
            url = f"https://{h}"
            logger.debug(
                "web_host input=%s normalized=%s branch=ghe.com url=%s",
                self.hostname,
                h,
                url,
            )
            return url
        url = None
        logger.debug(
            "web_host input=%s normalized=%s branch=ghes-fallback url=%s",
            self.hostname,
            h,
            url,
        )
        return url

    def __str__(self) -> str:
        """Return string representation (full_name format)."""
        return self.full_name

    @classmethod
    def from_full_name(
        cls, full_name: str, hostname: str = "github.com"
    ) -> "RepoIdentifier":
        """Parse 'owner/repo' format into RepoIdentifier.

        Args:
            full_name: Repository in "owner/repo" format
            hostname: Git host (default: "github.com")

        Returns:
            RepoIdentifier instance

        Raises:
            ValueError: If input doesn't contain exactly one slash,
                       or if owner or repo_name is empty
        """
        slash_count = full_name.count("/")
        if slash_count != 1:
            raise ValueError(
                f"Invalid repo identifier '{full_name}': expected 'owner/repo' format "
                f"(exactly one slash), got {slash_count} slashes"
            )

        owner, repo_name = full_name.split("/")

        if not owner:
            raise ValueError(
                f"Invalid repo identifier '{full_name}': owner cannot be empty"
            )
        if not repo_name:
            raise ValueError(
                f"Invalid repo identifier '{full_name}': repo_name cannot be empty"
            )

        return cls(owner=owner, repo_name=repo_name, hostname=hostname)

    @classmethod
    def from_repo_url(cls, url: str) -> "RepoIdentifier":
        """Parse a GitHub or GitHub Enterprise URL into RepoIdentifier.

        Supports both HTTPS and SSH URL formats with any hostname:
        - https://[credentials@]hostname/owner/repo[.git][/]
        - git@hostname:owner/repo[.git][/]

        Args:
            url: Repository URL (GitHub.com or GHE)

        Returns:
            RepoIdentifier instance

        Raises:
            ValueError: If URL is not a valid GitHub URL
        """
        if not isinstance(url, str):
            raise ValueError("Repository URL must be a string")

        # HTTPS: https://[credentials@]hostname/owner/repo[.git][/]
        https_pattern = r"https://(?:[^@]+@)?([^/]+)/([^/]+)/([^/]+?)(?:\.git)?/?$"
        https_match = re.match(https_pattern, url)
        if https_match:
            hostname, owner, repo_name = https_match.groups()
            return cls(owner=owner, repo_name=repo_name, hostname=hostname)

        # SSH: git@hostname:owner/repo[.git][/]
        ssh_pattern = r"git@([^:]+):([^/]+)/([^/]+?)(?:\.git)?/?$"
        ssh_match = re.match(ssh_pattern, url)
        if ssh_match:
            hostname, owner, repo_name = ssh_match.groups()
            return cls(owner=owner, repo_name=repo_name, hostname=hostname)

        raise ValueError(
            f"Invalid repository URL '{url}': expected HTTPS or SSH URL format"
        )
