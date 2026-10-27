# Step 2 — 403/404 on alerts → `skipped`, rendered as "alerts not checked"

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_2.md` only.
> TDD: update/add the tests first, then the code. Use the MCP tools from CLAUDE.md.
> Run pylint, pytest (`extra_args: ["-n", "auto"]`), mypy and vulture; all must pass.
> Whitelist a field in `vulture_whitelist.py` only if vulture flags it.
> Run `run_format_code`, then make exactly one commit.
> If `AlertData` does not exist in `src/mcp_workspace/github_operations/pr_types.py`
> (step 1 not done), write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/github_operations/pr_types.py`
- `src/mcp_workspace/github_operations/_pr_feedback_sources.py`
- `src/mcp_workspace/github_operations/pr_feedback_mixin.py`
- `src/mcp_workspace/checks/pr_feedback.py`
- `tests/github_operations/test_pr_feedback_mixin.py`
- `tests/checks/test_branch_status_pr_feedback.py`

## Tests first

`tests/github_operations/test_pr_feedback_mixin.py`
- Replace `test_code_scanning_403_silent_skip` and `test_code_scanning_500_unavailable`
  with one parametrized test `test_code_scanning_error_routing(exc, section)`:

  | exc | section |
  |---|---|
  | `GithubException(403, {"message": "forbidden"}, None)` | `"skipped"` |
  | `GithubException(404, {"message": "no analysis found"}, None)` | `"skipped"` |
  | `GithubException(403, {"message": "API rate limit exceeded"}, {"x-ratelimit-remaining": "0", "x-ratelimit-resource": "core", "x-ratelimit-reset": "<now+600>"})` (headers as in `test_diagnostics.py::test_remaining_zero_lowercase_headers`) | `"unavailable"` |
  | `GithubException(500, {"message": "server error"}, None)` | `"unavailable"` |

  Assert `result["alerts"] == []`, `result[section]["alerts"] is exc`, and that the
  other dict has no `"alerts"` key.
- All-empty test: add `assert result["skipped"] == {}`.
- pr_number=0 test (`_empty_pr_feedback` path): add `assert result["skipped"] == {}`.

`tests/checks/test_branch_status_pr_feedback.py`
- `_empty_feedback()` gains `"skipped": {}`.
- New `class TestSkipped`:
  - clean: `feedback["skipped"] = {"alerts": GithubException(403, {"message": "x"}, None)}`
    → `result == "Reviews: clean (0 unresolved threads, alerts not checked: 403)"`.
  - non-clean ordering: one thread + `unavailable={"threads": GithubException(500, …)}` +
    skipped 404 → `"[skipped] alerts not checked (404)"` is a line, and its index is
    greater than the `[unavailable]` line's index.
  - cap: 25 threads + skipped 403 → `"[skipped] alerts not checked (403)"` still present.
- `TestCollectPrFeedbackUndeterminable`: add `test_skipped_alerts_neither_blocks_nor_undeterminable`
  (skipped 403 only → `blocks_merge is False`, `undeterminable is False`).
- `TestCollectPrFeedbackUndeterminable`: add `test_alert_blocks_merge`
  (`feedback["alerts"] = [_alert()]`, no threads → `blocks_merge is True`,
  `undeterminable is False`).

## WHAT / HOW

`pr_types.py` — `PRFeedback` gains `skipped: dict[str, Exception]` after `unavailable`.

`_pr_feedback_sources.py` — `fetch_code_scanning_alerts(...) -> list["AlertData"]`:
remove the `try/except GithubException` and the 403 debug log; docstring
`Raises: GithubException: Any API error (caller classifies).`

`pr_feedback_mixin.py`
- `from ._diagnostics import format_rate_limit_error`.
- `_empty_pr_feedback()` adds `"skipped": {}`.
- `get_pr_feedback`: `skipped: dict[str, Exception] = {}`; alerts block below;
  return dict adds `"skipped": skipped`. Docstring: 403/404 on alerts (not rate-limited)
  go into `skipped`, other failures into `unavailable`.

`checks/pr_feedback.py` — `format_pr_feedback` reads `skipped = feedback["skipped"]`.
`_BLOCKING_RELEVANT_SECTIONS` and `collect_pr_feedback` are unchanged.

## ALGORITHM

Mixin:
```
try:
    alerts = fetch_code_scanning_alerts(self, pr_number)
except Exception as e:  # pylint: disable=broad-exception-caught  # one section failure must not abort
    alerts = []
    if getattr(e, "status", None) in (403, 404) and format_rate_limit_error(e) is None:
        logger.debug(...); skipped["alerts"] = e
    else:
        logger.warning(...); unavailable["alerts"] = e
```
Formatter:
```
if not blocking and not all_comments and not unavailable:          # unchanged condition
    note = f"alerts not checked: {getattr(skipped['alerts'], 'status', None)}" if "alerts" in skipped else "0 alerts"
    return f"Reviews: clean (0 unresolved threads, {note})"
...after the [unavailable] loop:
for section, exc in skipped.items():
    lines.append(f"[skipped] {section} not checked ({getattr(exc, 'status', None)})")
```

## DATA

- `fetch_code_scanning_alerts` → `list[AlertData]`; raises on any error.
- `PRFeedback["skipped"]` → `dict[str, Exception]`, only key ever set: `"alerts"`.
