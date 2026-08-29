---
description: Update GitHub issue with refined content from analysis discussion
disable-model-invocation: true
argument-hint: "<issue-number>"
allowed-tools:
  - mcp__mcp-workspace__github_issue_edit
  - mcp__mcp-workspace__github_issue_view
  - mcp__mcp-workspace__read_file
  - mcp__mcp-workspace__list_directory
  - mcp__mcp-workspace__search_files
---

# Update GitHub Issue

Based on our prior `/issue_analyse` discussion, update the GitHub issue with refined content.

**Instructions:**
1. If no issue context is found from prior analysis, respond: "No issue context found. Please run `/issue_analyse <number>` first."

2. First, fetch the current issue content:
   Call `mcp__mcp-workspace__github_issue_view` with the issue number.

3. Draft updated issue text with:
   - Clear, concise title
   - Well-structured body with implementation ideas

4. Update the issue in one call:
```python
mcp__mcp-workspace__github_issue_edit(number=<issue_number>, title="NEW_TITLE", body=body_content)
```

The body is passed inline — no temp file, no bash escaping.

**Editing Base Branch:**
- To add a base branch: Insert `### Base Branch` section with the branch name
- To change a base branch: Update the content under the existing section
- To remove a base branch: Delete the entire `### Base Branch` section

The base branch must be a single line. Multiple lines will cause an error during branch creation.

**The updated issue should include:**
- Summary of the requirement
- Discussed implementation approach (concise)
- `## Constraints & Rationale` — non-obvious gotchas and the "why" behind decisions. Skip if none identified.
- `## Decisions` table — decided topics so `/issue_analyse` won't re-ask. Skip if none yet.
- **`## Dependencies / references`** — preserve the links to the epic, design doc, dependencies, and curated siblings when rewriting; add the section if missing and the issue isn't standalone.
