# Step 3 — Unknown-argument warning + INFO startup line

Read `pr_info/steps/summary.md` first. This step is additive on top of step 2's
`_main()`; it does not change error handling.

## Precondition

Step 2 is merged: `src/mcp_workspace/main.py` has `_main()` calling
`args, unknown = parse_args(argv)` after `setup_logging` has run. If `_main()`
does not already bind an `unknown` variable from `parse_args()`, write one line
to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/main.py`
- `tests/test_startup.py`

## WHAT

No new functions. Add a short block in `_main()` right after
`args, unknown = parse_args(argv)`.

## HOW

Use the already-imported `stdlogger`, `__version__`, and `sys`. No new imports
needed beyond `sys.executable`, already available via the existing `import sys`.

## ALGORITHM

```
args, unknown = parse_args(argv)
for token in unknown:
    stdlogger.warning("Ignoring unknown startup argument: %s", token)
stdlogger.info(
    "Starting mcp-workspace %s: python=%s project_dir=%s ignored_args=%s",
    __version__, sys.executable, project_dir, unknown,
)
```

## DATA

No return value changes. The log file (console handler is never attached when
a file log is active, so these lines are file-only, as the issue requires)
gains: one `WARNING` line per unknown token, and one `INFO` line per startup
listing version, Python executable, project dir, and the ignored-args list
(empty list when there are none).

## Tests (write first)

In `tests/test_startup.py` (same fixtures/pattern as step 2):

- `test_unknown_argument_is_ignored_and_warned` — valid `--project-dir
  tmp_path` plus `--totally-unknown-flag value`; patch
  `mcp_workspace.server.run_server` to a no-op mock; call `main()`; assert it
  returns normally (no `SystemExit`); assert `mock_run_server` was called;
  read the normal log file and assert it contains a `WARNING` line with
  `--totally-unknown-flag` and an `INFO` line containing the running
  `__version__` string and `sys.executable`.
- `test_no_unknown_arguments_logs_empty_list` — same setup with no extra
  flags; assert the log's `INFO` startup line is present and does not list any
  ignored arguments (e.g. assert `"ignored_args=[]"` or equivalent appears).

## Checks

`run_pytest_check` (`-n auto`), `run_pylint_check`, `run_mypy_check`.

## Commit

One commit: `feat(main): log ignored unknown startup arguments`

## LLM prompt for this step

> Read `pr_info/steps/summary.md`, then implement exactly
> `pr_info/steps/step_3.md`. Add the two new tests to `tests/test_startup.py`
> first, see them fail, then add the warning/INFO logging block to `_main()`
> in `src/mcp_workspace/main.py`. Run pytest, pylint, and mypy via the MCP
> tools; all must pass. If the precondition does not hold, write one line to
> `pr_info/.blocked.txt` and stop.
