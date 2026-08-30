# Task Status Tracker

## Instructions for LLM

This tracks **Feature Implementation** consisting of multiple **Tasks**.

**Summary:** See [summary.md](./steps/summary.md) for implementation overview.

**How to update tasks:**
1. Change [ ] to [x] when implementation step is fully complete (code + checks pass)
2. Change [x] to [ ] if task needs to be reopened
3. Add brief notes in the linked detail files if needed
4. Keep it simple - just GitHub-style checkboxes

**Task format:**
- [x] = Task complete (code + all checks pass)
- [ ] = Task not complete
- Each task links to a detail file in steps/ folder

---

## Tasks

### Step 1: Non-swallowing linked-branch lookup on `IssueBranchManager`

Details: [step_1.md](./steps/step_1.md)

- [x] Implementation: split `get_linked_branches` into undecorated `_query_linked_branches` (`Optional[List[str]]`, `None` on the four in-body failure paths), a decorated `get_linked_branches` wrapper keeping the `[]` contract, and a new `get_linked_branches_or_none`; write the eight new cases in `tests/github_operations/issues/test_branch_manager_linked.py` first, leaving the existing `assert result == []` tests untouched
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared — applied as commit `39a3594`. The file `pr_info/.commit_message.txt` could not be written (`.gitignore:48` excludes it; the workspace MCP refuses gitignored paths and no shell tool is available in this session), so the text is recorded here instead:

  ```
  feat(github_operations/issues): add get_linked_branches_or_none

  Extract the GraphQL lookup into an undecorated helper that signals failure
  with None, so callers can distinguish "no linked branch" from "lookup failed".
  ```

### Step 2: Collect and record linked-branch state on the report

Details: [step_2.md](./steps/step_2.md) — depends on Step 1

- [x] Implementation: add `LinkedBranchStatus` + `linked_branch_blocks` to `branch_status_rendering.py`; add `_collect_linked_branch_status`, the two trailing defaulted report fields, `_LINKED_BRANCH_BLOCKS_KEY` and the `collect_branch_status` wiring to `branch_status.py`; write `tests/checks/test_branch_status_linked_branch.py` (six cases) first and add the `_collect_linked_branch_status` patch decorator to the seven manager-patching tests in `test_branch_status.py`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared — as in step 1, `pr_info/.commit_message.txt` could not be written (`.gitignore:48` excludes it; the workspace MCP refuses gitignored paths), so the text is recorded here instead:

  ```
  feat(checks): record the issue's linked-branch state on the report

  Add LinkedBranchStatus and the linked_branch_blocks predicate, collect the
  state via _collect_linked_branch_status and carry it on BranchStatusReport
  as two trailing defaulted fields. Nothing renders and nothing blocks yet.
  ```

### Step 3: Block the merge verdict and surface the state

Details: [step_3.md](./steps/step_3.md) — depends on Step 2. Parts (a) suppression, (b) render line, (c) review-gate header and (d) docs ship as **one commit on purpose**: splitting them would leave a commit rendering `Review Gate: clean` beside a suppressed `Ready to merge`.

- [x] Implementation: one `and not linked_branch_blocking` term in `_generate_recommendations`; `_format_linked_branch_line` called from both formatters; `Review Gate: BLOCKED (linked branch)` in `_review_gate_header`; relink row in `.claude/skills/check_branch_status/SKILL.md` and conditional `Linked Branch:` expectation in Test 3.2 of `tests/LLM_Test.md`. Tests first: the seven groups in step_3.md including the end-to-end suppression test through `collect_branch_status`, plus the suppression + default cases in `test_branch_status_recommendations.py`; verify `test_rebase_behind_but_mergeable_squash_safe` and `test_confirmed_no_pr_stays_clean_eligible` stay green via their patch decorator — both already carried the step-2 decorator and needed no change; no other manager-patching test was exposed
- [x] Quality checks: pylint, pytest, mypy — fix all issues (1765 passed, 1 skipped; pylint and mypy clean)
- [x] Commit message prepared — as in steps 1 and 2, `pr_info/.commit_message.txt` could not be written (`.gitignore:48` excludes it; the workspace MCP refuses gitignored paths), so the text is recorded here instead:

  ```
  feat(checks): block the merge verdict on a non-OK linked branch

  Add one `and not linked_branch_blocking` term to the recommendation chain so
  a mismatched, ambiguous, unlinked or undeterminable linked branch suppresses
  `Ready to merge`. Render the state as a `Linked Branch:` line in both
  formatters and flip the review gate to `BLOCKED (linked branch)`, so the
  report never shows a clean gate beside a suppressed merge verdict.

  Suppression only — no new recommendation string; the message lives on the
  render line. The wording stays repo-neutral (the GraphQL query returns a bare
  `ref { name }`, which may be fork-hosted) and UNKNOWN stays neutral ("could
  not determine"), since a branch numbered for a nonexistent issue reaches
  UNKNOWN through the GraphQL-null path.

  Docs ride along because their wording is the wording chosen here: a relink row
  in the skill's Follow-Up Actions table, and a conditional `Linked Branch:`
  expectation in Test 3.2 of tests/LLM_Test.md — the line is suppressed on
  `main` and other non-issue branches, so it is not a fifth mandatory prefix.
  ```

## Pull Request

- [ ] PR review: verify all steps implemented as specified, no unresolved review comments
- [ ] PR summary: write title and description covering the change and its rationale

### CI fix: isort import formatting in server.py

- [x] Implementation: collapse the parenthesized single-name import at
  `src/mcp_workspace/server.py:37` back to one line, restoring the file
  byte-for-byte to `origin/main` (`git diff origin/main -- src/mcp_workspace/server.py`
  is empty)
- [x] Quality checks: pylint, mypy and black clean. pytest passes; the only
  failure was `tests/test_startup_performance.py::test_server_startup_under_two_seconds`
  (median 2.142s vs a 2.0s threshold) under `-n auto` CPU contention — it passes
  consistently with `-n 0`, and import formatting cannot affect runtime.
- [x] Commit message prepared — as in steps 1-3, `pr_info/.commit_message.txt`
  could not be written (`.gitignore:48` excludes it; the workspace MCP refuses
  gitignored paths for both `save_file` and `move_file`, and no shell tool is
  available in this session), so the text is recorded here instead:

  ```
  fix(server): restore single-line import to satisfy isort in CI

  The isort CI job failed on src/mcp_workspace/server.py:

    isort --check --profile=black --float-to-top src tests
    ERROR: src/mcp_workspace/server.py Imports are incorrectly sorted
           and/or formatted.

  A single-name import had been rewritten into a parenthesized multi-line
  form:

      from mcp_workspace.server_reference_tools import (
          set_reference_projects,
      )

  isort 9.0.1 (the version used in CI) normalizes a lone import that fits
  within line_length = 88 back to a single line without parentheses, so the
  file no longer matched isort's canonical output.

  Collapse it back to the single-line form, restoring the file byte-for-byte
  to its origin/main state, where this same CI step passes. This import block
  is outside the scope of the implementation plan, which lists server.py under
  "Unchanged (deliberately)", so no feature work depends on it.

  No other source or test file is affected. The surrounding
  server_reference_tools statements (the parenthesized
  get_reference_project_path / get_reference_repo_url block and the aliased
  register import) were already in isort's expected form.

  NOTE: the isort installed in the local dev environment disagrees with CI on
  this construct and actively rewrites the single-line import back into the
  parenthesized form. Running the local isort (tools/format_all.sh or
  run_format_code) will reintroduce this CI failure. Verify instead with the CI
  invocation itself, or by confirming that
  "git diff origin/main -- src/mcp_workspace/server.py" is empty.
  ```
