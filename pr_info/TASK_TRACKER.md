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

### Step 1: Ref-name check for `### Base Branch` (read and write time) + README flag line
See [step_1.md](./steps/step_1.md)

- [x] Implementation: tests for `is_valid_ref_name`, `InvalidBaseBranchRefError`, `format_malformed_base_branch`, write-tool rejection and MALFORMED line; then `base.py` validator/error/message, docstrings in `server.py` / `branch_status.py`, README `--enforce-base-branch-format` line
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: `IssueData.author_association` + shared `issue_to_data`
See [step_2.md](./steps/step_2.md)

- [x] Implementation: tests for `issue_to_data`, `create_empty_issue_data`, `get_issue` / `list_issues` / labels-mixin results; then add required `author_association` key, move converter into `types.py`, use it in `manager.py` and `labels_mixin.py`, default `"OWNER"` in test helpers and fixtures
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 3: `base_branch_trust.py` — editor lookup + body trust decision
See [step_3.md](./steps/step_3.md)

- [ ] Implementation: tests in `test_base_branch_trust.py` for `fetch_body_editor` and `is_body_trusted`; then the new module (GraphQL editor query, role → allowlist → editor check, never raises)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 4: Base Branch gate in `IssueManager`
See [step_4.md](./steps/step_4.md)

- [ ] Implementation: tests for trusted/untrusted bodies in `get_issue` / `list_issues`, failure handling, allowlist laziness, end-to-end `check_branch_status` / `get_base_branch`; then gate `_parse_base_branch_fields` with `is_body_trusted` and a per-call cached allowlist
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 5: Fenced `format_issue_view` + summary line
See [step_5.md](./steps/step_5.md)

- [ ] Implementation: tests for fencing, summary line, fence id, ghost/allowlisted authors, `max_lines` truncation, `github_issue_view` fence id and allowlist reads; then `_fence`, `trusted` / `fence_id` keywords in `format_issue_view`, `_allowlist_for` and wiring in `github_issue_view`
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 6: `[untrusted @login]` prefix in list/search/sub-issue tools + README trust section
See [step_6.md](./steps/step_6.md)

- [ ] Implementation: tests for `untrusted_prefix`, `format_issue_list`, `format_search_results`, `github_search`, `github_subissue_list`, `github_issue_list`; then the prefix helper, `trusted` keyword in formatters, server wiring, search item fields, README trust section
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: review the full branch diff against `main` and address findings
- [ ] PR summary prepared
