---
description: Create additional implementation steps after code review findings
disable-model-invocation: true
allowed-tools:
  - mcp__mcp-workspace__read_file
  - mcp__mcp-workspace__save_file
  - mcp__mcp-workspace__edit_file
  - mcp__mcp-workspace__list_directory
---

# Create Further Implementation Tasks

Append new implementation tasks to the project plan after code review identified areas needing additional work.

## Instructions

Please expand the **implementation plan** stored under `pr_info/steps`
Update the `pr_info/steps/Decisions.md` with the decisions we took.
Please create additional self-contained steps (`pr_info/steps/step_1.md`, `pr_info/steps/step_2.md`, etc.).
Please update the **summary** (`pr_info/steps/summary.md`).

### Requirements for the new implementation steps:
- Follow **Test-Driven Development** where applicable.
  Each step should have its own test implementation followed by related functionality implementation.
- Each step must include a **clear LLM prompt** that references the summary and that specific step
- Apply **KISS principle** - minimize complexity, maximize maintainability
- Keep code changes minimal and follow best practices

### Each Step Must Specify:
- **WHERE**: File paths and module structure
- **WHAT**: Main functions with signatures
- **HOW**: Integration points (decorators, imports, etc.)
- **ALGORITHM**: 5-6 line pseudocode for core logic (if any)
- **DATA**: Return values and data structures

Please also update the task tracker (`pr_info/TASK_TRACKER.md`).
