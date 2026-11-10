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
