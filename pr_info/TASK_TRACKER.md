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

### Step 1: Config allowlist, trust helpers, README — [step_1.md](./steps/step_1.md)

- [ ] Implementation: tests first (`test_trust.py`, `test_config.py`, conftest autouse fixture), then `trust.py`, `config.py` (`_read_config_list`, `get_trusted_commenters`), `github_operations/__init__.py` re-exports, README "GitHub configuration" section
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 2: `author_association` on every data type and collection path — [step_2.md](./steps/step_2.md)

- [ ] Implementation: tests first, then `ReviewThreadData` + `author_association` on all TypedDicts, GraphQL/REST mapping, `_pr_to_data`, comments/review mixins, `server.py` item construction, all test fixtures (no rendering changes)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 3: `check_branch_status` gate — PR feedback and ❌ issue note — [step_3.md](./steps/step_3.md)

- [ ] Implementation: tests first, then `format_withheld_line`, `format_pr_feedback`/`collect_pr_feedback(trusted)`, ❌-note filter in `collect_branch_status`, `tach.toml` dependency for `mcp_workspace.checks`
- [ ] Quality checks: pylint, pytest, mypy (plus tach) — fix all issues
- [ ] Commit message prepared

### Step 4: `github_pr_view` gate — title/body, reviews, comments, inline comments — [step_4.md](./steps/step_4.md)

- [ ] Implementation: tests first, then `format_pr_view(trusted=...)`, `github_pr_view` (`pr_dict` user/association, ghost-safe logins, allowlist lookup), test fixture updates, `tach.toml` dependency for `mcp_workspace.server`
- [ ] Quality checks: pylint, pytest, mypy (plus tach) — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: review the full branch diff against `main`, address findings
- [ ] PR summary prepared
