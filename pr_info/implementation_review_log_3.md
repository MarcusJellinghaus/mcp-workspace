# Implementation review log 3 — issue #378

Supervisor-driven review of branch `378-export-workspace-tools-as-toolspec-s-from-a-toolset-factory-bound-to-a-project-directory` against `main`. Follows log 2. Since then the check venv got an `mcp-coder-utils` with `tool_spec`: pylint, mypy, pytest (6549 passed, 20 skipped) and the serial performance test pass locally. Decided outside log 2: `list_directory` root-`.gitignore` gap → #392; CLAUDE.md performance-test line recorded as LOCAL-ONLY in #72; intentional deviations listed on #378 for the PR description.

## Round 1 — 2026-11-10
**Findings**: none new.
- Full local gate passes for the first time: pylint, mypy, pytest `-n auto` (6549 passed, 20 skipped, 340.7s — needs `timeout_seconds` above the 300s default), serial performance test, ruff, lint-imports, tach (2 ModuleNotFound warnings for the declared external `mcp_coder_utils` modules, exit 0), vulture, deptry.
- `mcp_coder_utils.tool_spec` API use (`tool_spec`, `ToolSink`, `ToolCollector`, `ToolSpec`, `dataclasses.replace`) matches the reference source; `FastMCPSink` satisfies `ToolSink` structurally.
- No workarounds for the missing module: `cast`, `type: ignore`, `Any` and pylint disables in `toolset/` come verbatim from `main`'s `server.py`; the new `redefined-outer-name` disable (`_github_common.py:130`) follows the `_pr_manager` → `pr_manager` rename.
**Decisions**: —
**Changes**: none
**Status**: no changes needed

## Final Status
- 1 round, no code changes.
- vulture: clean. lint-imports: 9 contracts kept.
- Local gate (pylint, mypy, pytest, performance, ruff, tach, deptry) passes; the venv blocker from logs 1–2 is resolved.
- No open review items. Deviations for the PR description are listed in the #378 comments; #392 tracks the pre-existing `list_directory` gap.
