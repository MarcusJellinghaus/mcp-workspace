# Step 3 — Orchestrator parallel polling + server tool signature change

**Reference:** [summary.md](./summary.md) — see "Implementation Steps".

## LLM Prompt

> Read `pr_info/steps/summary.md` first, then implement this step (`pr_info/steps/step_3.md`) in a single commit using TDD: update polling tests + server-tool tests first, then change `async_poll_branch_status` and `check_branch_status`. After every edit run `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_mypy_check`, and `mcp__tools-py__run_pytest_check` (with `extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"]`). Confirm `wait_for_pr` and `_DEFAULT_PR_TIMEOUT` no longer appear anywhere in the codebase. Commit with message `feat(branch_status): parallel polling, drop wait_for_pr, default ci_timeout=300`.

## Scope (one commit)

Land the breaking API change. After this step, the issue is fully implemented.

## WHERE

| File | Change |
|------|--------|
| `src/mcp_workspace/checks/branch_status.py` | Remove `_DEFAULT_PR_TIMEOUT`; rewrite `async_poll_branch_status` |
| `src/mcp_workspace/server.py` | `check_branch_status`: drop `wait_for_pr`, change defaults, params-only docstring |
| `tests/checks/test_branch_status_polling.py` | Drop `wait_for_pr`; drop `_DEFAULT_PR_TIMEOUT` test; replace sequential test with event-based parallel proof |
| `tests/test_server.py` | Drop `wait_for_pr` from server-tool tests; assert new defaults |

## WHAT

### `async_poll_branch_status` new signature

```python
async def async_poll_branch_status(
    project_dir: Path,
    max_log_lines: int = 300,
    ci_timeout: int = 0,
    pr_timeout: int = 0,
) -> str:
```

(Orchestrator default stays `0` — the policy default `300` lives on the MCP tool wrapper.)

### `check_branch_status` new signature

```python
@mcp.tool()
@log_function_call
async def check_branch_status(
    max_log_lines: int = 300,
    ci_timeout: int = 300,
    pr_timeout: int = 0,
) -> str:
    """Check comprehensive branch status: git state, CI, PR, tasks.

    Args:
        max_log_lines: Maximum CI log lines to include (default 300).
        ci_timeout: Seconds to poll for CI completion. 0 disables polling.
        pr_timeout: Seconds to poll for PR existence. 0 disables polling.

    Returns:
        Formatted branch status report for LLM consumption.
    """
```

Strict params-only — no parallelism prose.

## HOW (integration)

- Remove the `_DEFAULT_PR_TIMEOUT` constant from `branch_status.py`.
- `needs_remote = ci_timeout > 0 or pr_timeout > 0` (was `wait_for_pr or ci_timeout > 0`).
- Run polls in parallel via `asyncio.gather` — call **both** helpers unconditionally; they early-exit on `timeout <= 0`.
- Build `WaitContext` from the gather results; pass to `format_for_llm`.
- Server tool forwards explicit kwargs (no `wait_for_pr`).

## ALGORITHM (`async_poll_branch_status` rewrite)

```
branch = get_current_branch_name(project_dir)
if branch is None: return collect_branch_status(...).format_for_llm()

needs_remote   = ci_timeout > 0 or pr_timeout > 0
remote_present = remote_branch_exists(...) if needs_remote else True

skip_msg, wait_ctx = None, None
if needs_remote and not remote_present:
    skip_msg = "Push branch to remote before waiting for PR or CI"
elif needs_remote:
    ci_elapsed, pr_elapsed = await asyncio.gather(
        _wait_for_ci(project_dir, branch, ci_timeout),
        _wait_for_pr(project_dir, branch, pr_timeout),
    )
    wait_ctx = WaitContext(
        ci_elapsed = ci_elapsed if ci_timeout > 0 else None,
        ci_timeout = ci_timeout,
        pr_elapsed = pr_elapsed if pr_timeout > 0 else None,
        pr_timeout = pr_timeout,
    )

report = collect_branch_status(...)
if skip_msg: report = replace(report, recommendations=[skip_msg, *report.recommendations])
return report.format_for_llm(wait_context=wait_ctx)
```

## DATA

- `WaitContext` constructed only inside `async_poll_branch_status`.
- `collect_branch_status` and `BranchStatusReport` remain polling-agnostic.
- Server tool defaults: `max_log_lines=300, ci_timeout=300, pr_timeout=0`.
- Wall-clock when both polling: `max(ci_timeout, pr_timeout)`, not their sum.

## Tests

### `tests/checks/test_branch_status_polling.py` — `TestAsyncPollBranchStatus`

Drop `wait_for_pr=...` from every call. Update / replace tests as follows:

- **Delete** `test_wait_for_pr_uses_default_pr_timeout` (constant removed).
- **Update** `test_defaults_call_no_helpers_and_skip_remote_check` — with new defaults the orchestrator default still has `ci_timeout=0, pr_timeout=0`, so behavior unchanged (this test stays). Just drop any `wait_for_pr` reference.
- **Update** `test_wait_for_pr_uses_explicit_pr_timeout` → rename to `test_pr_timeout_propagates_to_helper`; call `async_poll_branch_status(project_dir, pr_timeout=120)`; assert `mock_wait_pr` awaited with `120`.
- **Update** `test_wait_for_pr_skipped_when_no_remote_branch` → call with `pr_timeout=120`; assert recommendation injected and helpers not called.
- **Update** `test_both_flags_no_remote_branch_emits_recommendation_once` → call with `ci_timeout=30, pr_timeout=120`.
- **Update** `test_no_branch_skips_helpers_and_remote_check` → call with `ci_timeout=30, pr_timeout=120`.
- **Replace** `test_pr_wait_runs_before_ci_wait_then_collect` with `test_polls_run_in_parallel`:
  ```
  release = asyncio.Event()
  ci_started, pr_started = asyncio.Event(), asyncio.Event()

  async def fake_wait_ci(*_a, **_kw): ci_started.set(); await release.wait(); return 0.0
  async def fake_wait_pr(*_a, **_kw): pr_started.set(); await release.wait(); return 0.0

  patch _wait_for_ci, _wait_for_pr, collect_branch_status, get_current_branch_name, remote_branch_exists
  task = asyncio.create_task(async_poll_branch_status(project_dir, ci_timeout=30, pr_timeout=30))
  await asyncio.wait_for(ci_started.wait(), timeout=1)
  await asyncio.wait_for(pr_started.wait(), timeout=1)   # both started before either returned
  release.set()
  await task
  ```
- **Add** `test_wait_context_built_from_elapsed_values`:
  ```
  Patch helpers to return 12.3 (ci) and 7.7 (pr); patch format_for_llm on the report instance to capture kwargs;
  call async_poll_branch_status(project_dir, ci_timeout=30, pr_timeout=30);
  assert captured wait_context.ci_elapsed == 12.3, .pr_elapsed == 7.7, both timeouts == 30.
  ```
- **Add** `test_wait_context_pr_side_none_when_pr_timeout_zero`:
  ```
  Call with ci_timeout=30, pr_timeout=0; assert WaitContext.pr_elapsed is None and ci_elapsed is the helper's return.
  ```

### `tests/test_server.py` — `TestCheckBranchStatusTool`

- **Update** `test_check_branch_status_defaults`:
  - Drop the `wait_for_pr=False` kwarg from the asserted forwarding call.
  - Change asserted defaults to `max_log_lines=300, ci_timeout=300, pr_timeout=0`.
- **Update** `test_check_branch_status_with_polling_params`:
  - Drop `wait_for_pr=True` from the call and from the asserted forwarding call.
- `test_check_branch_status_no_project_dir` — no change needed.

## Verification

After this step:

- `grep -r 'wait_for_pr\|_DEFAULT_PR_TIMEOUT' src/ tests/` returns nothing.
- `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_mypy_check`, `mcp__tools-py__run_pytest_check` all green.

## Definition of Done

- All three quality checks pass.
- The MCP tool exposes exactly three parameters: `max_log_lines`, `ci_timeout`, `pr_timeout`.
- Event-based test proves both polls are running in parallel before either returns.
- One commit produced.
