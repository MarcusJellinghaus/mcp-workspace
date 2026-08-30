# Summary — Issue #268: verify the issue's linked branch matches the current branch

## Problem

`check_branch_status` resolves the issue number from the branch name by regex
(`extract_issue_number_from_branch`, `^(\d+)-`). It never reads the issue's
linked branch, so when the branch linked in the issue's Development panel is a
superseded one, every reported field is still green and nothing flags the
mismatch. `get_branch_with_pr_fallback` trusts `linkedBranches` as its first
resolution step, so every issue-driven flow then resolves to the wrong branch.

## Goal

Look up the issue's linked branches, compare them against the current branch,
render the result, and **block the merge verdict** on anything other than a
clean match.

| Linked branches | State | Blocks? |
|---|---|---|
| exactly one, equals current branch | `OK` | no |
| exactly one, differs | `MISMATCH` | yes |
| more than one | `AMBIGUOUS` | yes |
| none | `NOT_LINKED` | yes |
| lookup failed | `UNKNOWN` | yes |
| branch name yields no issue number | `NOT_CHECKED` | no (silent, zero requests) |

## Architectural / design changes

### 1. A non-swallowing lookup path on `IssueBranchManager` (sibling, not a flag)

`get_linked_branches` is wrapped in `@_handle_github_errors(default_return=[])`.
A 404, a network blip and a parse error all become `[]` — indistinguishable from
a genuinely unlinked issue. Since every non-OK state blocks, that conflation
would let a blip block the merge while telling you to link a branch that may
already be linked.

A `raise_on_error=True` flag cannot fix this: the decorator wraps the *entire*
body and converts the exceptions to `[]` before any in-body flag logic runs.
The shape is therefore a **sibling method**:

```
_query_linked_branches(issue_number) -> Optional[List[str]]   # undecorated, None on failure
get_linked_branches(issue_number)    -> List[str]             # decorated wrapper, [] as today
get_linked_branches_or_none(...)     -> Optional[List[str]]   # None on failure
```

The private method signals its four in-body failure paths with a `None`
sentinel rather than a custom exception. This is deliberate: an exception would
have to avoid being a `ValueError`, because `_handle_github_errors` re-raises
those (`base_manager.py:75-77`), which would turn `get_linked_branches` from
returning `[]` into raising and break its caller at `branch_manager.py:302`
(that caller reads `[]` as "no existing branches, safe to create"; making it
raise would turn an API blip into a duplicate branch). The sentinel keeps
`get_linked_branches` byte-identical in behaviour *and* in logging.

Four paths map to `UNKNOWN`: invalid issue number, repository unavailable,
GraphQL `issue` null, parse error. **Only a successful query returning an empty
list is `NOT_LINKED`.**

### 2. A new report enum and two new report fields

`LinkedBranchStatus` joins `CIStatus` in `checks/branch_status_rendering.py`,
which is the canonical home of the report enums. A single predicate
`linked_branch_blocks(status)` is the one source of truth for "does this state
block", consumed by both the recommendation chain and the review-gate header.

`BranchStatusReport` gains two **trailing defaulted** fields, so the frozen
dataclass stays backward compatible (including for the `dataclasses.replace`
call in `branch_status_polling.py:154`, and for `mcp_coder`'s re-export shim):

```python
linked_branch_status: LinkedBranchStatus = LinkedBranchStatus.NOT_CHECKED
linked_branches: tuple[str, ...] = ()
```

`NOT_CHECKED` as the default keeps `create_empty_report` from being
double-blocked on top of `CIStatus.UNKNOWN`.

### 3. A step helper that owns all of its error handling

`_collect_linked_branch_status(project_dir, branch_name)` sits beside
`_collect_pr_info` / `_collect_github_label`. It constructs its **own**
`IssueBranchManager` and re-extracts the issue number from the branch name,
because `issue_number` is bound inside the inner `try` in
`collect_branch_status` and is unbound if `IssueManager(...)` raises.

It **must not propagate**: the outer `except` in `collect_branch_status`
returns `create_empty_report(UNKNOWN)` and discards the whole report. So the
helper catches everything — including the `ValueError` that
`IssueBranchManager.__init__` raises without a token — and returns `UNKNOWN`.

The cost is two requests (a REST `get_repo` plus the GraphQL query), because
`BaseGitHubManager` caches `_repository` per instance. That duplicate is
accepted rather than threading a shared manager through: it keeps a single
deterministic patch point for tests and lets the helper own its exception
handling. Gating on "branch name yields an issue number" keeps the cost at
**zero** on `main` and on any non-issue branch.

### 4. Blocking, and a single verdict in the output

- `_generate_recommendations` gains **one term** in the existing `and` chain,
  reading `report_data.get("linked_branch_blocks", False)` — it takes a plain
  dict and is called with hand-built dicts by the recommendation tests.
- `_review_gate_header` renders a distinct `Review Gate: BLOCKED (linked
  branch)`, inserted **after** the CI `UNAVAILABLE`/`UNKNOWN` checks and
  **before** the reviews check, so a report never shows `Review Gate: clean`
  beside a suppressed `Ready to merge`. A linked-branch `UNKNOWN` therefore
  renders as BLOCKED, not UNKNOWN — that is what "all non-OK states block"
  asks for, and it is pinned by a test. Display-only; no exit-code change here.
- One render line in `format_report_for_human` and `format_report_for_llm`.
  These two are the complete output surface: the MCP tool returns a plain
  `str`, and mcp_coder's CLI uses `format_for_human`. There is no dict/JSON
  serialization layer to update.

Message text never asserts the linked branch lives in this repo — the GraphQL
query selects only `ref { name }`, so a fork-hosted linked branch comes back as
a bare name. The `UNKNOWN` message is neutral ("could not determine the linked
branch for issue #N", not "lookup failed"), since a branch numbered for a
nonexistent issue reaches `UNKNOWN` via the GraphQL-null path.

### Design notes

- **A false `MISMATCH` is impossible.** An error yields `None`/`[]`, never a
  wrong branch name. Only `NOT_LINKED` could be counterfeited by an error —
  which is exactly what `UNKNOWN` removes.
- **Comparison is direct.** `get_linked_branches` returns GraphQL `Ref.name`
  values: short names with no `refs/heads/` prefix, matching what
  `get_current_branch_name` returns.
- **Blocking on a no-token run is not a new hole.** Without a token the lookup
  is `UNKNOWN` and blocks, but CI already renders `UNAVAILABLE` and mcp_coder
  already exits 2 for undeterminable CI, so such a run was never clean.
- **No new recommendation string.** Per the issue, blocking is *suppression*
  only; the message lives on the render line. On an otherwise-green mismatch
  the recommendations therefore fall through to `Continue with current work`
  beside a BLOCKED gate header.
- **File size.** `branch_status.py` 615 → ~660 lines and
  `branch_status_rendering.py` 301 → ~345, both well under the CI limit of 750.
  No file split is needed.

## Out of scope

- Repairing the link. `createLinkedBranch` / `deleteLinkedBranch` are writes;
  `check_branch_status` is a read-only check.
- `mcp_coder`'s `_exit_code`. That is a companion issue, filed separately once
  the report field exists here. Note for it: the shim's `__all__` is a fixed
  name list that will not re-export the new enum, so mcp_coder must import
  `LinkedBranchStatus` from `mcp_workspace.checks.branch_status_rendering` or
  the shim gains a re-export.

## Files created / modified

### Created

| Path | Purpose |
|---|---|
| `tests/checks/test_branch_status_linked_branch.py` | State matrix, rendering and review-gate tests for the new check |

### Modified — source

| Path | Change |
|---|---|
| `src/mcp_workspace/github_operations/issues/branch_manager.py` | `_query_linked_branches` (private, `Optional`), `get_linked_branches` becomes a thin wrapper, new `get_linked_branches_or_none` |
| `src/mcp_workspace/checks/branch_status_rendering.py` | `LinkedBranchStatus`, `linked_branch_blocks`, `_format_linked_branch_line`, render line in both formatters, `BLOCKED (linked branch)` in `_review_gate_header` |
| `src/mcp_workspace/checks/branch_status.py` | Two report fields, `_collect_linked_branch_status`, wiring in `collect_branch_status`, one term in `_generate_recommendations` |

### Modified — tests

| Path | Change |
|---|---|
| `tests/github_operations/issues/test_branch_manager_linked.py` | New cases for `get_linked_branches_or_none`; existing `assert result == []` cases stay untouched as the regression harness |
| `tests/checks/test_branch_status_recommendations.py` | One case: `linked_branch_blocks=True` suppresses `Ready to merge` |
| `tests/checks/test_branch_status.py` | `_collect_linked_branch_status` patch decorator on the seven manager-patching tests (step 2), so none constructs a real `IssueBranchManager`. Two of them assert a clean verdict and would otherwise fail: `test_rebase_behind_but_mergeable_squash_safe` (`squash-merge safe` recommendation) and `test_confirmed_no_pr_stays_clean_eligible` (`Review Gate: clean`) |

### Modified — docs

| Path | Change |
|---|---|
| `.claude/skills/check_branch_status/SKILL.md` | Relink row in the status→action table (step 3) |
| `tests/LLM_Test.md` | Conditional expectation for the new line in Test 3.2 (step 3) |

### Unchanged (deliberately)

- `get_linked_branches`' `default_return=[]` and its caller at
  `branch_manager.py:302`.
- `branch_status.py`'s `__all__` — consumers import the enum from
  `branch_status_rendering`, as they already do for `CIStatus`.
- `server.py`, `branch_status_polling.py` — no signature or serialization
  change reaches them.

## Steps

| Step | Commit |
|---|---|
| [step_1.md](./step_1.md) | Non-swallowing linked-branch lookup on `IssueBranchManager` |
| [step_2.md](./step_2.md) | Collect and record linked-branch state on the report (silent) |
| [step_3.md](./step_3.md) | Act on it: suppress `Ready to merge`, gate header, render line, docs |

Steps 2 and 3 are split as "observe" then "act". Step 3's parts stay in one
commit on purpose: splitting them would leave a commit where the report shows
`Review Gate: clean` next to a suppressed `Ready to merge` — precisely the
disagreeing double verdict the issue rules out. The two documentation edits
ride along in step 3 rather than forming a step of their own: they are two
lines of prose that only restate the wording chosen there, and a separate
commit for them would be verification-only.
