---
description: Code review of implementation with compact diff analysis
disable-model-invocation: true
allowed-tools:
  - mcp__mcp-workspace__git
  - mcp__mcp-workspace__check_branch_status
  - mcp__mcp-workspace__read_file
  - mcp__mcp-workspace__list_directory
  - mcp__mcp-workspace__search_files
---

# Implementation Review (Code Review)

**First, ensure we're up to date:**
Call `mcp__mcp-workspace__git` with command `"fetch"` and args `["origin"]`.
Use `mcp__mcp-workspace__git` with command `"status"` to check working directory state.
Call `mcp__mcp-workspace__check_branch_status`.

Confirm and display the current feature branch name.

---

**Then run the code review:**

## Code Review Request

Use `mcp__mcp-workspace__git` with command `"diff"` to get the changes to review.

No need to run all checks; do not use pylint warnings. Feel free to further analyse any mentioned files and/or the file structure.

### Focus Areas:
- Logic errors or bugs
- Tests for `__main__` functions should be removed (not needed)
- Unnecessary debug code or print statements
- Code that could break existing functionality
- Compliance with existing architecture principles, see `docs/architecture/architecture.md`

### Output Format:
1. **Summary** - What changed (1-2 sentences)
2. **Critical Issues** - Must fix before merging
3. **Suggestions** - Nice to have improvements
4. **Good** - What works well

Do not perform any action. Just present the code review.
