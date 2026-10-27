# Summary: Opt-in GitHub traffic log (issue #359)

## Goal

Make it visible which command and which function sends each GitHub HTTP request, across all
processes that share one `config.toml`, without changing normal logging.

When `[github] traffic_log = true` is set in the mcp-coder `config.toml`, every HTTP attempt
is written as one line to a daily file `github_requests_YYYY-MM-DD.log`. Each line carries the
command name and the filtered call chain.

```
timestamp | pid | command | METHOD path | status | resource remaining | duration | call chain
2026-10-27T09:14:03.412+01:00 | 18244 | vscodeclaude launch | GET /repos/o/r/actions/runs/123/jobs?page=2 | 200 | core 4211 | 182ms | commands_vscodeclaude.execute_coordinator_vscodeclaude > checks.check_pr_health > ci_results_manager.CIResultsManager.get_latest_ci_status
```

## Architectural / design changes

1. **New stdlib-only utility module `mcp_workspace/traffic_log.py`** (utilities layer, depends
   only on `mcp_workspace.config`). It owns the command context, the call-chain walk, the line
   format and the locked append. It must not import PyGithub or `requests`: `main.py` imports
   it, and `main.py` must not load PyGithub (`tests/test_startup_performance.py`, layering).
   mcp_coder imports it directly: `from mcp_workspace.traffic_log import set_traffic_log_context`.
2. **Config switch read once per process.** `config.get_traffic_log_dir() -> Path | None`,
   cached with `functools.cache`. `None` means off. `_load_config`, the token lookup and
   `get_trusted_commenters` stay uncached. Callers use `config.get_traffic_log_dir()` through
   the module attribute, so the autouse test fixture can replace it.
3. **Three hook points, all calling `traffic_log.log_request(...)`:**
   - `_client.build_github_client`: when the log is on, a per-instance wrapper replaces
     `client.requester._Requester__requestRaw`. Each hop (202/301/302) passes it again. An
     exception is logged once and then marked (`_traffic_logged` attribute), so outer wrappers
     stay silent. If the private name is missing, it warns once and doesn't install anything.
   - `_client._LoggingGithubRetry.increment`: writes a `retry ...` line only when
     `super().increment` returns (another attempt follows). If it raises, it writes nothing,
     and the wrapper's `ERR` line stands for that attempt.
   - `CIResultsManager._download_and_extract_zip`: one line for the raw `requests.get`.
4. **Entry point** `main._main()` calls `set_traffic_log_context(command="mcp-workspace server")`.
5. **Architecture configs:** `tach.toml` and `.importlinter` register `mcp_workspace.traffic_log`.

### Key decisions (KISS)

| Topic | Decision |
|---|---|
| Settings | One cached value, `Path \| None`; no settings type. Bad config values silently fall back (no warning). |
| Public API | `set_traffic_log_context(command)`, `log_request(method, url, status, headers, duration_ms)`, `error_status(exc)`. Everything else is private. |
| Off path | `log_request` returns at once when off; the wrapper is installed only when on. |
| Own frames | The chain walk skips the modules `mcp_workspace.traffic_log` and `mcp_workspace.github_operations._client`. |
| Signed URLs | Drop the query string on `follow_302_redirect=True` calls (blob downloads carry SAS signatures). The raw download logs the original API URL. |
| Write | Thread lock + non-blocking file lock (`msvcrt.locking` / `fcntl.flock`), a few short retries, one `os.write` per line, file opened per line. Any failure skips the line silently. |
| Rotation | The daily file name does it; no rotating handlers. |
| Concurrency check | A scratch probe in step 2 (deleted afterwards), not a permanent test. |
| No exit summary, no env var, independent of `--log-level`. | As in the issue. |

## Files created / modified

### Created
- `src/mcp_workspace/traffic_log.py` — context, chain, format, locked append
- `tests/github_operations/test_traffic_log.py` — unit tests for the module
- `tests/github_operations/test_client_traffic_log.py` — hook tests (wrapper, retry, line counts)

### Modified
- `src/mcp_workspace/config.py` — `get_traffic_log_dir()`
- `tests/conftest.py` — autouse fixture: log off, cache cleared
- `tests/test_config.py` — tests for `get_traffic_log_dir()`
- `src/mcp_workspace/github_operations/_client.py` — wrapper install + `increment` override
- `src/mcp_workspace/github_operations/ci_results_manager.py` — raw download logging
- `tests/github_operations/test_ci_results_manager_logs.py` (and `..._artifacts.py` if needed) — tests; mocks get `history = []`
- `src/mcp_workspace/main.py` — register command name
- `tests/test_main.py` — test that the command name is set
- `tach.toml`, `.importlinter` — register the new module
- `README.md` — document `traffic_log`, `traffic_log_dir`, the line format and hop semantics

## Steps

1. `step_1.md` — config switch `get_traffic_log_dir()` + autouse fixture
2. `step_2.md` — `traffic_log.py` writer module + architecture registration + concurrency probe
3. `step_3.md` — `__requestRaw` wrapper in `build_github_client`
4. `step_4.md` — retry lines in `_LoggingGithubRetry.increment` + end-to-end line counts
5. `step_5.md` — raw download logging in `CIResultsManager`
6. `step_6.md` — `mcp-workspace server` command name in `main.py`
7. `step_7.md` — README docs

## Out of scope

- mcp_coder side (command registration per CLI command, `_CONFIG_SCHEMA`, template, docs):
  MarcusJellinghaus/mcp_coder#1300.
