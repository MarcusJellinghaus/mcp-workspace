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

### Step 1: Library prerequisites — `create_issue` assignees, honest `get_available_labels`

Details: [step_1.md](./steps/step_1.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared: `Add create_issue assignees and stop get_available_labels swallowing errors`
      Final text is at `pr_info/commit_message_step1.txt`. It could not be placed
      at `pr_info/.commit_message.txt`: that path is gitignored (`.gitignore:48`)
      and the workspace MCP server refuses gitignored paths for `save_file`,
      `append_file` and `move_file` alike.
      Step 1 code is already committed as `67fc8cc`, so the message has served its
      purpose; `commit_message_step1.txt` is itself tracked (committed in
      `6e71278`) and should be deleted once this PR is wrapped up.

### Step 2: `IssueManager.edit_issue` + `_issue_to_data`

Details: [step_2.md](./steps/step_2.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared: `Add IssueManager.edit_issue combined edit function`
      Final text is at `pr_info/commit_message_step2.txt`, following the step-1
      convention: `pr_info/.commit_message.txt` is gitignored (`.gitignore:48`)
      and the workspace MCP server refuses gitignored paths for `save_file`.

### Step 3: `github_issue_create` tool (+ `_check_labels`, `_resolve_assignees`)

Details: [step_3.md](./steps/step_3.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy, vulture — fix all issues
- [x] Commit message prepared: `Add github_issue_create MCP tool`
      Final text is at `pr_info/commit_message_step3.txt`, following the step-1
      and step-2 convention: `pr_info/.commit_message.txt` is gitignored
      (`.gitignore:48`) and the workspace MCP server refuses gitignored paths
      for `save_file`.

### Step 4: `github_issue_edit` tool

Details: [step_4.md](./steps/step_4.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy, vulture — fix all issues
- [x] Commit message prepared: `Add github_issue_edit MCP tool`
      Final text is at `pr_info/commit_message_step4.txt`, following the step-1
      to step-3 convention: `pr_info/.commit_message.txt` is gitignored
      (`.gitignore:48`) and the workspace MCP server refuses gitignored paths
      for `save_file`.

### Step 5: `github_issue_comment` tool

Details: [step_5.md](./steps/step_5.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy, vulture — fix all issues
- [x] Commit message prepared: `Add github_issue_comment MCP tool`
      Final text is at `pr_info/commit_message_step5.txt`, following the step-1
      to step-4 convention: `pr_info/.commit_message.txt` is gitignored
      (`.gitignore:48`) and the workspace MCP server refuses gitignored paths
      for `save_file`.

### Step 6: `github_label_list` tool

Details: [step_6.md](./steps/step_6.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy, vulture — fix all issues
- [x] Commit message prepared: `Add github_label_list MCP tool`
      Final text is at `pr_info/commit_message_step6.txt`, following the step-1
      to step-5 convention: `pr_info/.commit_message.txt` is gitignored
      (`.gitignore:48`) and the workspace MCP server refuses gitignored paths
      for `save_file`.

### Step 7: `github_pr_create` tool

Details: [step_7.md](./steps/step_7.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy, vulture — fix all issues
- [x] Commit message prepared: `Add github_pr_create MCP tool`
      Final text is at `pr_info/commit_message_step7.txt`, following the step-1
      to step-6 convention: `pr_info/.commit_message.txt` is gitignored
      (`.gitignore:48`) and the workspace MCP server refuses gitignored paths
      for `save_file`.

### Step 8: `perm_write` permission probe — REVERTED, not shipped

Details: [step_8.md](./steps/step_8.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared: `Add perm_write probe to verify_github`
      Final text is at `pr_info/commit_message_step8.txt`, following the step-1
      to step-7 convention: `pr_info/.commit_message.txt` is gitignored
      (`.gitignore:48`) and the workspace MCP server refuses gitignored paths
      for `save_file`.
- [x] **Reverted during review (round 2).** Issue #232 makes shipping the probe
      conditional on a one-off check with a deliberately read-only token: if
      `repo.permissions.push` reflects the *user's* repo access rather than the
      *token's* grant, `perm_write: OK` is a false green and the issue says to
      drop the probe rather than ship it misleading. That check needs a second,
      deliberately read-only GitHub token which is not available here, and the
      answer is a property of GitHub's API that cannot be inferred from the
      code — so the conditional resolves to "do not ship". `_probe_write`, the
      `perm_write` key and their tests are removed; `_PROBE_KEYS` is back to the
      six read probes. Re-open a follow-up issue if the token check is ever run.

### Step 9: Documentation — `CLAUDE.md`, issue skills, `LLM_Test.md`

Details: [step_9.md](./steps/step_9.md)

- [x] Implementation (documentation edits; no code, no new tests)
- [x] Quality checks: pytest — fix all issues
- [x] Commit message prepared: `Document GitHub write tools and switch issue skills to them`
      Final text is at `pr_info/commit_message_step9.txt`, following the step-1
      to step-8 convention: `pr_info/.commit_message.txt` is gitignored
      (`.gitignore:48`) and the workspace MCP server refuses gitignored paths
      for `save_file`.

## Pull Request

- [x] PR review — address review feedback
      Run 2 (`implementation_review_log_2.md`) ran four rounds on top of run 1's
      three. All accepted findings are implemented and committed. The one
      escalation, a `PyGithub Library Isolation` contract violation, was resolved
      by re-exporting `GithubException` from `github_operations` (`2da2144`).
      Still open, and **not** review feedback: the CI `isort` failure caused by a
      local/CI version split (local 8.0.1, CI 9.0.1, `pyproject.toml` pins only
      `isort>=5.13.2`), and the rebase onto `main`.
- [ ] PR summary prepared (note that the `perm_write` probe was dropped, per Step 8)
- [x] **Resolved (round 2): probe dropped, no longer blocking.** The read-only-token
      acceptance check could not be run here — it needs a second, deliberately
      read-only GitHub token that is not available in this environment, and the
      result is a property of GitHub's API that cannot be inferred from the
      code. Issue #232's stated fallback ("If it reports a false green, drop the
      probe rather than ship it misleading") therefore applies: `_probe_write`
      and the `perm_write` key are removed. Nothing about write permissions is
      claimed, so there is no false green left to validate.
