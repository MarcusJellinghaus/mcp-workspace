# Summary — #380 Maximum line count for full reads in `read_file` / `read_reference_file`

Part of MarcusJellinghaus/agent-workbench#13 (step 3c). Blocks #378 (its factory uses `DEFAULT_READ_MAX_LINES`).

## Goal

A full read (no `start_line` / `end_line`) returns at most N lines (default **2000**) followed by a truncation note telling the agent how to page on. An explicit range is always returned in full. `append_file` is never limited.

## Architectural / design changes

| Layer | Change |
|---|---|
| Shared library (`file_tools`) | `read_file(..., max_lines: int \| None = None)`. `None`/`0` = no limit; `bool`, non-int, negative → `ValueError` (validated on every call, before the range check). Only applies to full reads. New public constant `DEFAULT_READ_MAX_LINES = 2000`, re-exported from `file_tools`. The shared default stays `None` so `append_file` (which reads through `read_file`) keeps reading whole files. |
| Config (`config.py`) | New `get_read_max_lines() -> int \| None` reading `[mcp_workspace] read_max_lines` from `~/.mcp_coder/config.toml`. Invalid values (negative, non-int, `bool`) log a warning and return `None`. No cache — called once at startup. |
| Server state | Module state `_read_max_lines: int \| None = DEFAULT_READ_MAX_LINES` in **both** `server.py` (setter `set_read_max_lines`) and `server_reference_tools.py` (setter `set_reference_read_max_lines`, separate to avoid a circular import and a name clash with the `server.py` import). |
| Tool wrappers | `read_file` (server) and `read_reference_file` always pass `max_lines=_read_max_lines`; the shared function decides whether it applies. Docstrings mention truncation + paging. |
| Startup (`main.py` / `run_server`) | New CLI flag `--read-max-lines` (argparse default `None`; `< 0` rejected). Resolution once at startup: CLI → `config.get_read_max_lines()` → `DEFAULT_READ_MAX_LINES`. Passed as `run_server(read_max_lines=...)`, which calls both setters unconditionally (outside the `if reference_projects:` block). |

### Truncation algorithm (shared function)

- Collect lines 1..N; for lines after N only count (`total = line_num`) — memory stays flat.
- Truncate only when line N+1 exists, so line N always ends with `\n` and the note starts on its own line.
- Note appended with no trailing newline, never numbered:
  `[truncated: showing lines 1–{N} of {total}; continue with start_line={N + 1}, end_line={min(2 * N, total)}]` (U+2013 en dash).
- With `with_line_numbers=True` only the N content lines are numbered (width from N — the existing `collected[-1][0]` logic).

### KISS decisions (agreed in plan review)

- No `0 → None` conversion in `main.py`: the shared function already treats `0` as no limit, so `0` flows through unchanged. (The issue calls this conversion "harmless"; dropping it preserves every requirement.)
- No helper extraction for the read loop unless pylint demands it.
- `get_read_max_lines` reads `_load_config()` directly, because `_read_config_value` is typed `str | None`.
- Tests: parametrize invalid values; no extra `test_startup.py` case (the existing file-size-limit startup test already covers the startup-error logging path).

## Files to modify

```
src/mcp_workspace/file_tools/file_operations.py   # DEFAULT_READ_MAX_LINES, read_file(max_lines=...)
src/mcp_workspace/file_tools/__init__.py          # re-export DEFAULT_READ_MAX_LINES
src/mcp_workspace/config.py                       # get_read_max_lines()
src/mcp_workspace/server_reference_tools.py       # _read_max_lines, set_reference_read_max_lines, wrapper
src/mcp_workspace/server.py                       # _read_max_lines, set_read_max_lines, wrapper, run_server
src/mcp_workspace/main.py                         # --read-max-lines, resolution, run_server kwarg
tach.toml                                         # main depends_on += config, file_tools
tests/file_tools/test_file_operations.py
tests/test_config.py
tests/conftest.py                                 # autouse stub for get_read_max_lines
tests/test_reference_projects_mcp_tools.py        # update exact-kwargs assertions (~279-285, ~318-324)
tests/test_server.py                              # update exact-kwargs assertion (~403-409)
tests/test_main.py
README.md
docs/release-notes.md
```

No new files or folders in `src/` or `tests/`.

## Steps

1. Shared `read_file` `max_lines` + `DEFAULT_READ_MAX_LINES` export.
2. `config.get_read_max_lines()` + conftest stub.
3. `server_reference_tools.py`: state, setter, `read_reference_file` passes limit.
4. `server.py`: state, setter, `read_file` passes limit, `run_server(read_max_lines=...)` calls both setters.
5. `main.py`: `--read-max-lines` flag and resolution.
6. Docs: README + release notes.
