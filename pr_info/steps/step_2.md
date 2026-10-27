# Step 2: `traffic_log.py` writer module

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_2.md` only.
> TDD: write the tests first, then the implementation. Run pylint, pytest
> (`extra_args: ["-n", "auto"]`), mypy, `run_lint_imports_check` and `run_tach_check` until all
> pass. Run the concurrency probe described below, then delete `.scratch/`. Format with
> `run_format_code`, then make exactly one commit for this step.

## WHERE

- `src/mcp_workspace/traffic_log.py` (new, stdlib + `mcp_workspace.config` only)
- `tests/github_operations/test_traffic_log.py` (new)
- `tach.toml`, `.importlinter`

## WHAT

```python
def set_traffic_log_context(command: str) -> None:
    """Register the command name written on every line (set once at startup)."""

def log_request(
    method: str,
    url: str,
    status: str,
    headers: Mapping[str, Any] | None,
    started: float | None,
) -> None:
    """Append one traffic line when the log is on. Never raises.

    ``started`` is the caller's ``time.monotonic()`` before the request; the duration
    is computed here. ``None`` (retry lines) prints ``-``.
    """

def error_status(exc: BaseException) -> str:
    """Return ``ERR <Type>`` plus `` <status>`` when ``exc.status`` is an int."""

# private
def _call_chain() -> str: ...
def _header(headers: Mapping[str, Any] | None, name: str) -> str: ...  # case-insensitive, "-" if missing
def _append(directory: Path, day: str, line: str) -> None: ...
```

Module state: `_command = ""`, `_thread_lock = threading.Lock()`,
`_PACKAGES = frozenset({"mcp_coder", "mcp_workspace"})`,
`_SKIP_MODULES = frozenset({"mcp_workspace.traffic_log", "mcp_workspace.github_operations._client"})`,
`_DROP = ("<locals>.wrapper", "<listcomp>", "<genexpr>", "<lambda>", "<module>")`.

## HOW

- `from mcp_workspace import config`; call `config.get_traffic_log_dir()` (module attribute).
- Platform locks: `if sys.platform == "win32": import msvcrt` / `else: import fcntl` (mypy
  understands the platform check).
- `log_request` wraps everything after the off-check in
  `try: ... except Exception:  # pylint: disable=broad-exception-caught` → `pass`.
- `tach.toml`: new `[[modules]] path = "mcp_workspace.traffic_log"`, `layer = "utilities"`,
  `depends_on = [{ path = "mcp_workspace.config" }]`; add it to the `tests` module's `depends_on`.
- `.importlinter` layers contract: add a row `mcp_workspace.traffic_log` directly above the
  `mcp_workspace.config | ...` row (`|` siblings must not import each other).

## ALGORITHM

```
log_request: directory = config.get_traffic_log_dir(); if None: return
  now = datetime.now().astimezone(); parts = urlsplit(url)
  path = parts.path + ("?" + parts.query if parts.query else "")
  line = " | ".join([now.isoformat(timespec="milliseconds"), str(os.getpid()), _command,
         f"{method} {path}", status, f"{_header(h,'x-ratelimit-resource')} {_header(h,'x-ratelimit-remaining')}",
         f"{round((time.monotonic() - started) * 1000)}ms" if started is not None else "-", _call_chain()])
  _append(directory, now.strftime("%Y-%m-%d"), line)

_call_chain: frame = sys._getframe(1); names = []
  while frame: module = frame.f_globals.get("__name__", ""); qual = frame.f_code.co_qualname
    if module.partition(".")[0] in _PACKAGES and module not in _SKIP_MODULES and not any(d in qual for d in _DROP):
      names.append(f"{module.rpartition('.')[2]}.{qual}")
    frame = frame.f_back
  return " > ".join(reversed(names))

_append: mkdir(parents, exist_ok); with _thread_lock:
  fd = os.open(file, O_WRONLY|O_APPEND|O_CREAT|getattr(os, "O_BINARY", 0))
  try: up to ~50 tries: lock (win: lseek(fd,0); msvcrt.locking(fd, LK_NBLCK, 1); posix: flock LOCK_EX|LOCK_NB), sleep 2 ms on OSError
       if not locked: return (skip line)
       os.write(fd, (line + "\n").encode("utf-8")); unlock (win: lseek(fd,0); LK_UNLCK)
  finally: os.close(fd)
```

## DATA

- File: `<dir>/github_requests_YYYY-MM-DD.log`, utf-8, `\n` line ends, one line per call.
- `error_status(GithubException(403, ...))` → `"ERR GithubException 403"`;
  `error_status(TimeoutError())` → `"ERR TimeoutError"`.
- Never written: token, auth headers, request/response bodies.

## Tests (`tests/github_operations/test_traffic_log.py`)

Enable with `monkeypatch.setattr("mcp_workspace.config.get_traffic_log_dir", lambda: tmp_path)`.
Reset `_command` after tests that set it (monkeypatch `traffic_log._command`).

- off (fixture default) → no file created, `_call_chain` not called
- line fields: timestamp with offset, pid, command, `GET /repos/o/r?page=2` (host stripped
  from an absolute URL, query kept), status, `core 4211`, `182ms` (monkeypatch
  `traffic_log.time.monotonic` to return `started + 0.182`); `started=None` → `-`
- headers: lowercased keys, mixed-case keys, missing → `- -`, `headers=None` → `- -`
- `error_status` with and without `.status`
- chain filtering: build fake frames by `exec`-ing code with `__name__` set in globals
  (e.g. `{"__name__": "mcp_coder.cli.commands"}`) that calls a helper calling `_call_chain()`;
  assert:
  - `mcp_coder_utils.log_utils` frames dropped (exact package match)
  - `x.<locals>.wrapper`, `<lambda>`, `<listcomp>`, `<genexpr>`, `<module>` dropped
  - `mcp_workspace.traffic_log` / `..._client` frames dropped
  - outermost first, joined by ` > `, name is `<last component>.<co_qualname>`
- unwritable directory (a file path used as directory) → no exception
- two calls → two lines in the same daily file

## Concurrency probe (scratch, not committed)

`.scratch/test_probe.py`: spawn 8 processes (`multiprocessing`, spawn context), each appending
200 lines via `traffic_log._append` to one `tmp_path` file. Assert 1600 lines, each line intact
and unique. Run with `run_pytest_check(extra_args=["-p", "no:cacheprovider", ".scratch/test_probe.py"])`,
then `delete_directory(".scratch", recursive=True)`.

If the probe loses or merges lines after the lock is in place, write one line to
`pr_info/.blocked.txt` and stop.
