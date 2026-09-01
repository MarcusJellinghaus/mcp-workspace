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

### Step 1: Server-level MCP `instructions` — [step_1.md](./steps/step_1.md)

- [x] Implementation: add the instructions-content test to `tests/test_server.py`, then pass `instructions=` to `FastMCP(...)` in `src/mcp_workspace/server.py`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: Shrink the docstring and the `usage` value — [step_2.md](./steps/step_2.md)

- [x] Implementation: update both `usage` expectations in `tests/test_reference_projects_mcp_tools.py`, then the docstring and `usage` value in `src/mcp_workspace/server_reference_tools.py` and the example in `README.md`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 3: Prose enumerations become category descriptions — [step_3.md](./steps/step_3.md)

- [ ] Implementation: replace the prose enumerations in `README.md` and `.claude/CLAUDE.md` with category descriptions, and add the seven missing rows to the per-tool table
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review
- [ ] PR summary
