# Step 2 — Opt-in review-gate header (three-state, both formatters)

**One commit: tests + implementation + all three checks passing.**

Implements Item 2 of `summary.md`. Adds a three-state review-gate header,
rendered only when the effective flag is true, in **both** `format_for_human`
and `format_for_llm`. Text signal only — no exception, no exit code. Depends on
Step 1 (`CIStatus.UNAVAILABLE` must exist). This step works entirely at the
report/formatter level and is fully testable without any server wiring
(Step 3 does the wiring).

## WHERE

- Implementation: `src/mcp_workspace/checks/branch_status.py`
- Tests: `tests/checks/test_branch_status.py`

## WHAT

1. **Shared helper** (module-level, next to the existing `_format_wait_line`):
   ```python
   def _review_gate_header(
       report: "BranchStatusReport",
       fail_on_reviews: bool,
   ) -> Optional[str]:
       ...
   ```
   Returns the header line, or `None` when the gate is off. Pure function of
   `report.ci_status`, `report.pr_feedback_blocks_merge`, and the flag —
   **no token lookup** (reuses `ci_status == UNAVAILABLE` as the no-token signal).

2. **`format_for_human`** — add parameter `fail_on_reviews: bool = False`; when
   the helper returns a line, insert it near the top (right after the
   `Branch Status Report` header block, before the PR section).

3. **`format_for_llm`** — add parameter `fail_on_reviews: bool = False`; when the
   helper returns a line, insert it as a top line (e.g. directly after the
   `status_summary` line) so truncation can never hide it.

## HOW (integration points)

- Both formatters take a plain `bool` (already-resolved value). The
  `Optional[bool]` tri-state is introduced only in Step 3 at the tool boundary.
- Header strings are fixed and greppable (for the #1068 parser):
  `"Review Gate: BLOCKED (reviews)"`, `"Review Gate: clean"`,
  `"Review Gate: UNKNOWN (no token)"`.
- No change to any existing default behaviour: with `fail_on_reviews=False`
  (the default) the helper returns `None` and output is byte-for-byte unchanged.

## ALGORITHM (`_review_gate_header`)

```
if not fail_on_reviews:
    return None
if report.ci_status == CIStatus.UNAVAILABLE:   # checked FIRST — never clean/BLOCKED
    return "Review Gate: UNKNOWN (no token)"
if report.pr_feedback_blocks_merge:            # pr_feedback only, never mergeable_state
    return "Review Gate: BLOCKED (reviews)"
return "Review Gate: clean"
```

Insertion (both formatters):
```
header = _review_gate_header(self, fail_on_reviews)
if header is not None:
    lines.append(header)   # placed near the top, above truncatable body
```

## DATA

- `_review_gate_header` → `Optional[str]` (one of the three fixed strings, or
  `None`).
- `format_for_human` / `format_for_llm` → `str`, with at most one extra line.

## TESTS (write first, TDD)

Add to `tests/checks/test_branch_status.py`. Build reports via the existing
report factory/helper used in that file.

1. `test_review_gate_absent_when_off` — `fail_on_reviews=False` (default): output
   of both formatters contains no `"Review Gate:"` substring (additive guarantee).
2. `test_review_gate_blocked` — `pr_feedback_blocks_merge=True`, token present
   (`ci_status != UNAVAILABLE`), `fail_on_reviews=True`: both formatters contain
   `"Review Gate: BLOCKED (reviews)"`.
3. `test_review_gate_clean` — `pr_feedback_blocks_merge=False`, token present,
   `fail_on_reviews=True`: both formatters contain `"Review Gate: clean"`.
4. `test_review_gate_unknown_no_token` — `ci_status=UNAVAILABLE`,
   `fail_on_reviews=True`: both formatters contain
   `"Review Gate: UNKNOWN (no token)"` and contain neither
   `"Review Gate: clean"` nor `"Review Gate: BLOCKED"`.
5. `test_review_gate_unknown_wins_over_blocks` — `ci_status=UNAVAILABLE` **and**
   `pr_feedback_blocks_merge=True`, `fail_on_reviews=True`: header is
   `"UNKNOWN (no token)"` (UNAVAILABLE precedence), never `BLOCKED`.
6. `test_review_gate_helper_returns_none_when_off` — direct unit test of
   `_review_gate_header(report, False) is None`.

## CHECKS

Run and pass all three MCP checks (same invocation as Step 1). Confirm
`branch_status.py` stays under the 750-line limit (`mcp-coder check file-size`).

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`. Implement Step 2
> only: the opt-in three-state review-gate header. Follow TDD — first add the six
> tests to `tests/checks/test_branch_status.py`, then implement the module-level
> `_review_gate_header(report, fail_on_reviews) -> Optional[str]` helper (next to
> `_format_wait_line`) using exactly the branch order in the step (UNAVAILABLE
> checked first, then `pr_feedback_blocks_merge`, else clean; no token lookup),
> and add a `fail_on_reviews: bool = False` parameter to both `format_for_human`
> and `format_for_llm`, inserting the header near the top of each. Header strings
> must be exactly `"Review Gate: BLOCKED (reviews)"`, `"Review Gate: clean"`,
> `"Review Gate: UNKNOWN (no token)"`. Blocking must key off
> `pr_feedback_blocks_merge` ONLY — never `mergeable_state`. Default behaviour
> (`fail_on_reviews=False`) must be byte-for-byte unchanged. Use MCP
> `mcp__workspace__*` tools. After every edit run the three
> `mcp__tools-py__run_*` checks (pytest with the `-n auto` + `not <integration>`
> exclusions) and fix all issues. Produce exactly one commit.
