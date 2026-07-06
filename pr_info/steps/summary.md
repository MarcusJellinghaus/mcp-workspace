# Summary — Make `check_file_size` default limit configurable via a server CLI flag

Implements issue **#221**.

## Goal

Let each project set the default line limit used by the `check_file_size` MCP tool,
via a server-launch flag, without making `mcp-workspace` Python-specific.

```
mcp-workspace --project-dir /path/to/project --file-size-limit 750
```

## Resolution order (the core behaviour)

`check_file_size` resolves its effective limit as:

1. Explicit `max_lines` argument (always wins).
2. `--file-size-limit` value passed at server launch.
3. Fallback default `600`.

The distinction between "omitted" and "explicitly 600" is made with an explicit
`is None` sentinel test — **not** truthiness — which is why the signature changes
from `max_lines: int = 600` to `max_lines: Optional[int] = None`.

## Architectural / design changes

- **No new config source.** `mcp-workspace` has no project-scoped config file; every
  per-project setting is already a CLI flag (`--project-dir`, `--reference-project`,
  `--log-level`, `--log-file`, `--console-only`). `--file-size-limit` follows that
  existing pattern. We deliberately do **not** read `pyproject.toml` (that would make
  the default Python-ecosystem-only; the tool is otherwise language-neutral).
- **Mirrors the existing `project_dir` mechanism exactly.** A new module-level global
  `_file_size_limit` in `server.py` is set through a `set_file_size_limit()` setter,
  just like `_project_dir` / `set_project_dir`. The value flows
  `main() → run_server(file_size_limit=...) → set_file_size_limit(...)`, mirroring how
  `project_dir` flows today. `main.py` never touches the global directly — layering
  (Entry → Protocol) is preserved, consistent with `docs/ARCHITECTURE.md`.
- **Fail-fast validation at startup.** `argparse type=int` already rejects non-integers;
  `main()` adds a `<= 0` guard (`print(...)` + `sys.exit(1)`), matching the existing
  `--project-dir` validation style, so the server refuses to start on a bad value.
- **No coupling with `mcp-coder`.** The two tools keep independent limits; `mcp-coder`
  still enforces its own 750 via `check file-size --max-lines 750`. No shared config.
- **Backward compatible.** With no flag, `check_file_size()` still behaves as 600. The
  only user-visible schema change is the tool's `max_lines` default going from `600`
  to "unset" (server default applies).

## KISS notes

- The limit is resolved **inline** inside `check_file_size` (one small expression) —
  no helper function, no config object, no constant module.
- The `600` fallback stays inline (used in the resolution and the docstring); no named
  constant is introduced.
- Tests are pure-logic / mock-based — no fixtures beyond a global-reset, no integration
  markers.

## Folders / modules / files created or modified

| File | Change | Step |
|------|--------|------|
| `src/mcp_workspace/server.py` | Add `_file_size_limit` global + `set_file_size_limit()` setter; change `check_file_size` signature/resolution/docstring; add `file_size_limit` param to `run_server` and call the setter | 1 |
| `tests/test_server.py` | New tests: resolution order for `check_file_size`; `run_server` threads `file_size_limit` to the setter | 1 |
| `src/mcp_workspace/main.py` | Add `--file-size-limit` arg (`type=int`, default `None`); `<= 0` validation in `main()`; pass `file_size_limit=args.file_size_limit` to `run_server` | 2 |
| `tests/test_reference_projects.py` | New tests: `parse_args` parses/defaults `--file-size-limit`; `main()` exits on `<= 0`; `main()` passes the value to `run_server` | 2 |

No new folders or modules are created. (`tests/test_server.py` already exists.)

## Steps

- **Step 1 — `server.py`:** global, setter, resolution, docstring, `run_server` threading (+ tests). One commit.
- **Step 2 — `main.py`:** CLI flag, fail-fast validation, wire value into `run_server` (+ tests). One commit.

Step 2 depends on Step 1 (`run_server` must already accept `file_size_limit`).

## Acceptance criteria (from the issue)

- [ ] `--file-size-limit` value used when `max_lines` is omitted.
- [ ] Explicit `max_lines` overrides the flag value.
- [ ] No flag → fallback 600.
- [ ] Invalid flag value (≤ 0 or non-int) → server fails to start with a clear error.
- [ ] `check_file_size` docstring updated.
- [ ] Unit tests covering the above.
- [ ] Full check suite passes (format, lint-imports, vulture, pytest, pylint, mypy).
