# Issue #319 — Startup: always log, and tolerate unknown CLI arguments

## Problem

`mcp-workspace` uses a single `argparse.ArgumentParser` with `required=True` on
`--project-dir`. Any parse failure (missing required arg, unknown flag, bad value)
calls `argparse`'s default `error()`, which prints to stderr and `sys.exit(2)`s
**before logging is configured**. No log file is written, and an unrelated unknown
flag (e.g. a newer `.mcp.json` passing a flag an older install doesn't have) kills
the server outright with no diagnostic trail.

## Architectural / design changes

**Two-stage argument parsing.** A small, tolerant *pre-parser* (`add_help=False`,
`parse_known_args`, `allow_abbrev=False`) extracts only the four options logging
needs — `--project-dir`, `--log-level`, `--log-file`, `--console-only` — before
anything else happens. Logging is configured from those values. Only then does the
*full* parser (all other options) run. The four shared options are defined once in
a small template parser and reused by both the pre-parser and the full parser via
`parents=[...]`, so `--help` output stays complete and nothing is duplicated.

**Raise instead of exit.** Both parsers are instances of `StartupArgumentParser`,
an `argparse.ArgumentParser` subclass whose `error()` raises `ValueError` instead
of printing + `sys.exit(2)`. This is the *only* new exception type introduced —
every other startup failure (missing/invalid `--project-dir`, invalid
`--log-level`, invalid `--file-size-limit`, a reference-project URL mismatch) also
raises plain `ValueError`, matching the existing convention already used by
`validate_reference_projects`. There is deliberately no dedicated
`StartupError`/`ArgumentParsingError` class: every startup failure is just an
`Exception`, and they are all handled by the same single catch block.

**One wrapper, one fallback rule.** `main()` becomes a thin wrapper around a new
`_main()`:

```python
def main() -> None:
    try:
        _main()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _handle_startup_failure(exc)
        sys.exit(1)
```

`_handle_startup_failure` is the single place that decides whether a fallback log
is needed, using one rule: *if the root logger has no `FileHandler` yet, write the
error to `logs/mcp_workspace_startup_error.log` (relative to the working
directory) before logging the exception.* This one `isinstance` check correctly
covers every case the issue describes: no `setup_logging` call happened yet
(missing `--project-dir`, a trailing flag that made the pre-parser itself raise),
`setup_logging` raised `OSError` (unwritable log directory), and `--console-only`
was used (console handler only, no file — a fatal error still gets a file).
Nothing else needs to branch on *why* the error happened; a crash inside
`run_server()` is caught and logged with its traceback the same way as a bad CLI
argument.

**Unknown arguments are tolerated, not swallowed silently.** The full parser's
`parse_known_args` leftovers (not the pre-parser's) are logged one `WARNING` per
token, plus a single `INFO` line with version, `sys.executable`, project dir, and
the full ignored-args list — once logging is up. `--help`/`--version` are detected
by an exact-token scan of `sys.argv` *before* the pre-parser runs, so they still
exit 0 with no log file and no spurious "missing `--project-dir`" error.

**Stdout stays clean.** All startup error text that used to go to `print()`
(stdout) now goes to `print(..., file=sys.stderr)`, since stdout is the MCP
protocol channel.

## Files created or modified

| Path | Change |
|---|---|
| `src/mcp_workspace/main.py` | Core rewrite: `StartupArgumentParser`, shared pre-parser template, `parse_args()` returns `(Namespace, list[str])`, new `_main()`/`main()` split, fallback-log handling, unknown-arg logging |
| `tests/test_reference_projects.py` | Update the seven existing `parse_args()` tests for the new `(args, unknown)` return shape and the `ValueError` (not `SystemExit`) on a bad `--file-size-limit`; add one abbreviated-flag test |
| `tests/test_startup.py` | **New.** Real-`setup_logging` + `tmp_path` tests for the fallback log, invalid known args, trailing flags, unwritable log dir, crash-in-`run_server` traceback, `--help`/`--version` no-log-file, and unknown-argument warning/INFO line |
| `README.md` | Drop the "(Required)"/"required for security reasons" wording for `--project-dir` (still exits 1 without it, just not via `argparse`'s `required=True`); document that unknown arguments are ignored and logged |
| `tests/test_ssl.py` | No edit expected — verified by trace that `test_main_activates_truststore_before_server_start` still passes unchanged; step 2 re-runs it to confirm |
| `docs/ARCHITECTURE.md` | No edit — checked, contains no CLI/startup argument description to update |

No other module needs to change; `parse_args()` has exactly one call site
(`main.py` itself).

## Steps

1. [step_1.md](./step_1.md) — Tolerant, raising `parse_args()`
2. [step_2.md](./step_2.md) — Two-stage startup, fallback log, unified error wrapper
3. [step_3.md](./step_3.md) — Unknown-argument warning + INFO startup line
4. [step_4.md](./step_4.md) — README documentation update

Each step is one commit: tests, implementation, and `pylint`/`pytest`/`mypy`
(and `ruff`/`format`) all green.
