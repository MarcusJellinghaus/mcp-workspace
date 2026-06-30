"""Centralized PyGithub client factory.

All PyGithub ``Github`` instances are created through ``build_github_client`` so
the timeout/retry policy lives in exactly one place and cannot drift across the
individual call sites.
"""

from github import Auth, Github, GithubRetry

GITHUB_REQUEST_TIMEOUT = 10
GITHUB_RETRY_TOTAL = 2


def build_github_client(token: str, base_url: str) -> Github:
    """Create a PyGithub client with bounded timeout/retry.

    timeout=10 with GithubRetry(total=2) gives ~30s worst case on an
    unreachable host (1 initial + 2 retries). total=2 also caps 403
    secondary-rate-limit backoff to 2 attempts — deliberate, do NOT raise back.

    Args:
        token: GitHub personal access token.
        base_url: API base URL (e.g. ``https://api.github.com`` or a GHE host).

    Returns:
        A configured ``github.Github`` instance.
    """
    return Github(
        auth=Auth.Token(token),
        base_url=base_url,
        timeout=GITHUB_REQUEST_TIMEOUT,
        retry=GithubRetry(total=GITHUB_RETRY_TOTAL),
    )
