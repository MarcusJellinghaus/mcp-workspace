---
description: Create a new GitHub issue from discussion context
disable-model-invocation: true
argument-hint: "<title>"
allowed-tools:
  - "Bash(gh issue create *)"
  - mcp__mcp-workspace__git
---

# Create GitHub Issue

Based on our prior discussion, create a GitHub issue.

**Instructions:**
1. Extract the issue title and body from the conversation context
2. Use a clear, descriptive title
3. Include relevant details from our discussion in the body
4. Use markdown formatting for better readability

**Link related issues.** If the issue belongs to an epic or design doc, or has dependencies, list them near the top and in a `## Dependencies / references` section — the epic, design doc, dependencies, and any curated sibling issues worth reading. Add a short "read these first" note when they're essential. Omit for standalone issues.

**Optional: Base Branch**
If the feature should be based on a branch other than the default (main/master), include:

```markdown
### Base Branch

<branch-name>
```

Use cases:
- Hotfixes based on release branches
- Features building on existing work
- Long-running feature branches

**Important:** Before specifying a base branch, verify it exists:
Call `mcp__mcp-workspace__git` with command `"ls_remote"` and args `["--heads", "origin", "<branch-name>"]`.

If no base branch is needed, omit this section entirely.

**Create the issue using:**
```bash
gh issue create --title "TITLE" --body "BODY"
```

If no prior discussion context is found, respond: "No discussion context found. Please discuss the feature or bug first before creating an issue."
