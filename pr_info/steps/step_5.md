# Step 5 — `main.py`: `--read-max-lines` flag and resolution

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **Step 5** exactly as described in `pr_info/steps/step_5.md`. Write the tests first, then the implementation. Run pylint, pytest (`-n auto`) and mypy via the MCP tools; all must pass. Run `run_format_code`, then make one commit.

## Precondition

Steps 1, 2 and 4 are done (`DEFAULT_READ_MAX_LINES` exported, `config.get_read_max_lines` exists, `run_server` accepts `read_max_lines`). If not, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/main.py`
- `tach.toml`
- `tests/test_main.py`

## WHAT

```python
# parse_args, after --file-size-limit
parser.add_argument(
    "--read-max-lines",
    type=int,
    default=None,
    help="Maximum lines returned by a full read_file / read_reference_file "
    "(0 = no limit; overrides [mcp_workspace] read_max_lines in config.toml; "
    "defaults to 2000).",
)
```

## HOW

- Imports: `from mcp_workspace import config` (call `config.get_read_max_lines()` through the module attribute so the conftest stub applies) and `from mcp_workspace.file_tools import DEFAULT_READ_MAX_LINES`. If importing `file_tools` at module top noticeably affects startup or causes a cycle, import it inside `_main()` next to the `run_server` import.
- `tach.toml`: add `{ path = "mcp_workspace.config" }` and `{ path = "mcp_workspace.file_tools" }` to the `mcp_workspace.main` module's `depends_on`, otherwise the tach check fails (`.importlinter`'s layered contract already permits these downward imports).
- Validation right after the `--file-size-limit` check: `< 0` (not `<= 0` — `0` is valid) → `ValueError(f"--read-max-lines must be a non-negative integer: {value}")`.
- Pass `read_max_lines=read_max_lines` to `run_server(...)`.
- No `0 → None` conversion: `0` flows through and the shared function treats it as no limit.

## ALGORITHM

```
if args.read_max_lines is not None and args.read_max_lines < 0: raise ValueError(...)
read_max_lines = args.read_max_lines
if read_max_lines is None: read_max_lines = config.get_read_max_lines()
if read_max_lines is None: read_max_lines = DEFAULT_READ_MAX_LINES
run_server(..., read_max_lines=read_max_lines)
```

## DATA

`read_max_lines: int` (≥ 0) passed to `run_server`.

## Tests (write first) — `tests/test_main.py`

Follow the existing `test_main_passes_file_size_limit` pattern (patch `mcp_workspace.server.run_server`, `Path.exists`, `Path.is_dir`, `setup_logging`).

- `parse_args` parses `--read-max-lines 500` → `500`; omitted → `None`.
- Nothing configured (conftest stub returns `None`) → `run_server` called with `read_max_lines=2000`.
- Config only (`monkeypatch.setattr("mcp_workspace.config.get_read_max_lines", lambda: 300)`) → `300`.
- Config `0` (`get_read_max_lines` stubbed to return `0`), no CLI flag → `run_server` called with `read_max_lines=0` (not replaced by the 2000 default).
- CLI and config both set (CLI `500`, config `300`) → `500`.
- CLI `0` → `0`.
- CLI `-1` → `SystemExit(1)`, `run_server` not called.
