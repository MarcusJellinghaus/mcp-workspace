# Step 4 — Render `LINKED_VIA_PR` and PR-sourced `MISMATCH`

## Prompt for LLM

Read `pr_info/steps/summary.md` for full context on issue #316, then implement this
step only. This step depends on steps 1–3 being committed (the `closing_pr_candidate`
field and `LINKED_VIA_PR` status must already exist and be producible). Follow TDD:
write the tests first, confirm they fail for the right reason, then implement until
they pass. Run pylint, pytest (`-n auto`), and mypy; all must pass. Produce exactly
one commit.

Precondition: `src/mcp_workspace/checks/branch_status_rendering.py` must still define
`_format_linked_branch_line(report)` with its current `if/elif` chain over
`report.linked_branch_status` (`OK`, `MISMATCH`, `AMBIGUOUS`, `NOT_LINKED`, else
`UNKNOWN`), and `report.closing_pr_candidate` must exist on `BranchStatusReport`
(from step 3). If not, write one line to `pr_info/.blocked.txt` naming the mismatch
and stop.

## WHERE

- `src/mcp_workspace/checks/branch_status_rendering.py` — update
  `_format_linked_branch_line` only.
- `tests/checks/test_branch_status_linked_branch.py` — extend `_make_report`,
  `TestLinkedBranchRendering`, `TestLinkedBranchReviewGate`.

## WHAT

```python
def _format_linked_branch_line(report: "BranchStatusReport") -> Optional[str]:
    ...
```
No signature change — only the body's branching grows one case and the `MISMATCH`
case splits in two.

## HOW

- Add a `LinkedBranchStatus.LINKED_VIA_PR` branch, placed before the `MISMATCH`
  branch: names the current branch and the closing PR from
  `report.closing_pr_candidate` (always set when this status is reached, per step 3).
- Split the existing `MISMATCH` branch into:
  - branch-sourced (today's exact wording), when `report.linked_branches` is
    non-empty;
  - PR-sourced named, when `report.linked_branches` is empty and
    `report.closing_pr_candidate` is not `None` — wording must name the PR number and
    its `head_ref_name`, distinct from the branch-sourced wording (it must not say
    "issue links branch" since no Development-panel branch link exists);
  - PR-sourced generic (2+ non-matching candidates), when both are empty/`None` — no
    PR named, but still explains that no open closing PR matches either.
- Update the `NOT_LINKED` branch's text to also mention that an open PR with
  `Closes #N` satisfies the check, using `report.linked_branch_issue_number` for `N`
  when it is not `None` (omit that clause entirely when it is `None`, same guard
  style as the existing `issue` variable above it).
- Do not change `AMBIGUOUS` or `UNKNOWN` wording, `_review_gate_header`, or
  `linked_branch_blocks` — those are already correct from step 2.

## ALGORITHM

```
status = report.linked_branch_status
if status == NOT_CHECKED: return None
if status == OK: text = "OK ('<current>')"
elif status == LINKED_VIA_PR: text = "LINKED_VIA_PR — issue #N closed by PR #M ('<current>')"
elif status == MISMATCH and report.linked_branches: text = <today's branch-sourced wording>
elif status == MISMATCH and report.closing_pr_candidate: text = "MISMATCH — PR #M points at branch '<pr-branch>', not current branch '<current>' — ..."
elif status == MISMATCH: text = "MISMATCH — no linked branch and no open closing PR matches current branch '<current>' — ..."
elif status == AMBIGUOUS: text = <unchanged>
elif status == NOT_LINKED: text = "NOT_LINKED — ... links no branch and no open PR closes it — ..., or open a PR with 'Closes #N'"
else: text = <unchanged UNKNOWN wording>
return f"Linked Branch: {text}"
```

## DATA

No new data structures — reads the existing `report.closing_pr_candidate` field.
Output is still a single `Optional[str]` line, same contract as today.

## Tests to add/extend (`tests/checks/test_branch_status_linked_branch.py`)

- Extend the `_make_report` helper with an optional
  `closing_pr_candidate: Optional[ClosingPRRef] = None` parameter, passed through to
  the `BranchStatusReport(...)` constructor.
- In `TestLinkedBranchRendering`'s parametrized `test_state_renders_one_line`, add
  cases:
  - `LinkedBranchStatus.LINKED_VIA_PR` with `closing_pr_candidate=ClosingPRRef(10, "255-feature")`
    → substrings `["#255", "PR #10", "255-feature"]`.
  - `LinkedBranchStatus.MISMATCH` with empty `linked_branches` and
    `closing_pr_candidate=ClosingPRRef(10, "255-other")` → substrings
    `["PR #10", "255-other", "255-feature"]` (current branch name).
  - `LinkedBranchStatus.MISMATCH` with empty `linked_branches` and
    `closing_pr_candidate=None` → substring `["no open closing PR"]`, and assert
    `"PR #"` is **not** in the line (proves the generic path never fabricates a PR
    number).
  - `LinkedBranchStatus.NOT_LINKED` → add substring `"Closes #255"` to the existing
    expected list.
- Add a case to `TestLinkedBranchReviewGate.test_non_blocking_states_stay_clean` for
  `LinkedBranchStatus.LINKED_VIA_PR` (with a `closing_pr_candidate` set) → expect
  `"Review Gate: clean"`.
- Add a regression test asserting the branch-sourced `MISMATCH` wording (existing
  `255-old` fixture, no `closing_pr_candidate`) is unchanged byte-for-byte from the
  pre-step-4 wording, to lock in that the split didn't alter the original case.
