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

### Step 1: `reference_name` on the four GitHub read tools

Details: [step_1.md](./steps/step_1.md)

- [x] Implementation: fixture, `_configure_manager` helper and six tests in `tests/github_operations/test_github_read_tools.py`; `get_reference_repo_url()` in `server_reference_tools.py`; `_issue_manager()` plus `reference_name` on `github_issue_view`, `github_issue_list`, `github_pr_view`, `github_search` in `server.py`, including the `github_search` scope wording
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: Name the API base URL in "Could not access repository"

Details: [step_2.md](./steps/step_2.md)

- [x] Implementation: extend `test_github_pr_view_no_repo` and `test_github_search_no_repo`; include the resolved `api_base_url` in the two error strings in `github_pr_view` and `github_search`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared — used by commit `115e6e1`; the transient `pr_info/.commit_message.txt` could not be written (gitignored, and the MCP workspace tools reject gitignored paths)

### Step 3: Documentation surfaces

Details: [step_3.md](./steps/step_3.md)

- [x] Implementation: `usage` string and docstring of `get_reference_projects()` plus the two exact-match assertions in `tests/test_reference_projects_mcp_tools.py`; update `README.md`, `.claude/CLAUDE.md`, `.claude/skills/issue_approve/SKILL.md` and `tests/LLM_Test.md`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared — same blocker as step 2: `pr_info/.commit_message.txt` is gitignored and the MCP workspace tools reject gitignored paths, so the message was handed back in the run output instead

## Pull Request

- [ ] PR review
- [ ] PR summary
