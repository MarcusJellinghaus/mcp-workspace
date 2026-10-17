# Step 2 — Two-stage startup, fallback log, unified error wrapper

Read `pr_info/steps/summary.md` first. This is the core step: the pre-parser, the
reordered startup sequence, and the single error-handling wrapper all land
together because they are one cohesive mechanism — none of them is independently
testable in a half-done state without temporarily breaking an existing test.

## Precondition

Step 1 is merged: `parse_args()` in `src/mcp_workspace/main.py` returns
`Tuple[argparse.Namespace, List[str]]` via `StartupArgumentParser` and
`parse_known_args`. If `parse_args()` does not already have this shape, write
one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/main.py`
- `tests/test_startup.py` (new file)

## WHAT

New functions in `src/mcp_workspace/main.py`:

```python
def _shared_options_parser() -> argparse.ArgumentParser: ...
def _pre_parse(argv: List[str]) -> argparse.Namespace: ...
def _validate_log_level(log_level: str) -> str: ...
def _resolve_project_dir(project_dir_arg: Optional[str]) -> Optional[Path]: ...
def _resolve_log_file(
    pre_args: argparse.Namespace, project_dir: Optional[Path]
) -> Optional[str]: ...
def _handle_startup_failure(exc: Exception) -> None: ...
def _main() -> None: ...
def main() -> None: ...   # replaces today's main()
```

Module-level constants:

```python
_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_FALLBACK_LOG_FILE = "logs/mcp_workspace_startup_error.log"
_HELP_TOKENS = frozenset({"-h", "--help", "--version"})
```

## HOW

- `_shared_options_parser()` builds one `StartupArgumentParser(add_help=False,
  allow_abbrev=False)` holding `--project-dir`, `--log-level`, `--log-file`,
  `--console-only` — the exact four `add_argument` calls `parse_args()` already
  has from step 1. `parse_args()` is changed to build its full parser with
  `parents=[_shared_options_parser()]` instead of defining those four options
  inline, so the definitions live in exactly one place.
- `_pre_parse(argv)` builds a second `StartupArgumentParser(add_help=False,
  allow_abbrev=False, parents=[_shared_options_parser()])` and returns
  `parser.parse_known_args(argv)[0]` (the namespace only; its extras are
  discarded — the issue requires unknown-argument reporting to come from the
  *full* parser's leftovers, handled in step 3).
- `_validate_log_level` raises `ValueError` if `log_level.upper()` is not in
  `_LOG_LEVELS`, else returns `log_level.upper()` (the normalized, upper-cased
  value — never the original-case input — since this return value is passed
  straight into `setup_logging`, which expects the canonical names).
- `_resolve_project_dir` returns `None` for an empty/missing value or a path
  that doesn't exist or isn't a directory, else `Path(arg).resolve()`.
- `_resolve_log_file`: `console_only` → `None`; else explicit `--log-file` →
  that value; else `project_dir is not None` → the existing default
  `<project_dir>/logs/mcp_workspace_{timestamp}.log` construction (unchanged
  from today's code); else `None`.
- `_handle_startup_failure(exc)`: if no handler in
  `logging.getLogger().handlers` is a `logging.FileHandler`, call
  `setup_logging("INFO", _FALLBACK_LOG_FILE)` inside a `try/except OSError:
  pass` (the known limitation: an unwritable working directory means no
  fallback file, but execution continues to the `print` below regardless).
  Then `stdlogger.error("Startup failed", exc_info=exc)` and
  `print(f"Error: {exc}", file=sys.stderr)`.
- Log-level validation must never run before a normal log sink can exist for
  it to be reported through. `_validate_log_level` only raises; it never
  establishes a handler. So when a log file is about to be used (`log_file is
  not None or pre.console_only`), call `setup_logging` with a *resolved*
  level: try `_validate_log_level(pre.log_level)` first — if it raises,
  immediately call `setup_logging("INFO", log_file)` to establish the normal
  (or console) sink anyway, then re-raise the original `ValueError` so
  `_handle_startup_failure` logs the bad value into the sink that now exists,
  instead of falling back. If validation succeeds, call `setup_logging` once
  with the validated level as normal. This is the only place a hardcoded
  `"INFO"` is used, and only to bootstrap a sink for reporting the error — it
  does not mean the server runs with `"INFO"` (the process still exits 1
  right after).
- `_main()` holds everything `main()` used to do, reordered. `main()` becomes
  the try/except wrapper shown in the summary, with
  `# pylint: disable=broad-exception-caught` on the `except Exception` line.
- Delete the old inline `print(...); sys.exit(1)` blocks for project-dir and
  file-size-limit validation; replace with `raise ValueError(...)`.
- Keep the call order inside `_main()`: pre-parse → resolve project dir/log
  file → validate log level and call `setup_logging(...)` (bootstrapping with
  `"INFO"` on an invalid level, per above) → project-dir check → full
  `parse_args()` → file-size-limit check → `ensure_truststore()` →
  reference-project validation → `run_server(...)`.

## ALGORITHM

```
_main():
    argv = sys.argv[1:]
    if any token in argv is one of -h/--help/--version:
        parse_args(argv)     # argparse's own -h/--version action exits 0
        return                # unreachable in practice

    pre = _pre_parse(argv)                       # may raise ValueError
    project_dir = _resolve_project_dir(pre.project_dir)
    log_file = _resolve_log_file(pre, project_dir)

    if log_file is not None or pre.console_only:
        try:
            log_level = _validate_log_level(pre.log_level)  # may raise ValueError
        except ValueError:
            # Bootstrap a sink with a known-good level so the bad value below
            # still lands in a real log file instead of triggering the fallback.
            setup_logging("INFO", log_file)      # may raise OSError
            raise
        setup_logging(log_level, log_file)       # may raise OSError

    if project_dir is None:
        raise ValueError("--project-dir is required and must be an existing directory: ...")

    args, unknown = parse_args(argv)              # may raise ValueError
    # (unknown handling: step 3)

    if args.file_size_limit is not None and args.file_size_limit <= 0:
        raise ValueError(f"--file-size-limit must be a positive integer: {args.file_size_limit}")

    ensure_truststore()
    reference_projects = validate_reference_projects(args.reference_project, project_dir) if args.reference_project else {}
    from mcp_workspace.server import run_server
    run_server(project_dir, reference_projects=reference_projects,
               file_size_limit=args.file_size_limit, fail_on_reviews=args.fail_on_reviews)

main():
    try: _main()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _handle_startup_failure(exc)
        sys.exit(1)
```

## DATA

- `_resolve_project_dir` / `_resolve_log_file`: `Optional[Path]` /
  `Optional[str]` — `None` signals "not available yet", never raises itself.
- `main()` always exits with code `1` on any exception, `0` on success or on
  `-h`/`--help`/`--version`, and never raises out of the process (every
  exception is caught once).

## Tests (write first)

Create `tests/test_startup.py`. Add an autouse fixture that snapshots
`logging.getLogger().handlers` and level before each test and restores them
after, since these tests call the real `setup_logging`. Use `tmp_path` for the
project directory and `monkeypatch.chdir` to control where the fallback log
lands; patch only `mcp_workspace.server.run_server` (never `setup_logging`).

- `test_missing_project_dir_falls_back` — `sys.argv` has no `--project-dir`;
  `monkeypatch.chdir(tmp_path)`; expect `SystemExit(1)`; assert
  `tmp_path / "logs" / "mcp_workspace_startup_error.log"` exists and its text
  mentions `--project-dir`.
- `test_invalid_project_dir_falls_back` — `--project-dir` points at a path that
  does not exist; same assertions as above.
- `test_invalid_log_level_logs_to_normal_log` — valid `--project-dir
  tmp_path`, `--log-level BOGUS`; expect `SystemExit(1)`; assert the normal
  log under `tmp_path/logs/` (glob `mcp_workspace_*.log`) contains `BOGUS`,
  and the fallback file was never created.
- `test_invalid_file_size_limit_logs_to_normal_log` — valid project dir,
  `--file-size-limit 0`; expect `SystemExit(1)`; assert the normal log
  contains `file-size-limit`.
- `test_trailing_log_level_flag_falls_back` — `argv` ends in `--log-level`
  with no value (plus a valid `--project-dir`); `monkeypatch.chdir(tmp_path)`;
  expect `SystemExit(1)`; assert
  `tmp_path / "logs" / "mcp_workspace_startup_error.log"` exists and has an
  entry (the pre-parser itself fails, so `--project-dir` is never reached).
- `test_trailing_project_dir_flag_falls_back` — `argv` ends in
  `--project-dir` with no value; `monkeypatch.chdir(tmp_path)`; same
  assertion against `tmp_path / "logs" / "mcp_workspace_startup_error.log"`.
- `test_bare_reference_project_flag_logs_to_normal_log` — valid
  `--project-dir`, trailing bare `--reference-project`; expect
  `SystemExit(1)`; assert the *normal* log (not fallback) has an entry, since
  the pre-parser succeeds and only the full parser fails.
- `test_unwritable_log_dir_falls_back` — create `tmp_path / "project"` as the
  project dir with a regular *file* named `logs` inside it (not a directory);
  `monkeypatch.chdir` to a *different* writable `tmp_path` subdirectory so the
  fallback target itself is writable; expect `SystemExit(1)`; assert the
  fallback log under the chdir'd cwd exists and mentions the failure.
- `test_fallback_log_appends_on_repeated_failures` — call `main()` twice with
  a missing `--project-dir` and the same `monkeypatch.chdir(tmp_path)`; assert
  the fallback log contains two error entries.
- `test_run_server_crash_logs_traceback` — valid project dir; patch
  `mcp_workspace.server.run_server` to `raise RuntimeError("boom")`; expect
  `SystemExit(1)`; assert the normal log contains `boom` and `Traceback`.
- `test_help_and_version_exit_zero_no_log_file` — parametrize over
  `["--help"]` and `["--version"]`, with no `--project-dir` given;
  `monkeypatch.chdir(tmp_path)`; expect `SystemExit(0)`; assert no `logs/`
  directory was created anywhere under `tmp_path`.
- `test_console_only_startup_error_still_writes_fallback` — `--console-only`,
  no `--project-dir`; `monkeypatch.chdir(tmp_path)`; expect `SystemExit(1)`;
  assert `tmp_path / "logs" / "mcp_workspace_startup_error.log"` exists.
- `test_startup_error_goes_to_stderr_not_stdout` — valid `--project-dir
  tmp_path`, `--log-level BOGUS`; use `capsys`; expect `SystemExit(1)`; assert
  `capsys.readouterr().err` contains `BOGUS` (or the error message) and
  `capsys.readouterr().out` is empty.

Also re-run (unchanged) `tests/test_reference_projects.py`'s `main()`-level
tests and `tests/test_ssl.py::test_main_activates_truststore_before_server_start`
to confirm they still pass with no edits — trace: they mock
`mcp_workspace.main.setup_logging` and `mcp_workspace.main.Path.exists`/
`Path.is_dir`, both of which the new code still calls the same way.

## Checks

`run_pytest_check` (`-n auto`), `run_pylint_check`, `run_mypy_check`,
`run_ruff_check`.

## Commit

One commit: `feat(main): two-stage startup parsing with fallback error log`

## LLM prompt for this step

> Read `pr_info/steps/summary.md`, then implement exactly
> `pr_info/steps/step_2.md`. Write the new `tests/test_startup.py` first (it
> will fail against the current `main.py`), then rewrite
> `src/mcp_workspace/main.py` to make it pass. Re-run the existing
> `main()`-level tests in `tests/test_reference_projects.py` and the
> truststore-order test in `tests/test_ssl.py` without editing them — they are
> expected to keep passing; if either fails, fix `main.py`, not the test. Run
> pytest, pylint, mypy, and ruff via the MCP tools; all must pass. If the
> precondition does not hold, write one line to `pr_info/.blocked.txt` and
> stop.
