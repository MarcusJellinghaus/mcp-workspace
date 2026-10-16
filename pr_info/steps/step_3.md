# Step 3 — Resolve the closing-PR fallback in `_collect_linked_branch_status`

## Prompt for LLM

Read `pr_info/steps/summary.md` for full context on issue #316, then implement this
step only. This step depends on steps 1 and 2 being committed. Follow TDD: write the
tests first, confirm they fail for the right reason, then implement until they pass.
Run pylint, pytest (`-n auto`), and mypy; all must pass. Produce exactly one commit.

Precondition: `src/mcp_workspace/checks/branch_status.py` must still define
`_collect_linked_branch_status` with signature
`(project_dir: Path, branch_name: str) -> tuple[LinkedBranchStatus, tuple[str, ...], Optional[int]]`,
calling `IssueBranchManager(...).get_linked_branches_or_none(issue_number)`, and
`collect_branch_status` must still unpack its result into three names
(`linked_branch_status`, `linked_branches`, `linked_branch_issue_number`) before
building `BranchStatusReport`. If not, write one line to `pr_info/.blocked.txt`
naming the mismatch and stop.

## WHERE

- `src/mcp_workspace/checks/branch_status.py` — add a field to `BranchStatusReport`;
  rewrite `_collect_linked_branch_status`; update its one call site in
  `collect_branch_status`.
- `tests/checks/test_branch_status_linked_branch.py` — extend
  `TestCollectLinkedBranchStatus`, `TestLinkedBranchWiring`, and
  `TestLinkedBranchSuppressesMergeVerdict`.
- `tests/checks/test_branch_status.py` — update ten existing 3-tuple mocks of
  `_collect_linked_branch_status` to 4-tuples.

## WHAT

```python
@dataclass(frozen=True)
class BranchStatusReport:
    ...
    closing_pr_candidate: Optional[ClosingPRRef] = None


def _collect_linked_branch_status(
    project_dir: Path, branch_name: str
) -> tuple[LinkedBranchStatus, tuple[str, ...], Optional[int], Optional[ClosingPRRef]]:
    ...
```

## HOW

- Import `ClosingPRRef` from `mcp_workspace.github_operations.issues` (added to that
  package's exports in step 1) into `branch_status.py`.
- Add `closing_pr_candidate: Optional[ClosingPRRef] = None` as the last field on
  `BranchStatusReport`, after `last_automated_note`.
- `_collect_linked_branch_status` now calls
  `manager.get_linked_branch_and_closing_prs_or_none(issue_number)` instead of
  `get_linked_branches_or_none`, and returns a 4-tuple (old 3-tuple plus the
  candidate). All existing early-return paths (`NOT_CHECKED` for no issue number,
  `UNKNOWN` for `None` result or any exception) gain a trailing `None` for the new
  slot — no other logic in those paths changes.
- All "which PR is worth naming" decisions are made here, not in the renderer: the
  function always resolves the field down to 0 or 1 `ClosingPRRef` before returning.
- In `collect_branch_status`, change the unpacking line to
  `(linked_branch_status, linked_branches, linked_branch_issue_number, closing_pr_candidate) = _collect_linked_branch_status(...)`
  and pass `closing_pr_candidate=closing_pr_candidate` into the `BranchStatusReport(...)`
  constructor call.
- `_LINKED_BRANCH_BLOCKS_KEY` / `_generate_recommendations` need no change — they
  already key off `linked_branch_status` alone via `linked_branch_blocks`, which
  step 2 already made correct for `LINKED_VIA_PR`.

## ALGORITHM

```
issue_number = extract_issue_number_from_branch(branch_name)
if issue_number is None: return (NOT_CHECKED, (), None, None)

try: result = IssueBranchManager(project_dir).get_linked_branch_and_closing_prs_or_none(issue_number)
except Exception: return (UNKNOWN, (), issue_number, None)
if result is None: return (UNKNOWN, (), issue_number, None)
branches, closing_prs = result

if len(branches) > 1: return (AMBIGUOUS, tuple(branches), issue_number, None)
if len(branches) == 1:
    state = OK if branches[0] == branch_name else MISMATCH
    return (state, tuple(branches), issue_number, None)

# branches is empty: fall back to closing PRs
matches = [pr for pr in closing_prs if pr.head_ref_name == branch_name]
if matches: return (LINKED_VIA_PR, (), issue_number, matches[0])
if not closing_prs: return (NOT_LINKED, (), issue_number, None)
if len(closing_prs) == 1: return (MISMATCH, (), issue_number, closing_prs[0])
return (MISMATCH, (), issue_number, None)  # 2+ non-matching candidates: generic
```

## DATA

- Return type: `tuple[LinkedBranchStatus, tuple[str, ...], Optional[int], Optional[ClosingPRRef]]`.
- `closing_pr_candidate` is non-`None` only for `LINKED_VIA_PR` (the matching PR) and
  for a `MISMATCH` sourced from exactly one non-matching closing PR (that PR). It is
  always `None` for `OK`, `AMBIGUOUS`, `NOT_LINKED`, `UNKNOWN`, `NOT_CHECKED`, and for
  a branch-sourced `MISMATCH`.

## Tests to add/extend (`tests/checks/test_branch_status_linked_branch.py`)

Rename/retarget the mocked attribute in `TestCollectLinkedBranchStatus` from
`get_linked_branches_or_none` to `get_linked_branch_and_closing_prs_or_none`, and
change its `return_value` to a `(branches, closing_prs)` tuple (or `None`). Extend the
parametrized matrix to cover, in addition to the existing five cases (now expressed as
`(branches, [])` inputs with a trailing `None` expected):

- `(["255-feature"], [])` → `(OK, ("255-feature",), 255, None)`
- `(["255-old"], [])` → `(MISMATCH, ("255-old",), 255, None)`
- `(["255-a", "255-b"], [])` → `(AMBIGUOUS, ("255-a", "255-b"), 255, None)`
- `([], [])` → `(NOT_LINKED, (), 255, None)`
- `([], [ClosingPRRef(10, "255-feature")])` →
  `(LINKED_VIA_PR, (), 255, ClosingPRRef(10, "255-feature"))`
- `([], [ClosingPRRef(10, "255-other")])` →
  `(MISMATCH, (), 255, ClosingPRRef(10, "255-other"))`
- `([], [ClosingPRRef(10, "255-other"), ClosingPRRef(11, "255-other2")])` →
  `(MISMATCH, (), 255, None)`
- `(["255-old"], [ClosingPRRef(10, "255-feature")])` →
  `(MISMATCH, ("255-old",), 255, None)` — proves branch link wins over a matching PR
- `None` (lookup returns `None`) → `(UNKNOWN, (), 255, None)`

Keep the existing `test_non_issue_branch_is_not_checked_and_makes_no_request`,
`test_manager_init_failure_is_unknown`, and `test_lookup_exception_is_unknown` tests,
retargeted to the new mocked method name; their expected tuples gain a trailing
`None`.

In `TestLinkedBranchWiring.test_report_carries_linked_branch_state`, extend the mocked
`_collect_linked_branch_status` return value to a 4-tuple and add an assertion that
`report.closing_pr_candidate` matches.

Changing `_collect_linked_branch_status`'s return arity and `collect_branch_status`'s
unpacking breaks every existing mock of `_collect_linked_branch_status` that still
returns a 3-tuple. Update all of them in the same commit, appending a trailing `None`
to each `return_value`:

- In this file, `TestLinkedBranchSuppressesMergeVerdict.test_mismatch_suppresses_ready_to_merge`
  (~line 417) and `test_ok_still_yields_ready_to_merge` (~line 459) — both mock
  `_collect_linked_branch_status` with a 3-tuple.
- In `tests/checks/test_branch_status.py` — ten separate
  `@patch("mcp_workspace.checks.branch_status._collect_linked_branch_status", return_value=(...))`
  decorators (around lines 547, 622, 675, 723, 766, 814, 866, 936, 1005, 1064), each
  currently `return_value=(LinkedBranchStatus.OK, ("123-feature",), 123)`. Change each
  to `return_value=(LinkedBranchStatus.OK, ("123-feature",), 123, None)`.
