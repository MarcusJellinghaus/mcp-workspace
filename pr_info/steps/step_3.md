# Step 3 — Block the merge verdict and surface the state

**Goal:** a non-OK linked-branch state suppresses `Ready to merge`, flips the
review-gate header, and renders a message naming the branches involved.

Depends on step 2. See [summary.md](./summary.md), section *4*.

These three parts ship as **one commit on purpose**: splitting them would leave
a commit where the report shows `Review Gate: clean` next to a suppressed
`Ready to merge` — the disagreeing double verdict the issue rules out.

## WHERE

| File | Change |
|---|---|
| `src/mcp_workspace/checks/branch_status.py` | One term in `_generate_recommendations` |
| `src/mcp_workspace/checks/branch_status_rendering.py` | `_format_linked_branch_line`, a call in each formatter, one branch in `_review_gate_header` |
| `tests/checks/test_branch_status_linked_branch.py` | Rendering + gate tests, plus the end-to-end suppression test (extend the step-2 file) |
| `tests/checks/test_branch_status_recommendations.py` | One suppression case |
| `tests/checks/test_branch_status.py` | Verify the two tests that depend on a clean verdict |
| `.claude/skills/check_branch_status/SKILL.md` | Relink row in the *Follow-Up Actions* table |
| `tests/LLM_Test.md` | Conditional expectation for the new line in Test 3.2 |

## WHAT

```python
def _format_linked_branch_line(report: "BranchStatusReport") -> Optional[str]:
    """Build the ``Linked Branch: ...`` line, or None when nothing to render."""
```

## HOW

### a. Suppression — `_generate_recommendations`

Read the flag near the other `report_data.get(...)` reads, through the same
`_LINKED_BRANCH_BLOCKS_KEY` constant step 2 used to write it (both sides live
in `branch_status.py`, so the literal exists exactly once and cannot drift):

```python
linked_branch_blocking = report_data.get(_LINKED_BRANCH_BLOCKS_KEY, False)
```

and add **one term** to the existing `and` chain at `branch_status.py:460-466`:

```python
and not linked_branch_blocking
```

Read it off the dict, not off a report object: `_generate_recommendations`
takes a plain dict and is called with hand-built dicts by
`test_branch_status_recommendations.py`. Add **no** new recommendation string —
blocking here is suppression only; the message lives on the render line.

### b. Render line — both formatters

`_format_linked_branch_line` lives beside `_format_wait_line`. It needs the
issue number, which it re-derives with
`extract_issue_number_from_branch(report.branch_name)` (import from
`mcp_workspace.git_operations.branch_queries`; `checks/` already depends on
`git_operations`, so this adds no layering violation). Return `None` when the
state is `NOT_CHECKED` **or** when the issue number is `None`.

Wording — identical text in both formatters (one helper, two call sites; no
emoji, so the LLM format stays emoji-free as it is today):

| State | Line |
|---|---|
| `OK` | `Linked Branch: OK ('{current}')` |
| `MISMATCH` | `Linked Branch: MISMATCH — issue #{n} links '{linked}', not current branch '{current}' — relink in the Development panel` |
| `AMBIGUOUS` | `Linked Branch: AMBIGUOUS — issue #{n} links {k} branches ({names}) — unlink the extra branches in the Development panel so exactly one remains` |
| `NOT_LINKED` | `Linked Branch: NOT_LINKED — issue #{n} links no branch — link '{current}' in the Development panel` |
| `UNKNOWN` | `Linked Branch: UNKNOWN — could not determine the linked branch for issue #{n}` |

Use an em dash `—`, as the existing `CI Status:` line does. The wording must
**not** claim the linked branch lives in this repository: the GraphQL query
selects only `ref { name }`, so a fork-hosted branch arrives as a bare name.
`UNKNOWN` must stay neutral — "could not determine", never "lookup failed" —
because a branch numbered for a nonexistent issue reaches `UNKNOWN` through the
GraphQL-null path.

Placement, chosen so no existing format assertion shifts:

- `format_report_for_human`: append after the `GitHub Status: ...` entry, before
  the blank line preceding `Recommendations:`.
- `format_report_for_llm`: append after the `GitHub Label: ...` line, before
  `Recommendations: ...`.

### c. Review gate — `_review_gate_header`

Insert **after** the CI `UNAVAILABLE` and `UNKNOWN`/`pr_feedback_undeterminable`
checks and **before** the `pr_feedback_blocks_merge` check:

```python
if linked_branch_blocks(report.linked_branch_status):
    return "Review Gate: BLOCKED (linked branch)"
```

That ordering means a linked-branch `UNKNOWN` renders as **BLOCKED**, not
UNKNOWN — which is what "all non-OK states block" asks for. Pin it with a test.
The existing `if not fail_on_reviews: return None` guard stays first, so the
whole header remains suppressed when the gate is off. Display-only: no exit code
changes from this step.

### d. Documentation

Two non-code files describe this output. They ship in **this** commit because
their wording is the wording chosen above — split into their own commit they
would either restate text that does not exist yet or drift from it.

- `.claude/skills/check_branch_status/SKILL.md` — one row in the *Follow-Up
  Actions* table, keeping the two-column format and terse style:

  ```
  | Linked branch not OK | Relink the branch in the issue's Development panel |
  ```

  Place it with the other blocking rows, above the two "ready" rows at the
  bottom of the table. Do not touch the frontmatter (`description`,
  `allowed-tools`).
- `tests/LLM_Test.md` — Test 3.2 (`:149-155`) lists the line prefixes a live
  `check_branch_status(ci_timeout=0, pr_timeout=0)` call must produce. The four
  existing prefixes are unconditional; `Linked Branch:` is **not** — the state
  is `NOT_CHECKED` and the line is suppressed entirely on `main` and on any
  branch whose name does not start with `<digits>-`. Add it as a conditional
  expectation after the existing list, not as a fifth mandatory bullet:

  ```
     Additionally, when run on an issue-numbered branch (`<number>-...`), expect a
     `"Linked Branch:"` line; it is absent on `main` and other non-issue branches.
  ```

  Keep the existing four bullets exactly as they are.

Check both against what `_format_linked_branch_line` actually renders.

## ALGORITHM

```
_format_linked_branch_line(report):
    if report.linked_branch_status is NOT_CHECKED:  return None
    n = extract_issue_number_from_branch(report.branch_name)
    if n is None:                                   return None
    match state:  OK -> ok text;  MISMATCH -> names linked[0] and branch_name
                  AMBIGUOUS -> joins report.linked_branches
                  NOT_LINKED -> names branch_name;  UNKNOWN -> names #n only
    return "Linked Branch: " + text
```

## DATA

`Optional[str]` — a single line, or `None` when nothing should be rendered.
No new report fields in this step; the gate and the line are pure functions of
`linked_branch_status`, `linked_branches` and `branch_name`.

## TDD — tests first

In `tests/checks/test_branch_status_linked_branch.py`:

1. Parametrized render test over all six states for **both** formatters:
   `NOT_CHECKED` renders no `Linked Branch:` line at all; each other state
   renders one, and `MISMATCH` / `AMBIGUOUS` name every branch involved plus
   the current branch.
2. `MISMATCH` on a report whose `branch_name` yields no issue number → no line
   (the `None` guard).
3. Parametrized gate test: each of `MISMATCH`, `AMBIGUOUS`, `NOT_LINKED`,
   `UNKNOWN` with `fail_on_reviews=True` → `"Review Gate: BLOCKED (linked
   branch)"`. **Assert the `UNKNOWN` case explicitly** — it is the deliberate
   BLOCKED-not-UNKNOWN decision.
4. Precedence: `ci_status=UNAVAILABLE` + `linked_branch_status=MISMATCH` →
   `"Review Gate: UNKNOWN (no token)"`; `ci_status=CIStatus.UNKNOWN` + MISMATCH
   → `"Review Gate: UNKNOWN (undeterminable)"`.
5. `fail_on_reviews=False` + `MISMATCH` → `None`.
6. `OK` and `NOT_CHECKED` with an otherwise clean report → `"Review Gate:
   clean"`.

7. **End-to-end suppression through `collect_branch_status`.** The dict cases
   below only exercise `_generate_recommendations` with hand-built dicts, so
   nothing else pins that the value `collect_branch_status` writes actually
   reaches the read. Patch `get_current_branch_name` (`"255-feature"`),
   `detect_base_branch`, `IssueManager`, `PullRequestManager`,
   `_collect_ci_status` → `(CIStatus.PASSED, None, [])`,
   `_collect_rebase_status` → `(False, "up-to-date")`, `_collect_task_status`
   → `(TaskTrackerStatus.COMPLETE, "done", False)`, `_collect_pr_info` and
   `_collect_linked_branch_status` → `(MISMATCH, ("255-old",))`; assert
   neither `"Ready to merge"` nor `"Ready to merge (squash-merge safe)"` is in
   `report.recommendations`. Add the mirror case with the helper returning
   `(OK, ("255-feature",))`, which must still yield `Ready to merge`.
   Both sides of the join share `_LINKED_BRANCH_BLOCKS_KEY` (defined once in
   `branch_status.py`, step 2), and this test is what proves the write reaches
   the read — without it a key mismatch would silently disable the whole
   feature with every other planned test still green.

In `tests/checks/test_branch_status_recommendations.py`, beside the existing
`Ready to merge` cases: an otherwise-clean `report_data` plus
`_LINKED_BRANCH_BLOCKS_KEY: True` → neither `"Ready to merge"` nor `"Ready to
merge (squash-merge safe)"` in the result. Add a matching case asserting the
default (`key absent`) still yields `Ready to merge`, so the
`.get(..., False)` default is pinned.

## The two existing tests that depend on a clean verdict

Two tests in `tests/checks/test_branch_status.py` assert an outcome that a
blocking linked-branch state destroys. Both patch `IssueManager` and
`PullRequestManager` but nothing that would otherwise stop the new step, and
both run on branch `"123-feature"`:

| Test | Assertion | What the block breaks |
|---|---|---|
| `test_rebase_behind_but_mergeable_squash_safe` (`:581`, assertion `:616`) | `"squash-merge safe"` is in the recommendations | `Ready to merge (squash-merge safe)` is suppressed |
| `test_confirmed_no_pr_stays_clean_eligible` (`:811`, assertion `:848`) | `"Review Gate: clean"` is in `format_for_llm(fail_on_reviews=True)` | the header renders `Review Gate: BLOCKED (linked branch)` |

Step 2 already added
`@patch("mcp_workspace.checks.branch_status._collect_linked_branch_status")`
with `return_value=(LinkedBranchStatus.OK, ("123-feature",))` to the seven
manager-patching tests in that file, which covers both of these. Verify both
are green here, and add the decorator to either one that is missing it. **A
second adjusted test is expected — it is not a sign that the implementation is
wrong.** The remaining manager-patching tests assert `"Ready to merge" not in
...`, which stays true either way — but check rather than assume, and fix any
exposure with a patch decorator, never by weakening an assertion.

## Definition of done

- The new and amended tests pass; the whole `tests/checks/` and
  `tests/github_operations/` suites pass.
- **Two** existing tests depend on a clean merge verdict —
  `test_rebase_behind_but_mergeable_squash_safe` and
  `test_confirmed_no_pr_stays_clean_eligible`. Both must be green through
  their `_collect_linked_branch_status` patch (added in step 2; add it here if
  either lacks it). Two adjusted tests is the expected outcome, not a defect.
  Every adjustment is a patch decorator, never a weakened assertion.
- The end-to-end suppression test through `collect_branch_status` exists and
  fails if the `report_data` key is not shared between the write and the read.
- `SKILL.md` and `tests/LLM_Test.md` updated, and their wording matches what
  `_format_linked_branch_line` renders. `SKILL.md`'s table still renders as
  valid Markdown.
- Pylint / pytest / mypy via the MCP tools all pass.
- One commit.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`. Steps 1 and 2
> are done, so the report already carries `linked_branch_status` and
> `linked_branches`.
>
> Implement step 3: (a) one `and not linked_branch_blocking` term in the
> `_generate_recommendations` chain, reading
> `report_data.get("linked_branch_blocks", False)` — no new recommendation
> string; (b) `_format_linked_branch_line` in
> `checks/branch_status_rendering.py` with the exact wording table from
> step_3.md, called from both `format_report_for_human` and
> `format_report_for_llm` at the placements given; (c) a
> `"Review Gate: BLOCKED (linked branch)"` branch in `_review_gate_header`,
> inserted after the CI UNAVAILABLE/UNKNOWN checks and before the reviews check;
> (d) the two documentation edits described in step_3.md — a relink row in
> `.claude/skills/check_branch_status/SKILL.md` and a **conditional** expectation
> for the `Linked Branch:` line in Test 3.2 of `tests/LLM_Test.md` (the line is
> suppressed on `main` and other non-issue branches, so it must not join the four
> unconditional prefixes). They belong in this commit because their wording is
> the wording you choose in (b).
>
> Write the tests first — the seven groups listed in step_3.md, including the
> end-to-end suppression test through `collect_branch_status`, plus the
> suppression case in `tests/checks/test_branch_status_recommendations.py`.
> Assert explicitly that a linked-branch `UNKNOWN` renders BLOCKED, not UNKNOWN.
>
> Then verify the two tests in `tests/checks/test_branch_status.py` that depend
> on a clean verdict — `test_rebase_behind_but_mergeable_squash_safe` and
> `test_confirmed_no_pr_stays_clean_eligible`. Both should already carry the
> `_collect_linked_branch_status` patch from step 2; add it (returning `OK`) to
> either one that does not. Two affected tests is expected. Check the other
> manager-patching tests in that file for the same exposure, and fix any with a
> patch decorator, never by weakening an assertion.
>
> Keep the message wording repo-neutral and keep `UNKNOWN` phrased as "could not
> determine", per step_3.md.
>
> Use the MCP tools per `.claude/CLAUDE.md`: `mcp__workspace__*` for file
> operations, and `mcp__tools-py__run_pylint_check`, `run_pytest_check`
> (`extra_args=["-n","auto","-m","not git_integration and not
> claude_cli_integration and not claude_api_integration and not
> formatter_integration and not github_integration and not
> langchain_integration"]`) and `run_mypy_check` after each edit. All three must
> pass. Produce exactly one commit.
