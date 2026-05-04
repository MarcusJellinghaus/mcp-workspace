# Step 2 — `WaitContext` dataclass + `_format_wait_line` + formatter kwargs

**Reference:** [summary.md](./summary.md) — see "Implementation Steps".

## LLM Prompt

> Read `pr_info/steps/summary.md` first, then implement this step (`pr_info/steps/step_2.md`) in a single commit using TDD: write the rendering tests first, then add `WaitContext`, the `_format_wait_line` helper, and the new optional kwarg on both `BranchStatusReport.format_for_llm` and `BranchStatusReport.format_for_human`. Do not change `_wait_for_*`, `async_poll_branch_status`, or the server tool. After every edit run `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_mypy_check`, and `mcp__tools-py__run_pytest_check` (with `extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"]`). Commit with message `feat(branch_status): add WaitContext and Wait line rendering`.

## Scope (one commit)

Pure additive change in `branch_status.py` — `WaitContext` is unused so far (Step 3 wires it). All existing tests must keep passing because the new `wait_context` kwarg defaults to `None` and changes nothing when omitted.

## WHERE

| File | Change |
|------|--------|
| `src/mcp_workspace/checks/branch_status.py` | Add `WaitContext` dataclass, `_format_wait_line` helper, optional kwarg on both formatters |
| `tests/checks/test_branch_status_polling.py` | Add a `TestWaitLineRendering` class |

## WHAT

```python
@dataclass(frozen=True)
class WaitContext:
    pr_elapsed: Optional[float] = None    # None when pr_timeout was 0
    pr_timeout: int = 0
    ci_elapsed: Optional[float] = None    # None when ci_timeout was 0
    ci_timeout: int = 0


def _format_wait_line(
    report: BranchStatusReport,
    wait_context: Optional[WaitContext],
) -> Optional[str]:
    """Build the 'Wait: ...' line, or None when nothing to render."""


class BranchStatusReport:
    def format_for_llm(
        self,
        max_lines: int = 300,
        wait_context: Optional[WaitContext] = None,
    ) -> str: ...

    def format_for_human(
        self,
        wait_context: Optional[WaitContext] = None,
    ) -> str: ...
```

## HOW (integration)

- `WaitContext` placed below `CIStatus`, alongside `BranchStatusReport`.
- `_format_wait_line` is module-private (single underscore). Both formatters call it once and append the result if not `None`.
- In `format_for_llm`, append the Wait line **directly below the `Branch Status:` summary line** (between the existing `status_summary` and `GitHub Label:`).
- In `format_for_human`, insert the Wait line **between the `Base Branch: <name>` line and the existing blank line that precedes `"Branch Status Report"`** (placement A). The resulting order is: `Branch: <name>`, `Base Branch: <name>`, `Wait: ...` (only when `wait_context` provided), then blank line, then `Branch Status Report`. Keep it on a single line so the wording mirrors `format_for_llm` (Wait line directly under the summary line).

## ALGORITHM (`_format_wait_line`)

```
parts = []
if wait_context is None:                             return None
if wait_context.ci_timeout > 0 and wait_context.ci_elapsed is not None:
    state = ci_state(report.ci_status)               # PASSED→ok, FAILED→fail, else pending
    parts.append(f"ci={int(round(wait_context.ci_elapsed))}s {state}")
if wait_context.pr_timeout > 0 and wait_context.pr_elapsed is not None:
    state = "ok" if report.pr_found else "missing"
    parts.append(f"pr={int(round(wait_context.pr_elapsed))}s {state}")
return f"Wait: {', '.join(parts)}" if parts else None
```

CI-state mapping (private helper or inline `if/elif`):

```
PASSED          → ok
FAILED          → fail
PENDING         → pending
NOT_CONFIGURED  → pending
```

## DATA

- `WaitContext` fields exactly as listed (issue requirement). No extra fields.
- Wait line format: `Wait: ci=<N>s <state>, pr=<N>s <state>` — order is CI then PR; comma+space separator.
- Elapsed values rendered as integer seconds (`int(round(...))`) to keep the line compact.
- One-sided polling: omit the disabled side from the joined output. If both sides disabled, helper returns `None` and formatter appends nothing.

## Tests (in `tests/checks/test_branch_status_polling.py`, new `TestWaitLineRendering` class)

Each test builds a `BranchStatusReport` (use the existing `_make_report` style), constructs a `WaitContext`, calls `report.format_for_llm(wait_context=...)`, and asserts the substring on the rendered output:

- `test_wait_line_both_sides_ci_ok_pr_missing` — `ci_timeout=300, ci_elapsed=80, pr_timeout=300, pr_elapsed=300`, `pr_found=False`. Expect `"Wait: ci=80s ok, pr=300s missing"`.
- `test_wait_line_ci_fail_pr_ok` — CI failed, PR found. Expect `"Wait: ci=…s fail, pr=…s ok"`.
- `test_wait_line_ci_pending_when_status_not_configured` — `ci_status=NOT_CONFIGURED`. Expect substring `"ci=…s pending"`.
- `test_wait_line_omits_ci_side_when_ci_timeout_zero` — `ci_timeout=0`, `pr_timeout=120, pr_elapsed=10`, `pr_found=True`. Expect line is `"Wait: pr=10s ok"`, no `ci=` substring.
- `test_wait_line_omits_pr_side_when_pr_timeout_zero` — symmetric.
- `test_wait_line_absent_when_both_timeouts_zero` — empty `WaitContext()` produces no `Wait:` substring at all.
- `test_wait_line_absent_when_no_wait_context` — no `wait_context` kwarg passed to `format_for_llm`; output identical to current behavior (regression guard, LLM side).
- `test_format_for_human_unchanged_when_no_wait_context` — calling `format_for_human()` without `wait_context` produces output identical to the current implementation (regression guard, human side; symmetric to the LLM-side guard).
- `test_format_for_human_renders_same_wait_line` — pass `WaitContext(ci_timeout=60, ci_elapsed=10, …)` to `format_for_human`; assert the same `Wait: ci=10s ok` substring appears, and assert it sits between the `Base Branch:` line and the blank line preceding `Branch Status Report`.

## Definition of Done

- All three quality checks pass.
- `WaitContext` exported from the module (importable from `mcp_workspace.checks.branch_status`).
- All existing formatter tests in `tests/checks/test_branch_status.py` still pass unchanged (kwarg is optional).
- One commit produced.
