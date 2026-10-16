# Step 2 — Add `LINKED_VIA_PR` status

## Prompt for LLM

Read `pr_info/steps/summary.md` for full context on issue #316, then implement this
step only. This step depends on step 1 being committed (it does not call the new
mixin method yet — it only adds the enum value and updates the single predicate that
decides blocking). Follow TDD: write the tests first, confirm they fail for the right
reason, then implement until they pass. Run pylint, pytest (`-n auto`), and mypy; all
must pass. Produce exactly one commit.

Precondition: `src/mcp_workspace/checks/branch_status_rendering.py` must still define
`LinkedBranchStatus` as a `str, Enum` with members `OK`, `MISMATCH`, `AMBIGUOUS`,
`NOT_LINKED`, `UNKNOWN`, `NOT_CHECKED`, and `linked_branch_blocks` must still be the
single predicate used by `_review_gate_header`. If not, write one line to
`pr_info/.blocked.txt` naming the mismatch and stop.

## WHERE

- `src/mcp_workspace/checks/branch_status_rendering.py` — add enum member, update
  `linked_branch_blocks`.
- `tests/checks/test_branch_status_linked_branch.py` — extend
  `TestLinkedBranchBlocks`.

## WHAT

```python
class LinkedBranchStatus(str, Enum):
    OK = "OK"
    LINKED_VIA_PR = "LINKED_VIA_PR"  # new
    MISMATCH = "MISMATCH"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_LINKED = "NOT_LINKED"
    UNKNOWN = "UNKNOWN"
    NOT_CHECKED = "NOT_CHECKED"


def linked_branch_blocks(status: LinkedBranchStatus) -> bool:
    ...
```

## HOW

- Add `LINKED_VIA_PR = "LINKED_VIA_PR"` to `LinkedBranchStatus`, placed right after
  `OK` (it is the second non-blocking state).
- Change `linked_branch_blocks` to return `False` for
  `(LinkedBranchStatus.OK, LinkedBranchStatus.NOT_CHECKED, LinkedBranchStatus.LINKED_VIA_PR)`
  instead of the current two-element tuple. No other function in this module needs a
  code change — `_review_gate_header` already calls `linked_branch_blocks(...)`
  generically.
- Do not touch `_format_linked_branch_line`, `_review_gate_header`,
  `BranchStatusReport`, or `_collect_linked_branch_status` in this step — `LINKED_VIA_PR`
  is not yet producible by the collector and not yet rendered; that is step 3 and
  step 4. This step only makes the enum value exist and correctly classified as
  non-blocking.

## ALGORITHM

N/A — single-line tuple-membership change.

## DATA

No data-shape change. `linked_branch_blocks(LinkedBranchStatus.LINKED_VIA_PR)` must
return `False`.

## Tests to add (`tests/checks/test_branch_status_linked_branch.py`)

In `TestLinkedBranchBlocks`, add a parametrize case:
`(LinkedBranchStatus.LINKED_VIA_PR, False)`.
