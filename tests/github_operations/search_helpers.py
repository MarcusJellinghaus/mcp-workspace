"""Shared doubles for the github_search tests.

Lives outside a ``test_`` module so pytest does not collect it, and outside
``conftest.py`` because these are plain importable helpers rather than
fixtures. Both ``test_github_read_tools_pr_search`` (result capping and the
truncation notice) and ``test_github_search_tool`` (query construction) need
them.
"""

from typing import Iterator, Optional
from unittest.mock import MagicMock


class FakeSearchResults:
    """PaginatedList stand-in with lazy iteration and a real totalCount.

    PyGithub fills `totalCount` from the first search page, so reading it after
    iterating costs no extra request. This double records every read, and yields
    items one at a time, so tests can assert both how often the property is read
    and how many items the caller pulled.
    """

    def __init__(
        self, items: list[MagicMock], total_count: Optional[int] = None
    ) -> None:
        self._items = items
        self._total_count = len(items) if total_count is None else total_count
        self.items_pulled = 0
        self.total_count_reads = 0

    def __iter__(self) -> Iterator[MagicMock]:
        for item in self._items:
            self.items_pulled += 1
            yield item

    @property
    def totalCount(self) -> int:  # pylint: disable=invalid-name
        """Mirrors PyGithub's camelCase attribute; counts each read."""
        self.total_count_reads += 1
        return self._total_count


def make_search_items(count: int) -> list[MagicMock]:
    """Create search result mocks numbered 1..count."""
    items = []
    for i in range(count):
        item = MagicMock()
        item.number = i + 1
        item.title = f"Item {i + 1}"
        item.state = "open"
        item.labels = []
        item.pull_request = None
        items.append(item)
    return items
