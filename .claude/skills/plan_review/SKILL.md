---
description: Review implementation plan for completeness, simplicity, and risks
disable-model-invocation: true
allowed-tools:
  - mcp__mcp-workspace__git
  - mcp__mcp-workspace__read_file
  - mcp__mcp-workspace__list_directory
  - mcp__mcp-workspace__search_files
---

# Review Implementation Plan

**First, ensure we're up to date:**
Call `mcp__mcp-workspace__git` with command `"fetch"` and args `["origin"]`.
Use `mcp__mcp-workspace__git` with command `"status"` to check working directory state.

Confirm and display the current feature branch name.

---

**Then review the plan:**

Please review the project plan for a new feature in folder `pr_info/steps`.
Please revise the project plan with a balanced level of detail.
Please let me know if any complexity could be reduced.
Please let me know any questions / comments or suggestions you might have.

Please consider the already discussed and decided decisions (if any) under decisions.
We do not need to challenge them again unless absolutely necessary.

**Focus on:**
- Completeness of implementation steps
- Appropriate level of detail
- Opportunities for simplification (KISS principle)
- Test coverage strategy
- Step granularity — each step should produce exactly one commit. Flag steps with multiple independent parts (A, B, C) that should be split.
- Potential risks or blockers
- **Requirement changes** — flag new dependencies (`pyproject.toml`) that should be applied during planning, not deferred to implementation

For planning standards, see `.claude/knowledge_base/planning_principles.md`.
