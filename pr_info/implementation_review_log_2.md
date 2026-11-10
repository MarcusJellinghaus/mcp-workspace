# Implementation review log 2 — issue #378

Supervisor-driven review of branch `378-export-workspace-tools-as-toolspec-s-from-a-toolset-factory-bound-to-a-project-directory` against `main`. Follows log 1 (escalated: check venv lacked `mcp_coder_utils.tool_spec`; stale docstring at `github_operations/search.py:4`).

## Round 1 — 2026-11-10
**Findings**:
- Check venv still lacks `mcp_coder_utils.tool_spec` → pytest, perf pytest, pylint (13× E0401/E0611), mypy (13× import-not-found) cannot run locally. ruff, lint-imports, tach, vulture, deptry pass; GitHub CI green on `ad75838`.
- `src/mcp_workspace/github_operations/search.py:4` — stale "handler in server.py" docstring (low).
- `tests/test_startup_performance.py:108-138` — threshold 2.0s → 3.0s, renamed, xdist-skipped (medium).
- `.claude/CLAUDE.md:85` — shared-config edit for the performance step (low).
- `.github/workflows/ci.yml`, `tools/pytest_check.bat`, `tools/run_all_checks.sh`, `pyproject.toml:91` — new serial `performance` step/marker (low).
- `tests/toolset/test_toolset.py:101-147` — `list_directory` not covered by outside/gitignored refusal tests (low).
- `tests/test_server.py:15` — `ToolMap` imported from `tests.conftest` (low).
- All acceptance criteria otherwise met; 32 tools (issue table omits `github_issue_set_status`, placed correctly in `workspace.github`, `read_only=False`).

**Decisions**:
- Venv: environment, not code → escalate to user at the end; CI is the verification for now.
- search.py docstring: accept.
- Startup threshold / CLAUDE.md / perf tooling: skip — triaged in log 1; deliberate workaround for build-machine import time (`import mcp.server.fastmcp` ≈2.2s). Name in the PR description.
- `list_directory` coverage: accept (acceptance criterion covers `workspace.read`).
- `ToolMap` import: skip — speculative, cosmetic.

**Changes**:
- `search.py` docstring now points to the `github_search` tool in `toolset/github_read.py`.
- `test_toolset.py`: `("list_directory", {"path": ".."})` added to the outside-path refusal cases.
- Not added: `search_files` outside-path case (no path parameter); `list_directory` gitignored case — engineer found (analytically, not probed) that `list_files` applies only the listed directory's `.gitignore`, not the root one, so `list_directory("secret")` with root `secret/` ignored lists contents. Same on `main` → pre-existing, out of scope; raised with the user.
- Local pytest/pylint/mypy not runnable (venv); ruff + format pass.

**Status**: committed

## Round 2 — 2026-11-10
**Findings**:
- `src/mcp_workspace/toolset/__init__.py:28-38` — MCP tool list order changed (now `_GROUPS` order; names and schemas unchanged) (low).
- `src/mcp_workspace/server.py:83-97` — startup INFO logging of settings and reference projects lost with the setters (low).
- All 32 moved tool bodies, `_github_common.py`, `_github_write_helpers.py`, `checks.py`, `create_server`/`FastMCPSink`/`run_server` verified against `main`: no drift. Test changes stay within setup/imports/patch targets plus the listed exceptions.
- Checks: ruff, lint-imports, vulture, tach pass; pytest/pylint/mypy blocked only by missing `mcp_coder_utils.tool_spec` in the check venv. CI green on `d0f0ae9`.

**Decisions**:
- Tool order: skip — issue pins names and schemas, not order; name it in the PR description.
- Startup logging: accept — operator-visible regression, one-line fix.

**Changes**:
- `run_server` logs one INFO line with all settings and one `Reference project '%s' set to: %s` line per reference project before `create_server(...).run()`; `toolset/` untouched (no side effects on the library path).
- `tests/test_server.py`: `test_run_server_logs_reference_projects` (caplog). Not run locally (venv).

**Status**: committed
