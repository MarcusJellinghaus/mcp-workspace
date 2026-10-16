# Step 5 — Update the `check_branch_status` skill's follow-up-action table

## Prompt for LLM

Read `pr_info/steps/summary.md` for full context on issue #316, then implement this
step only. This step depends on steps 1–4 being committed (the behavior it documents
must already exist). This is a documentation-only change — no tests apply. Produce
exactly one commit.

Precondition: `.claude/skills/check_branch_status/SKILL.md` must still contain a
"Follow-Up Actions" table with a row `| Linked branch not OK | Relink the branch in
the issue's Development panel |`. If not, write one line to `pr_info/.blocked.txt`
naming the mismatch and stop.

## WHERE

- `.claude/skills/check_branch_status/SKILL.md` — replace one row in the
  "Follow-Up Actions" table with two rows.

## WHAT

Replace:

```markdown
| Linked branch not OK | Relink the branch in the issue's Development panel |
```

with:

```markdown
| Linked branch `MISMATCH` / `NOT_LINKED` / `AMBIGUOUS` / `UNKNOWN` | Relink the branch in the issue's Development panel, or open a PR on this branch with `Closes #N` in its body |
| Linked branch `LINKED_VIA_PR` | Already satisfies the check — no action needed |
```

## HOW

Direct text edit via the MCP edit tool — no imports, no code paths, no decorators.

## ALGORITHM

N/A — single table-row replacement.

## DATA

N/A — documentation only.
