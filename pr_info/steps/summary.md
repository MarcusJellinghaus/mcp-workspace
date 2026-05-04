# Summary — Issue #185: Simplify `check_branch_status` polling API

## Goal

Simplify and improve the `check_branch_status` MCP tool:

1. **Default-on CI polling** (5 minutes) so flows like `implementation_approve` actually wait for CI as their skill text implies.
2. **Drop the redundant `wait_for_pr` boolean** — collapse to a single `pr_timeout` int.
3. **Parallel polling** — `_wait_for_ci` and `_wait_for_pr` run concurrently via `asyncio.gather`. Total wall-clock = `max(ci_timeout, pr_timeout)`, not their sum.
4. **`Wait:` line in the report** — LLM can see how long polling actually ran and decide whether to retry with a longer timeout.
5. **Deadline-aware sleep bug fix** — small timeouts (e.g. `pr_timeout=5`) no longer wait one full poll interval (20 s).

## Architectural / Design Changes

This is a **single-module refactor** inside the `checks` layer — no new modules, no layer-boundary changes, no new external dependencies.

The shape of the change inside `branch_status.py`:

```
Before:                           After:
  BranchStatusReport               BranchStatusReport (+ optional wait_context kwarg on formatters)
                                   WaitContext              ← new dataclass alongside report
  _wait_for_ci   → None            _wait_for_ci   → float   (elapsed seconds)
  _wait_for_pr   → None            _wait_for_pr   → float   (elapsed seconds)
  async_poll_branch_status         async_poll_branch_status
    sequential PR-then-CI            parallel via asyncio.gather
    wait_for_pr boolean              dropped
    _DEFAULT_PR_TIMEOUT              dropped
```

Key design points (preserved from issue):

- **`WaitContext` lives outside `BranchStatusReport`**: report describes branch state; `WaitContext` describes the act of having waited. They're orthogonal — `collect_branch_status` callers don't carry `None` ballast.
- **`async_poll_branch_status` is the only construction site for `WaitContext`** — `collect_branch_status` and `BranchStatusReport` stay polling-agnostic.
- **No cross-poll cancellation** — each poll exits independently on terminal / own timeout / 3-error abort.
- **State-based Wait vocabulary** — `ok` / `fail` / `pending` / `missing`, mirroring existing report fields (`CIStatus`, `pr_found`).
- **Breaking API change** — `wait_for_pr` and `_DEFAULT_PR_TIMEOUT` are removed. Only callers are tests; no skill files pass them. MCP tool schema regenerates from the new signature.

### Simplifications applied (KISS)

- **Always-call `gather`** — pass `timeout=0` directly to helpers (they early-exit). Avoids conditional coroutine assembly in the orchestrator.
- **Single `_format_wait_line` helper** — shared by `format_for_llm` and `format_for_human` (issue requires both to render the same Wait line).
- **Helpers always return `float`** — `Optional[float]` semantics live only in `WaitContext`, decided at construction time from the input timeout (not the elapsed value).

## Files Modified

| Path | Type | Change |
|------|------|--------|
| `src/mcp_workspace/checks/branch_status.py` | source | Helper return type; `WaitContext` dataclass; `_format_wait_line`; orchestrator parallel polling; deadline-aware sleep |
| `src/mcp_workspace/server.py` | source | `check_branch_status` tool signature: drop `wait_for_pr`, change defaults to `ci_timeout=300, pr_timeout=0`, params-only docstring |
| `tests/checks/test_branch_status_polling.py` | tests | Drop `wait_for_pr` from calls; drop `_DEFAULT_PR_TIMEOUT` test; replace sequential-order test with event-based parallel proof; add deadline-aware sleep test; assert returned elapsed values; Wait-line rendering tests |
| `tests/test_server.py` | tests | Drop `wait_for_pr` from server-tool tests; assert new defaults |

No files created. No files deleted. No folder structure changes.

## Files NOT Touched (intentionally)

- `.claude/skills/*/SKILL.md` — issue explicitly says skills keep calling with defaults; the new `ci_timeout=300` default is the intended behavior.
- `tests/checks/test_branch_status.py` — non-polling formatter / collection tests are unaffected.
- `pyproject.toml`, `tach.toml`, `.importlinter` — no dependency or layer changes.

## Implementation Steps

Three steps, each one commit, TDD-shaped:

1. **[step_1.md](./step_1.md)** — `_wait_for_ci` / `_wait_for_pr`: return elapsed `float` + deadline-aware sleep.
2. **[step_2.md](./step_2.md)** — `WaitContext` dataclass + `_format_wait_line` + optional `wait_context` kwarg on both formatters.
3. **[step_3.md](./step_3.md)** — Orchestrator parallel polling + server tool signature change (drop `wait_for_pr`, new defaults).

Steps 1 and 2 are independent and additive (no observable behavior change from the tool's perspective). Step 3 wires the pieces together and lands the breaking API change.

## Acceptance Criteria

- All three MCP code-quality checks pass: `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_pytest_check`, `mcp__tools-py__run_mypy_check`.
- `wait_for_pr` no longer in any signature, test, or docstring.
- `_DEFAULT_PR_TIMEOUT` removed.
- `check_branch_status` tool signature is exactly `(max_log_lines=300, ci_timeout=300, pr_timeout=0)`.
- Two parallel polls observably run concurrently (event-based test proves it).
- Wait line renders with state vocabulary `ok` / `fail` / `pending` / `missing`; per-side omission and full-line omission honored.
