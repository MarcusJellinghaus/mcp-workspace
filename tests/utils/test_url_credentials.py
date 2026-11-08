"""Tests for scrub_credentials."""

from mcp_workspace.utils.url_credentials import scrub_credentials


class TestScrubCredentials:
    """Tests for scrub_credentials helper."""

    def test_scrubs_user_and_password(self) -> None:
        """Test user:password userinfo is removed."""
        assert scrub_credentials("https://u:p@h/x") == "https://h/x"

    def test_scrubs_user_only(self) -> None:
        """Test user-only userinfo is removed."""
        assert scrub_credentials("ssh://git@h/x") == "ssh://h/x"

    def test_no_userinfo_unchanged(self) -> None:
        """Test text without userinfo is returned unchanged."""
        text = "fatal: could not read https://github.com/org/repo.git"
        assert scrub_credentials(text) == text

    def test_scrubs_every_url(self) -> None:
        """Test all URLs in the text are scrubbed."""
        text = "a https://u:p@h/x b https://v:q@g/y"
        assert scrub_credentials(text) == "a https://h/x b https://g/y"
