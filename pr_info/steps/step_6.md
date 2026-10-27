# Step 6: `mcp-workspace server` command name in `main.py`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_6.md` only.
> TDD: write the tests first, then the implementation. Run pylint, pytest
> (`extra_args: ["-n", "auto"]`), mypy, `run_lint_imports_check` and `run_tach_check` until all
> pass. Format with `run_format_code`, then make exactly one commit for this step.

## WHERE

- `src/mcp_workspace/main.py`
- `tests/test_main.py`
- `tach.toml`: add `{ path = "mcp_workspace.traffic_log" }` to `mcp_workspace.main` `depends_on`

## WHAT

```python
from mcp_workspace.traffic_log import set_traffic_log_context

# in _main(), right after the -h/--help/--version early return:
set_traffic_log_context(command="mcp-workspace server")
```

## HOW

- A top-level import is fine: `traffic_log` imports only the standard library and
  `mcp_workspace.config`, never PyGithub. `tests/test_startup_performance.py` must still pass.
- No config read at startup; the setting is read on the first request.

## ALGORITHM

None (one call).

## DATA

- `traffic_log._command == "mcp-workspace server"` after `_main()` starts.

## Tests (`tests/test_main.py`)

Follow the file's existing pattern for running `_main()` with `run_server` patched out.
- after `_main()` with valid args, `traffic_log._command == "mcp-workspace server"`
  (reset `_command` with monkeypatch)
- `--version` / `--help` path: unchanged behaviour (no new assertion needed beyond existing tests)
