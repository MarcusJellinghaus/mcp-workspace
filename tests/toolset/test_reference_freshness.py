"""Tests for the throttled reference auto-fetch and its notes."""

import subprocess
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from git import Repo

from mcp_workspace.git_operations.origin_fetch import FetchOutcome
from mcp_workspace.reference_projects import ReferenceProject
from mcp_workspace.toolset import _reference_freshness as freshness
from mcp_workspace.toolset._context import FetchRecord, WorkspaceContext
from mcp_workspace.toolset._reference_freshness import (
    FETCH_TIMEOUT_S,
    fallback_note,
    fetch_failure_note,
    fetch_if_stale,
    mark_fetched,
    with_notes,
)
from mcp_workspace.toolset.reference import reference_project_path

_FETCH_TARGET = "mcp_workspace.git_operations.origin_fetch.fetch_origin"
NAME = "ref"


class _Clock:
    """Settable stand-in for ``time.monotonic``."""

    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _ctx(tmp_path: Path, interval: int = 15) -> WorkspaceContext:
    path = tmp_path / NAME
    return WorkspaceContext(
        tmp_path,
        {NAME: ReferenceProject(name=NAME, path=path)},
        None,
        None,
        False,
        False,
        reference_fetch_interval_minutes=interval,
    )


@pytest.fixture
def clock() -> Iterator[_Clock]:
    """Patch the module's monotonic clock with a settable one."""
    fake = _Clock()
    with patch.object(freshness, "time", SimpleNamespace(monotonic=fake)):
        yield fake


class TestFetchIfStale:
    """Staleness and throttling."""

    def test_no_record_fetches_then_throttles_then_refetches(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        ctx = _ctx(tmp_path)
        path = tmp_path / NAME
        with patch(_FETCH_TARGET, return_value=FetchOutcome(True, None)) as fetch:
            fetch_if_stale(ctx, NAME, path)
            assert fetch.call_count == 1
            fetch.assert_called_with(path, timeout=FETCH_TIMEOUT_S)

            clock.now += 15 * 60 - 1
            fetch_if_stale(ctx, NAME, path)
            assert fetch.call_count == 1

            clock.now += 1
            fetch_if_stale(ctx, NAME, path)
            assert fetch.call_count == 2

    def test_record_is_written(self, tmp_path: Path, clock: _Clock) -> None:
        ctx = _ctx(tmp_path)
        clock.now = 1234.5
        with patch(
            _FETCH_TARGET,
            return_value=FetchOutcome(True, "git fetch timed out after 10 s"),
        ):
            fetch_if_stale(ctx, NAME, tmp_path / NAME)
        assert ctx.reference_state.fetch_records[NAME] == FetchRecord(
            1234.5, "git fetch timed out after 10 s"
        )

    def test_interval_zero_never_fetches(self, tmp_path: Path, clock: _Clock) -> None:
        ctx = _ctx(tmp_path, interval=0)
        ctx.reference_state.fetch_records[NAME] = FetchRecord(0.0, "boom")
        clock.now = 10_000_000.0
        with patch(_FETCH_TARGET) as fetch:
            fetch_if_stale(ctx, NAME, tmp_path / NAME)
        fetch.assert_not_called()
        assert fetch_failure_note(ctx, NAME, None) is None
        assert fetch_failure_note(ctx, NAME, "origin/main @ 03d1741") is None

    def test_not_attempted_writes_no_record(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        ctx = _ctx(tmp_path)
        with patch(_FETCH_TARGET, return_value=FetchOutcome(False, None)) as fetch:
            fetch_if_stale(ctx, NAME, tmp_path / NAME)
            fetch_if_stale(ctx, NAME, tmp_path / NAME)
        assert NAME not in ctx.reference_state.fetch_records
        assert fetch.call_count == 2

    def test_failure_note_until_next_attempt(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        ctx = _ctx(tmp_path)
        path = tmp_path / NAME
        with patch(_FETCH_TARGET, return_value=FetchOutcome(True, "boom")) as fetch:
            fetch_if_stale(ctx, NAME, path)
        assert fetch_failure_note(ctx, NAME, None) == (
            f"[reference {NAME}: fetch failed (boom)]"
        )

        with patch(_FETCH_TARGET) as fetch:
            for _ in range(3):
                clock.now += 60
                fetch_if_stale(ctx, NAME, path)
                assert fetch_failure_note(ctx, NAME, None) is not None
            fetch.assert_not_called()

        clock.now += 15 * 60
        with patch(_FETCH_TARGET, return_value=FetchOutcome(True, None)) as fetch:
            fetch_if_stale(ctx, NAME, path)
        fetch.assert_called_once()
        assert fetch_failure_note(ctx, NAME, None) is None
        assert ctx.reference_state.fetch_records[NAME] == FetchRecord(clock.now, None)

    def test_queued_readers_fetch_once(self, tmp_path: Path) -> None:
        ctx = _ctx(tmp_path)
        calls: list[Path] = []

        def slow_fetch(path: Path, timeout: float) -> FetchOutcome:
            calls.append(path)
            time.sleep(0.2)
            return FetchOutcome(True, None)

        with patch(_FETCH_TARGET, side_effect=slow_fetch):
            threads = [
                threading.Thread(target=fetch_if_stale, args=(ctx, NAME, tmp_path))
                for _ in range(3)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        assert len(calls) == 1


class TestNotes:
    """Note texts."""

    def test_failure_note_with_where(self, tmp_path: Path) -> None:
        ctx = _ctx(tmp_path)
        ctx.reference_state.fetch_records[NAME] = FetchRecord(1.0, "boom")
        assert fetch_failure_note(ctx, NAME, "origin/main @ 03d1741") == (
            f"[reference {NAME}: fetch failed (boom) — read origin/main @ 03d1741]"
        )

    def test_failure_note_without_where(self, tmp_path: Path) -> None:
        ctx = _ctx(tmp_path)
        ctx.reference_state.fetch_records[NAME] = FetchRecord(1.0, "boom")
        assert fetch_failure_note(ctx, NAME, None) == (
            f"[reference {NAME}: fetch failed (boom)]"
        )

    def test_no_note_without_record_or_on_success(self, tmp_path: Path) -> None:
        ctx = _ctx(tmp_path)
        assert fetch_failure_note(ctx, NAME, None) is None
        ctx.reference_state.fetch_records[NAME] = FetchRecord(1.0, None)
        assert fetch_failure_note(ctx, NAME, None) is None

    def test_fallback_note(self) -> None:
        assert fallback_note(NAME) == (
            f"[reference {NAME}: no usable origin default branch — read the local folder]"
        )

    def test_timeout_note_names_git_fetch(self, tmp_path: Path) -> None:
        """The real fetch's timeout reason names ``git fetch``, not ``git -c``."""
        path = tmp_path / NAME
        repo = Repo.init(path)
        repo.create_remote("origin", "https://example.invalid/x.git")
        repo.close()
        ctx = _ctx(tmp_path)
        with patch(
            "mcp_workspace.git_operations._subprocess_git.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=10),
        ):
            fetch_if_stale(ctx, NAME, path)
        note = fetch_failure_note(ctx, NAME, None)
        assert note == (
            f"[reference {NAME}: fetch failed (git fetch timed out after 10 s)]"
        )
        assert "git -c" not in note


class TestWithNotes:
    """Errors keep their type and carry the notes."""

    @pytest.mark.parametrize(
        "exc_type",
        [FileNotFoundError, IsADirectoryError, PermissionError, ValueError],
    )
    def test_type_is_kept(self, exc_type: type[Exception]) -> None:
        result = with_notes(exc_type("original"), ["[a]", "[b]"])
        assert type(result) is exc_type
        assert str(result) == "original\n[a]\n[b]"

    def test_other_exception_becomes_value_error(self) -> None:
        result = with_notes(RuntimeError("git broke"), ["[note]"])
        assert type(result) is ValueError
        assert str(result) == "git broke\n[note]"


class TestMarkFetched:
    """A fresh clone counts as a fresh fetch."""

    def test_mark_fetched_records_success(self, tmp_path: Path, clock: _Clock) -> None:
        ctx = _ctx(tmp_path)
        clock.now = 42.0
        mark_fetched(ctx, NAME)
        assert ctx.reference_state.fetch_records[NAME] == FetchRecord(42.0, None)

    @pytest.mark.asyncio
    async def test_fresh_clone_skips_first_fetch(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        ctx = _ctx(tmp_path)
        with patch(
            "mcp_workspace.toolset.reference.ensure_available",
            new_callable=AsyncMock,
            return_value=True,
        ):
            path = await reference_project_path(ctx, NAME)
        fetch = MagicMock()
        with patch(_FETCH_TARGET, fetch):
            fetch_if_stale(ctx, NAME, path)
        fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_existing_project_does_not_mark(self, tmp_path: Path) -> None:
        ctx = _ctx(tmp_path)
        with patch(
            "mcp_workspace.toolset.reference.ensure_available",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await reference_project_path(ctx, NAME)
        assert NAME not in ctx.reference_state.fetch_records
