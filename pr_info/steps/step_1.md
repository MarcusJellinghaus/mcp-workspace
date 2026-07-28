# Step 1 — Missing-token degradation (port from fork), CI-only

**One commit: tests + implementation + all three checks passing.**

Implements Item 1 of `summary.md`. Ports the fork's missing-token handling into
`mcp_workspace.checks.branch_status`. **CI-only scope** — PR / label / feedback
fallbacks are untouched. This is the only change to the token-*absent* path;
the token-present path stays byte-for-byte identical.

## WHERE

- Implementation: `src/mcp_workspace/checks/branch_status.py`
- Tests: `tests/checks/test_branch_status.py`

## WHAT

1. **`CIStatus` enum** — add member:
   ```python
   UNAVAILABLE = "UNAVAILABLE"  # auth/token missing — CI truth unknown
   ```

2. **Module constant** (near `DEFAULT_LABEL` / `EMPTY_RECOMMENDATIONS`):
   ```python
   GITHUB_TOKEN_HINT = "no GitHub token; set GITHUB_TOKEN or add to config.toml"
   ```

3. **`_collect_ci_status(project_dir, branch_name, max_log_lines)`** — signature
   unchanged, still returns `tuple[CIStatus, Optional[str], List[str]]`. Add an
   early token gate as the **first** statement inside the function body.

4. Rendering in three existing places (inline, matching the fork — no helper):
   - `format_for_human`: CI icon map + CI status line.
   - `format_for_llm`: `status_summary` line.
   - `_generate_recommendations`.

## HOW (integration points)

- Add import at top of `branch_status.py`:
  ```python
  from mcp_workspace.config import get_github_token
  ```
  (`get_github_token` already exists at `src/mcp_workspace/config.py:45`.)
- No signature changes anywhere; no new call sites. The gate lives entirely
  inside `_collect_ci_status`.

## ALGORITHM (token gate — first lines of `_collect_ci_status`)

```
if get_github_token() is None:
    logger.info("GitHub token not configured — CI status unavailable")
    return CIStatus.UNAVAILABLE, None, []
# ... existing try/CIResultsManager logic unchanged below ...
```

Rendering additions:

```
# format_for_human: ci_icon_map
CIStatus.UNAVAILABLE: "\U0001f512"   # 🔒 lock

# format_for_human: after building the CI status line
ci_line = f"CI Status: {ci_icon} {self.ci_status.value}"
if self.ci_status == CIStatus.UNAVAILABLE:
    ci_line += f" — {GITHUB_TOKEN_HINT}"   # em dash
lines.append(ci_line)

# format_for_llm: after status_summary is built (before PR suffixes)
if self.ci_status == CIStatus.UNAVAILABLE:
    status_summary += f" ({GITHUB_TOKEN_HINT})"

# _generate_recommendations: extend the CI branch
elif ci_status == CIStatus.NOT_CONFIGURED:
    recommendations.append("Configure CI pipeline")
elif ci_status == CIStatus.UNAVAILABLE:
    recommendations.append(f"Set a GitHub token ({GITHUB_TOKEN_HINT})")
```

## DATA

- `_collect_ci_status` return unchanged: `(CIStatus.UNAVAILABLE, None, [])` on
  missing token.
- `format_for_human` / `format_for_llm` return `str` (one extra hint fragment
  when UNAVAILABLE).
- `_generate_recommendations` returns `List[str]` (one extra entry when
  UNAVAILABLE).

## TESTS (write first, TDD)

Add to `tests/checks/test_branch_status.py`. Import `GITHUB_TOKEN_HINT`.

1. `test_ci_status_enum_has_unavailable` — `CIStatus.UNAVAILABLE == "UNAVAILABLE"`.
2. `test_collect_ci_status_no_token_returns_unavailable` — patch
   `mcp_workspace.checks.branch_status.get_github_token` → `None` and
   `...CIResultsManager` as a mock; assert result is
   `(CIStatus.UNAVAILABLE, None, [])` and **the manager was never constructed**
   (early return precedes any network/manager work).
3. `test_collect_ci_status_with_token_still_works` — patch `get_github_token` →
   `"tok"`; existing happy path still reached (manager constructed).
4. `test_format_for_human_unavailable_status` — a report with
   `ci_status=UNAVAILABLE` renders
   `f"CI Status: \U0001f512 UNAVAILABLE — {GITHUB_TOKEN_HINT}"`.
5. `test_format_for_llm_unavailable_status` — summary line (line index 1)
   contains `CI=UNAVAILABLE` and `f"({GITHUB_TOKEN_HINT})"`.
6. `test_recommendations_unavailable_includes_token_hint` — `_generate_
   recommendations({"ci_status": CIStatus.UNAVAILABLE, ...})` contains
   `f"Set a GitHub token ({GITHUB_TOKEN_HINT})"` and excludes the
   "Configure CI pipeline" / "Ready to merge" entries.

## CHECKS

Run and pass: `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_pytest_check`
(`extra_args=["-n","auto","-m","not git_integration and not claude_cli_integration
and not claude_api_integration and not formatter_integration and not
github_integration and not langchain_integration"]`), `mcp__tools-py__run_mypy_check`.

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`. Implement Step 1
> only: the CI-only missing-token degradation in
> `src/mcp_workspace/checks/branch_status.py`. Follow TDD — first add the six
> tests described to `tests/checks/test_branch_status.py`, then implement:
> `CIStatus.UNAVAILABLE`, the `GITHUB_TOKEN_HINT` constant, the
> `from mcp_workspace.config import get_github_token` import, the early token
> gate as the first statement of `_collect_ci_status` (returning
> `(CIStatus.UNAVAILABLE, None, [])`), and the inline UNAVAILABLE rendering in
> `format_for_human`, `format_for_llm`, and `_generate_recommendations` exactly
> as specified. Do NOT touch PR/label/feedback paths and do NOT change any
> signature. Use MCP `mcp__workspace__*` tools for file ops. After every edit run
> `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_pytest_check` (with the
> `-n auto` + `not <integration>` exclusions from CLAUDE.md), and
> `mcp__tools-py__run_mypy_check`; fix all issues before finishing. Produce
> exactly one commit.
