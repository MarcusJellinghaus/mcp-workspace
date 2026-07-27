# Decisions — Issue #49

## 2026-07-27 — Expand scope to the README Features bullet (Option B)

User chose to expand the fix scope to a third human-facing description: the
`move_file` bullet in the README Features list (`README.md:31`), which had the same
git-agnostic wording as the two locations already in the plan. All three human-facing
descriptions (`server.py:413` docstring, `README.md:221` table row, `README.md:31`
Features bullet) should now agree and document the git-aware behavior.

The `README.md:332-336` Move File detail section stays **out of scope** — it already
documents git behavior correctly. Still a single step / single commit (documentation
edits only).
