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

### Step 1: Document git-aware behavior in the surfaced `move_file` descriptions

Detail: [step_1.md](./steps/step_1.md)

- [x] Implementation: update the three surfaced `move_file` descriptions — `server.py` docstring summary line, `README.md` table row (~line 221), and `README.md` Features bullet (~line 31)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared — content is in [step_1.md](./steps/step_1.md) under "## Commit message": `Clarify move_file description: document git-aware behavior (#49)`. NOTE: `pr_info/.commit_message.txt` cannot be written by this agent (gitignored at `.gitignore:48`; `save_file`/`append_file` refuse ignored paths and no Bash tool is available), so the downstream commit step must read the message from step_1.md.

## Pull Request

- [ ] PR review addressed
- [ ] PR summary written
