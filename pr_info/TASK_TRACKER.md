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

### Step 1: Bug 1 — UTF-8 decode chokepoint (`run_git_text`) ([details](./steps/step_1.md))

- [x] Implementation (tests + production code): add `run_git_text` helper in `core.py`, route all 12 read-only call sites in `read_operations.py`, add unit guards, fix broken str→bytes mocks
- [x] Quality checks: pylint, pytest (fast set + `git_integration` markers), mypy — fix all issues
- [x] Commit message prepared: `fix(git): decode read-only git output as UTF-8 via run_git_text chokepoint`

### Step 2: Bug 2 — content-aware search for `git show <blob>` ([details](./steps/step_2.md))

- [ ] Implementation (tests + production code): add `filter_content_output` in `output_filtering.py`, select it in `git_show` when `has_colon`, add unit tests + real-repo integration guard
- [ ] Quality checks: pylint, pytest (fast set + `git_integration` markers), mypy — fix all issues
- [ ] Commit message prepared: `fix(git): use line-based filter for show <blob> search (content, not diff)`

## Pull Request

- [ ] PR review completed
- [ ] PR summary prepared
