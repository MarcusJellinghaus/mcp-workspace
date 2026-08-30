# Step 2 — Collect and record linked-branch state on the report

**Goal:** the report *knows* whether the issue's linked branch matches the
current branch. Nothing is rendered and nothing blocks yet — that is step 3.

Depends on step 1. See [summary.md](./summary.md), sections *2* and *3*.

## WHERE

| File | Change |
|---|---|
| `src/mcp_workspace/checks/branch_status_rendering.py` | `LinkedBranchStatus` enum + `linked_branch_blocks` predicate |
| `src/mcp_workspace/checks/branch_status.py` | Two report fields, `_collect_linked_branch_status`, wiring |
| `tests/checks/test_branch_status_linked_branch.py` | **New file** — state matrix |

## WHAT

In `branch_status_rendering.py`, directly below `CIStatus`:

```python
class LinkedBranchStatus(str, Enum):
    """Whether the issue's linked branch matches the current branch."""

    OK = "OK"                    # exactly one linked branch, equals current
    MISMATCH = "MISMATCH"        # exactly one linked branch, differs
    AMBIGUOUS = "AMBIGUOUS"      # more than one linked branch
    NOT_LINKED = "NOT_LINKED"    # queried fine, no linked branch
    UNKNOWN = "UNKNOWN"          # lookup could not be completed
    NOT_CHECKED = "NOT_CHECKED"  # branch name yields no issue number


def linked_branch_blocks(status: LinkedBranchStatus) -> bool:
    """Return True when the state must block the merge verdict."""
    return status not in (LinkedBranchStatus.OK, LinkedBranchStatus.NOT_CHECKED)
```

In `branch_status.py`:

```python
def _collect_linked_branch_status(
    project_dir: Path, branch_name: str
) -> tuple[LinkedBranchStatus, tuple[str, ...]]:
    """Compare the issue's linked branches against the current branch."""
```

and two **trailing** fields on `BranchStatusReport`, after
`pr_feedback_undeterminable`:

```python
linked_branch_status: LinkedBranchStatus = LinkedBranchStatus.NOT_CHECKED
linked_branches: tuple[str, ...] = ()
```

## HOW

- Import `IssueBranchManager` **at module level** in `branch_status.py`
  (`from mcp_workspace.github_operations.issues import IssueBranchManager` —
  extend the existing import at line 37 or add a sibling line). Module-level is
  required so tests can patch
  `mcp_workspace.checks.branch_status.IssueBranchManager` by name, matching the
  existing `IssueManager` / `PullRequestManager` seam.
- Import `LinkedBranchStatus` and `linked_branch_blocks` into `branch_status.py`
  from `branch_status_rendering` (extend the existing import block at line 13).
- `_collect_linked_branch_status` goes beside `_collect_pr_info` /
  `_collect_github_label`, before `_generate_recommendations`.
- Call it in `collect_branch_status` as a **new step 4**, immediately after
  base-branch detection and before CI collection — i.e. **outside** the inner
  `try` that builds `IssueManager` / `PullRequestManager`. Renumber the
  following comment markers (`# 4.` → `# 5.` …) or leave the numbering to the
  implementer's judgement; keep it consistent.
- Pass both new values to the `BranchStatusReport(...)` constructor, and add
  one key to `report_data`:
  `"linked_branch_blocks": linked_branch_blocks(linked_branch_status)`.
  `_generate_recommendations` does not read it yet — step 3 adds that. Adding
  it here keeps `linked_branch_blocks` from being an unused symbol.
- `tuple[str, ...] = ()` rather than `List[str] = field(default_factory=list)`:
  an immutable default needs no `field` import and suits a frozen dataclass.
  Python is `>=3.11`, and the module already uses built-in generics
  (`frozenset[str]` at line 58).
- **The helper must catch everything.** The outer `except` in
  `collect_branch_status` returns `create_empty_report(UNKNOWN)` and discards
  the entire report, so a leak here loses CI, tasks and PR data. In particular
  `IssueBranchManager.__init__` raises `ValueError` when no token is
  configured — that is a `UNKNOWN`, not a crash.
- Do **not** reuse the `IssueManager` built at line 503, and do not thread a
  manager in as a parameter. A fresh `IssueBranchManager` inside the helper is
  the deliberate choice (see summary section 3): single patch point, helper owns
  its error handling, two requests accepted.

## ALGORITHM

```
_collect_linked_branch_status(project_dir, branch_name):
    issue_number = extract_issue_number_from_branch(branch_name)
    if issue_number is None:              return (NOT_CHECKED, ())
    try:
        manager  = IssueBranchManager(project_dir=project_dir)   # may raise ValueError
        branches = manager.get_linked_branches_or_none(issue_number)
    except Exception:  log.debug(exc_info=True); return (UNKNOWN, ())
    if branches is None:                  return (UNKNOWN, ())
    if len(branches) > 1:                 return (AMBIGUOUS, tuple(branches))
    if not branches:                      return (NOT_LINKED, ())
    state = OK if branches[0] == branch_name else MISMATCH
    return (state, tuple(branches))
```

Comparison is a direct string equality: GraphQL `Ref.name` and
`get_current_branch_name` both yield short names with no `refs/heads/` prefix.

## DATA

- Returns `tuple[LinkedBranchStatus, tuple[str, ...]]`. The names tuple is
  empty for `NOT_CHECKED`, `UNKNOWN` and `NOT_LINKED`; it holds the linked
  names for `OK`, `MISMATCH` and `AMBIGUOUS`.
- `BranchStatusReport.linked_branch_status` defaults to `NOT_CHECKED`, so
  `create_empty_report` is silent and non-blocking rather than double-blocked
  on top of `CIStatus.UNKNOWN`.

## TDD — tests first

New file `tests/checks/test_branch_status_linked_branch.py`. Patch
`mcp_workspace.checks.branch_status.IssueBranchManager`.

1. **Parametrized state matrix** over `_collect_linked_branch_status`, with
   `branch_name="255-feature"`:

   | `get_linked_branches_or_none` returns | expected |
   |---|---|
   | `["255-feature"]` | `(OK, ("255-feature",))` |
   | `["255-old"]` | `(MISMATCH, ("255-old",))` |
   | `["255-a", "255-b"]` | `(AMBIGUOUS, ("255-a", "255-b"))` |
   | `[]` | `(NOT_LINKED, ())` |
   | `None` | `(UNKNOWN, ())` |

2. `branch_name="main"` → `(NOT_CHECKED, ())` **and** the patched
   `IssueBranchManager` is never constructed (`assert_not_called`) — this pins
   the "zero requests off issue branches" guarantee.
3. `IssueBranchManager` side effect `ValueError("no token")` → `(UNKNOWN, ())`,
   no exception escaping.
4. `get_linked_branches_or_none` side effect `RuntimeError` → `(UNKNOWN, ())`.
5. A `collect_branch_status` wiring test: patch `get_current_branch_name`,
   `detect_base_branch`, `IssueManager`, `PullRequestManager` and
   `_collect_linked_branch_status` (returning `(MISMATCH, ("255-old",))`), and
   assert the returned report carries `linked_branch_status == MISMATCH` and
   `linked_branches == ("255-old",)`. Follow the decorator-stack style already
   used at `tests/checks/test_branch_status.py:489`.
6. `linked_branch_blocks` returns `False` for `OK` and `NOT_CHECKED`, `True`
   for the other four.

## Definition of done

- New tests pass; **all existing `tests/checks/` tests still pass unmodified**.
  Nothing blocks yet, so no existing recommendation assertion can break in this
  step. If one does, stop — the wiring is in the wrong place.
- Pylint / pytest / mypy via the MCP tools all pass.
- One commit.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`. Step 1 is done.
>
> Implement step 2 only: add `LinkedBranchStatus` and `linked_branch_blocks` to
> `src/mcp_workspace/checks/branch_status_rendering.py`, add
> `_collect_linked_branch_status` plus the two trailing defaulted fields to
> `src/mcp_workspace/checks/branch_status.py`, and wire the helper into
> `collect_branch_status` right after base-branch detection (outside the inner
> try block) so the report carries the state.
>
> Write `tests/checks/test_branch_status_linked_branch.py` first, covering the
> six cases in step_2.md. Patch
> `mcp_workspace.checks.branch_status.IssueBranchManager` by module-level name.
>
> The helper must catch every exception itself and return `UNKNOWN` — including
> the `ValueError` that `IssueBranchManager.__init__` raises without a token —
> because the outer handler in `collect_branch_status` would otherwise discard
> the whole report.
>
> Nothing renders and nothing blocks in this step: do **not** touch
> `_generate_recommendations`, `_review_gate_header` or either formatter, and do
> not modify any existing test. Add `"linked_branch_blocks"` to the
> `report_data` dict (step 3 consumes it).
>
> Use the MCP tools per `.claude/CLAUDE.md`: `mcp__workspace__*` for file
> operations, and `mcp__tools-py__run_pylint_check`, `run_pytest_check`
> (`extra_args=["-n","auto","-m","not git_integration and not
> claude_cli_integration and not claude_api_integration and not
> formatter_integration and not github_integration and not
> langchain_integration"]`) and `run_mypy_check` after each edit. All three must
> pass. Produce exactly one commit.
