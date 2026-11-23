# Step 10 — Throttled auto-fetch + notes; the `git` tool uses it

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_10.md`.
> Write the tests first, then the implementation. Use the MCP tools from `.claude/CLAUDE.md`.
> Run pylint, pytest (`extra_args: ["-n", "auto"]`), mypy, lint-imports and vulture; all
> must pass. Also run the performance tests serially
> (`run_pytest_check(markers=["performance"], extra_args=["-n", "0"])`). Run
> `run_format_code`, then make exactly one commit for this step.

## WHERE

- `src/mcp_workspace/toolset/_context.py` — `FetchRecord`, two `ReferenceState` fields
- `src/mcp_workspace/toolset/_reference_freshness.py` (new)
- `src/mcp_workspace/toolset/reference.py` — `reference_project_path` marks a fresh clone
- `src/mcp_workspace/toolset/git.py`
- `tests/toolset/test_reference_freshness.py` (new), `tests/test_reference_projects_git.py`,
  `tests/test_credential_scrubbing.py`

## WHAT

```python
# toolset/_context.py
@dataclass(frozen=True)
class FetchRecord:
    completed_at: float          # time.monotonic() when the attempt finished
    failure: str | None          # scrubbed reason, None on success

class ReferenceState:            # add:
    fetch_locks: dict[str, threading.Lock] = field(default_factory=dict)
    fetch_records: dict[str, FetchRecord] = field(default_factory=dict)

# toolset/_reference_freshness.py  (sync; called from worker threads)
FETCH_TIMEOUT_S = 10.0
def mark_fetched(ctx: WorkspaceContext, name: str) -> None: ...
def fetch_if_stale(ctx: WorkspaceContext, name: str, path: Path) -> None: ...
def fetch_failure_note(ctx: WorkspaceContext, name: str, where: str | None) -> str | None: ...
def fallback_note(name: str) -> str: ...
def with_notes(exc: BaseException, notes: list[str]) -> Exception: ...
```

## HOW

- `fetch_if_stale` imports `fetch_origin` lazily inside the function (server startup must
  not load GitPython; `test_startup_performance.py`).
- `reference_project_path`: `if await ensure_available(...): mark_fetched(ctx, name)` —
  a fresh lazy clone counts as a fresh fetch.
- `git` tool, `reference_name` set: run fetch and git in the **same** `asyncio.to_thread` call:

```python
def _run() -> str:
    fetch_if_stale(ctx, reference_name, project_dir)
    note = fetch_failure_note(ctx, reference_name, None)
    try:
        output = git_impl(...)
    except Exception as exc:  # pylint: disable=broad-exception-caught  # re-raised with the note
        if note is None:
            raise
        error = with_notes(exc, [note])
    else:
        return output if note is None else f"{output}\n{note}"
    raise error  # outside the except block: no unscrubbed __context__
```

  Workspace calls (`reference_name is None`) are unchanged. No special case for
  `git(command="fetch")`. The git tool never shows the fallback note.

## ALGORITHM

```
_is_stale(ctx, name): rec = records.get(name)
    return rec is None or time.monotonic() - rec.completed_at >= ctx.reference_fetch_interval_minutes * 60

fetch_if_stale(ctx, name, path):
    if ctx.reference_fetch_interval_minutes == 0 or not _is_stale(ctx, name): return
    with fetch_locks.setdefault(name, threading.Lock()):     # held for fetch + retry
        if not _is_stale(ctx, name): return                   # queued readers stop here
        outcome = fetch_origin(path, timeout=FETCH_TIMEOUT_S)
        if outcome.attempted: records[name] = FetchRecord(time.monotonic(), outcome.failure)

fetch_failure_note(ctx, name, where):
    rec = records.get(name)
    if ctx.reference_fetch_interval_minutes == 0 or rec is None or rec.failure is None: return None
    return f"[reference {name}: fetch failed ({rec.failure})" + (f" — read {where}" if where else "") + "]"

with_notes(exc, notes): text = f"{exc}\n" + "\n".join(notes)
    for cls in (IsADirectoryError, FileNotFoundError, PermissionError, ValueError):
        if isinstance(exc, cls): return cls(text)
    return ValueError(text)                                   # e.g. GitCommandError
```

`fallback_note(name)` → `[reference {name}: no usable origin default branch — read the local folder]`.

## DATA

`ctx.reference_state.fetch_records["mcp-workspace"] == FetchRecord(1234.5, "git fetch timed out after 10 s")`.

## Tests (write first)

`tests/toolset/test_reference_freshness.py` (patch `fetch_origin` and `time.monotonic` in
the module under test; build contexts via `WorkspaceContext(...)` or `tool_specs`):
- No record → fetch; second call within the interval → no fetch; after the interval → fetch.
- Interval `0` → never fetches, `fetch_failure_note` is `None` even with a failure record.
- `attempted=False` → no record written.
- Failure → note on every later call until the next attempt one interval later, which
  replaces the record (success → note gone). No further fetch before then.
- Queued readers: three threads call `fetch_if_stale` while a fake `fetch_origin` sleeps
  0.2 s → exactly one fetch.
- Note texts: with `where` ("… — read origin/main @ 03d1741]") and without; note names
  `git fetch` (from step 1's naming), not `git -c`.
- `with_notes` keeps `FileNotFoundError`, `IsADirectoryError`, `ValueError`; an arbitrary
  `Exception` becomes `ValueError`; message = original text + newline + notes.
- `mark_fetched` after a mocked fresh clone → the first read does not fetch
  (via `reference_project_path` with `ensure_available` returning `True`).

`tests/test_reference_projects_git.py`:
- `git(..., reference_name=…)` on a real clone of a local origin, interval 15, upstream
  commit pushed from a second clone → `git log origin/main` output shows the new commit.
- Fetch failure (patched `fetch_origin` → `FetchOutcome(True, "boom")`) → output ends with
  `\n[reference ref: fetch failed (boom)]`; the call does not fail.
- Same plus a git error → `ValueError` whose text is the original error text followed by
  the note (existing error-text tests such as `test_git_failure_reaches_client_as_error_text`
  still pass).
- Interval `0` → `fetch_origin` not called.
- Existing tests in this file keep passing (paths there are mocked and not git repos, so no
  fetch runs).

`tests/test_credential_scrubbing.py`:
- Reference clone whose `origin` URL is `https://user:tok@127.0.0.1:1/x.git` (offline,
  unreachable); call the `git` tool with `reference_name` → the trailing note exists and
  contains neither `tok` nor `user:`.
