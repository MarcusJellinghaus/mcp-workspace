# Summary — #357 PR feedback: code-scanning alerts never returned

## Problem

`fetch_code_scanning_alerts` queries `code-scanning/alerts?ref=refs/pull/{N}/head`.
CodeQL stores no PR alerts under that ref, so the result is always `[]` and
`check_branch_status` reports `Reviews: clean (…, 0 alerts)` while CodeQL fails.
A 403 is also silently rendered as `0 alerts`, and a 404 makes the verdict UNKNOWN.

## Architectural / design changes

1. **Query by PR, open alerts only.** The request becomes
   `GET /repos/{owner}/{repo}/code-scanning/alerts` with
   `parameters={"pr": N, "state": "open", "per_page": 100}`, one page only
   (one alert already blocks; rendering is capped at 20 items).
2. **Typed alert shape.** New `AlertData` TypedDict in `pr_types.py`
   (`number`, `rule_id`, `rule_description`, `message`, `path`, `line`), replacing
   `dict[str, Any]`. `number` and `rule_id` are needed downstream (mcp_coder#1342).
3. **Alert rendering:** `[alert] [alert_number=N] rule_id: message @ path:line`
   (path only when `line` is None). `rule_description` is carried but not rendered.
   The message is rendered unfenced, deliberately — alerts have no human author.
4. **New `skipped` category on `PRFeedback`** (`skipped: dict[str, Exception]`),
   next to `unavailable`:
   - `fetch_code_scanning_alerts` no longer swallows anything; it raises every error.
   - `get_pr_feedback` routes the error in one condition: status 403/404 (via
     `getattr(e, "status", None)`) **and not** a rate limit
     (`format_rate_limit_error(e) is None`) → `skipped["alerts"]`; everything else
     → `unavailable["alerts"]`.
   - `skipped` feeds neither `blocks_merge` nor `undeterminable`;
     `_BLOCKING_RELEVANT_SECTIONS` is unchanged.
5. **Skipped rendering:**
   - Clean path (condition unchanged — `skipped` never makes a report non-clean):
     `Reviews: clean (0 unresolved threads, alerts not checked: 403)`.
   - Non-clean path: `[skipped] alerts not checked (403)` after the
     `[unavailable]` lines, outside the 20-item cap.

KISS choices: no pagination; no `isinstance` check (the `getattr` status read
covers non-GitHub errors); clean-line note is alerts-specific (only alerts can be
skipped); a missing `number` in GitHub's payload raises `KeyError`, which lands in
`unavailable` (fail closed) — no Optional/fallback.

## Files modified

No new source modules or folders.

| File | Change |
|------|--------|
| `src/mcp_workspace/github_operations/pr_types.py` | `AlertData`; `PRFeedback.alerts: list[AlertData]`; `PRFeedback.skipped` |
| `src/mcp_workspace/github_operations/_pr_feedback_sources.py` | `fetch_code_scanning_alerts`: new params, `AlertData` shape, raises all errors |
| `src/mcp_workspace/github_operations/pr_feedback_mixin.py` | `_empty_pr_feedback` + `get_pr_feedback`: `skipped` routing |
| `src/mcp_workspace/checks/pr_feedback.py` | `format_pr_feedback`: alert line, clean-line note, `[skipped]` lines |
| `tests/github_operations/test_pr_feedback_mixin.py` | fixtures, exact params, `AlertData` fields, parametrized error routing |
| `tests/checks/test_branch_status_pr_feedback.py` | `_empty_feedback`, `_alert`, `TestAlerts`, `TestSkipped`, collect test |
| `vulture_whitelist.py` | only if vulture flags a new TypedDict field |

## Steps

- **Step 1** — Query by PR + `AlertData` shape + new alert line (one commit).
- **Step 2** — 403/404 → `skipped`: fetch raises, mixin routes, formatter renders (one commit).
