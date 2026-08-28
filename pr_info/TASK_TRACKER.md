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

### Step 1: `formatters.truncate_output` — name the cap and `max_lines`

Details: [step_1.md](./steps/step_1.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: `output_filtering.truncate_output` — restyle to the house pattern

Details: [step_2.md](./steps/step_2.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 3: `ci_log_parser` — one marker, one spelling, name `max_log_lines`

Details: [step_3.md](./steps/step_3.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared (message used directly in commit `e3620de`
      "fix(ci_log_parser): unify truncation marker and clamp caps";
      `pr_info/.commit_message.txt` could not be written because it is gitignored
      and the MCP workspace server refuses gitignored paths, and the step is
      already committed so the transient file is moot)

### Step 4: `github_issue_list` — make the silent truncation notice reachable

Details: [step_4.md](./steps/step_4.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared (recorded below; `pr_info/.commit_message.txt`
      could not be written because it is gitignored and the MCP workspace
      server refuses gitignored paths, as in step 3)

  ```
  Emit a truncation notice from github_issue_list by over-fetching one result

  format_issue_list guarded its notice with len(issues) > max_results, but its
  only production caller capped the list at max_results first, so the condition
  was never true and the tool truncated silently.

  github_issue_list now clamps max_results with max(0, max_results) and asks
  the manager for capped + 1 issues; the surplus item is what proves more
  results exist, since issue listing has no total count. The formatter still
  receives the capped value and renders "30+". Without the clamp a negative
  max_results rendered "... showing -1 of -1+ results" over an empty list.

  The notice follows the house style: it states the applied cap and names the
  parameters that lift or narrow it, without naming a query parameter that this
  tool does not accept.
  ```

### Step 5: `github_search` — emit a notice with the exact total from `totalCount`

Details: [step_5.md](./steps/step_5.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 6: `pr_feedback` — reorder sections, restyle notices, add a conditional footer

Details: [step_6.md](./steps/step_6.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 7: `tree_listing` — name the narrowing options in the truncation summary

Details: [step_7.md](./steps/step_7.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 8: `file_tools` internal caps — state the cap in `search.py`, document both

Details: [step_8.md](./steps/step_8.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review
- [ ] PR summary
