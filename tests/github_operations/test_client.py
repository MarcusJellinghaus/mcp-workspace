"""Unit tests for the centralized PyGithub client factory."""

from unittest.mock import patch

from mcp_workspace.github_operations._client import (
    GITHUB_REQUEST_TIMEOUT,
    GITHUB_RETRY_TOTAL,
    build_github_client,
)

MODULE = "mcp_workspace.github_operations._client"


def test_build_github_client_applies_timeout_retry_and_base_url() -> None:
    """build_github_client constructs Github with bounded timeout/retry."""
    with patch(f"{MODULE}.Github") as mock_github:
        client = build_github_client("tok", "https://api.github.com")

    mock_github.assert_called_once()
    call_kwargs = mock_github.call_args.kwargs
    assert call_kwargs["timeout"] == 10
    assert call_kwargs["base_url"] == "https://api.github.com"
    assert call_kwargs["retry"].total == 2
    assert client is mock_github.return_value


def test_factory_constants_are_load_bearing() -> None:
    """Guard the 30s single-call timeout math (10 x (1 + 2 retries))."""
    assert GITHUB_REQUEST_TIMEOUT == 10
    assert GITHUB_RETRY_TOTAL == 2
