"""Shared constants for mcp_workspace."""

DUPLICATE_PROTECTION_SECONDS: int = 60

# Fixed margin re-scanned on each incremental issue-cache refresh to absorb
# GitHub's eventually-consistent `since`-index lag (a write can be briefly
# absent from a `since`-filtered list just after it happens).
SINCE_OVERLAP_MINUTES: int = 5
