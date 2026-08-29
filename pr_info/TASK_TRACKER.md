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

### Step 8: `perm_write` permission probe

Details: [step_8.md](./steps/step_8.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared: `Add perm_write probe to verify_github`
      Final text is at `pr_info/commit_message_step8.txt`, following the step-1
      to step-7 convention: `pr_info/.commit_message.txt` is gitignored
      (`.gitignore:48`) and the workspace MCP server refuses gitignored paths
      for `save_file`.

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

- [ ] PR review — address review feedback
- [ ] PR summary prepared (include the manual read-only-token result for the `perm_write` probe, per summary.md)
- [ ] **BLOCKING, still open:** run `_probe_write` once against a deliberately
      read-only token (`BaseGitHubManager(github_token=…)` accepts one
      explicitly) and record the observed `repo.permissions.push` value in the
      PR description. If it reports `push: true` for a token with no write
      grant, that is a false green — drop the `perm_write` probe rather than
      ship it, per the acceptance criterion in issue #232 and summary.md.
      Not doable from the review environment: it needs a second, deliberately
      read-only GitHub token that is not available here, and the result cannot
      be inferred from the code — it is a property of GitHub's API.
