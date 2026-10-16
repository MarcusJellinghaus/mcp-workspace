# Implementation Summary — Issue #316

**Title:** check_branch_status: accept a closing PR on the current branch as a valid issue link

## Goal

`check_branch_status`'s linked-branch check currently reads only `Issue.linkedBranches`.
An issue connected only through a PR body (`Closes #N`) has no linked branch, so the
check reports `NOT_LINKED` and blocks "Ready to merge" even though the issue is
correctly connected to the current branch via that PR. This adds a second link type —
`Issue.closedByPullRequestsReferences` — as a fallback, consulted only when
`linkedBranches` is empty.

## Architectural / Design Changes

- **New GraphQL read path, old one untouched.** A new combined query (selecting both
  `linkedBranches` and `closedByPullRequestsReferences` in one request) is added to
  `linked_branches_mixin.py` behind a new method,
  `get_linked_branch_and_closing_prs_or_none`. It is used **only** by
  `_collect_linked_branch_status`. The existing `_LINKED_BRANCHES_QUERY`,
  `get_linked_branches`, `get_linked_branches_or_none`, and `delete_linked_branch` are
  not touched — they keep their current narrow (branch-names-only) shape for their own
  existing, unrelated callers.
- **New status, not a repurposed one.** `LinkedBranchStatus` gains `LINKED_VIA_PR`,
  treated as non-blocking everywhere `OK`/`NOT_CHECKED` already are (single predicate:
  `linked_branch_blocks`).
- **One new report field, resolved once.** `BranchStatusReport` gains
  `closing_pr_candidate: Optional[ClosingPRRef]`. All the "which PR (if any) is worth
  naming" logic lives in `_collect_linked_branch_status` (the existing owner of all
  OK/MISMATCH/AMBIGUOUS state logic) — it resolves the field down to 0 or 1 entries
  before the report is built. `_format_linked_branch_line` stays a dumb renderer: it
  never counts or filters candidates itself, it just reads the field.
- **Priority is fixed and encoded structurally, not by a flag.** Because the closing-PR
  fallback is only ever consulted when `linkedBranches` comes back empty, "an existing
  linked branch always wins, even if stale/ambiguous" falls out of the code's control
  flow rather than needing an explicit priority check.
- **`includeClosedPrs: false`** on the new query — only open closing PRs count.

### State resolution (in `_collect_linked_branch_status`)

| `linkedBranches` | closing PRs (open, `Closes #N`) | Result |
|---|---|---|
| 1, equals current branch | (irrelevant) | `OK` |
| 1, differs | (irrelevant) | `MISMATCH`, names the linked branch |
| 2+ | (irrelevant) | `AMBIGUOUS` |
| 0 | 1 matches current branch (others don't matter) | `LINKED_VIA_PR`, names that PR |
| 0 | 0 match, exactly 1 candidate total | `MISMATCH`, names that PR |
| 0 | 0 match, 2+ candidates | `MISMATCH`, generic (no PR named) |
| 0 | 0 candidates at all | `NOT_LINKED` |

## Files Created or Modified

| File | Change |
|---|---|
| `src/mcp_workspace/github_operations/issues/linked_branches_mixin.py` | Add `ClosingPRRef` NamedTuple, new combined query constant, private parser, and `get_linked_branch_and_closing_prs_or_none` method |
| `src/mcp_workspace/github_operations/issues/__init__.py` | Export `ClosingPRRef` |
| `src/mcp_workspace/checks/branch_status_rendering.py` | Add `LinkedBranchStatus.LINKED_VIA_PR`; update `linked_branch_blocks`; update `_format_linked_branch_line` (new `LINKED_VIA_PR` wording, PR-sourced/generic `MISMATCH` wording, updated `NOT_LINKED` wording) |
| `src/mcp_workspace/checks/branch_status.py` | Add `closing_pr_candidate` field to `BranchStatusReport`; rewrite `_collect_linked_branch_status` to call the new mixin method and apply the priority table above; wire the new field through `collect_branch_status` |
| `.claude/skills/check_branch_status/SKILL.md` | Update follow-up-action table: mention a `Closes #N` PR satisfies the check; distinguish non-blocking `LINKED_VIA_PR` from blocking `NOT_LINKED`/`MISMATCH` |
| `tests/github_operations/issues/test_branch_manager_linked.py` | New test class for `get_linked_branch_and_closing_prs_or_none` |
| `tests/checks/test_branch_status_linked_branch.py` | Extended state matrix, wiring, and rendering tests |

No other files change. `tests/LLM_Test.md` needs no edit — it already asserts on the
`Linked Branch:` line's presence/absence only, not on a specific status value.

## Out of Scope

- `MISMATCH`/`AMBIGUOUS` sourced from `linkedBranches` behave exactly as before (the
  #268 stale-link case is unaffected).
- No change to `get_branch_with_pr_fallback` (timeline-based PR resolution) — it's an
  unrelated resolver, cited in the issue only as prior art.
- No mcp_coder companion change (gated on mcp_coder #1146, already filed).

## Commit Plan (one commit per step)

1. `feat(github_operations): add combined linked-branch/closing-PR query`
2. `feat(branch_status): add LINKED_VIA_PR status`
3. `feat(branch_status): resolve closing-PR fallback in linked-branch check`
4. `feat(branch_status): render LINKED_VIA_PR and PR-sourced MISMATCH`
5. `docs(skills): update check_branch_status follow-up actions for closing-PR link`
