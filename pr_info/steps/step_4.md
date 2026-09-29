# Step 4 — documentation

Read [summary.md](./summary.md) first. Depends on Step 2. Docs only; no code and
no automated tests. All three surfaces are acceptance criteria (Decision 7).

## WHERE

Modified:

- `README.md` — the tool table, around line 246
- `tests/LLM_Test.md` — Section 4 (Test 4.1) and the reference-project section
  (Test 4.2)
- `.claude/CLAUDE.md` — the tool-mapping table

`docs/ARCHITECTURE.md` needs nothing: it mentions neither mixins nor individual
tools (verified by search).

## WHAT

**`README.md`** — three rows after `github_issue_edit`, matching the existing
`| tool | description | example prompt |` shape:

```
| `github_subissue_add` | Links an issue as a sub-issue of another | "Make issue 43 a sub-issue of 42" |
| `github_subissue_list` | Lists an issue's sub-issues | "What are the sub-issues of issue 42?" |
| `github_subissue_remove` | Unlinks a sub-issue from its parent | "Detach issue 43 from its parent" |
```

**`tests/LLM_Test.md`** — a new `### Test 4.4: Sub-issue link → list → unlink`
after Test 4.3, scripted in the file's existing numbered `call — expect …` style.
It needs two throwaway issues, so create both and close both:

1. `github_issue_create(title="LLM test parent - safe to close", ...)` → parent `#P`
2. `github_issue_create(title="LLM test child - safe to close", ...)` → child `#C`
3. `github_subissue_list(parent_number=<P>)` — expect `No sub-issues.`
4. `github_subissue_add(parent_number=<P>, child_number=<C>)` — expect
   `Linked #C as a sub-issue of #P — <url>`, with `(1 sub-issues)`
5. `github_subissue_list(parent_number=<P>)` — expect one line
   `#C  open  LLM test child - safe to close`
6. `github_subissue_add(parent_number=<P>, child_number=<C>)` again — expect an
   error naming duplicate sub-issues / one parent, not a success
7. `github_subissue_add(parent_number=<P>, child_number=<P>)` — expect
   `Error: an issue cannot be its own sub-issue`
8. `github_subissue_add(parent_number=<P>, child_number=0)` — expect
   `Error: invalid issue number: 0`
9. `github_subissue_remove(parent_number=<P>, child_number=<C>)` — expect
   `Unlinked #C from #P — <url>`
10. `github_subissue_remove(parent_number=<P>, child_number=<C>)` again — expect
    a 404 error, not a silent success
11. `github_subissue_list(parent_number=<P>)` — expect `No sub-issues.`
12. Close both issues with `github_issue_edit(..., state="closed")`

In the reference-project section (Test 4.2), append one step: repeat the
add → list → remove cycle with `reference_name=<name>` on every call, noting that
one `reference_name` scopes **both** numbers and that cross-repo linking is not
supported.

**`.claude/CLAUDE.md`** — three rows in the tool-mapping table, next to the other
GitHub issue entries:

```
| Link a sub-issue | `mcp__mcp-workspace__github_subissue_add` |
| List sub-issues | `mcp__mcp-workspace__github_subissue_list` |
| Unlink a sub-issue | `mcp__mcp-workspace__github_subissue_remove` |
```

This row is what makes an agent in this repo reach for the MCP tool instead of a
raw `gh api` call — the gap that produced issue #294.

## HOW

Plain Markdown edits. Match each file's existing table columns, heading depth and
numbering style. Keep the prose short: the repo's writing style is "say it once".

## ALGORITHM

None.

## DATA

None.

## Checks

`run_format_code`, then pylint, pytest `-n auto`, mypy, vulture, ruff,
lint-imports — all should be unaffected, but run them so the commit is verified
like every other.

## Commit

`docs: document the sub-issue tools (#294)`

## LLM prompt

> Implement Step 4 of the sub-issue tools feature for issue #294. Steps 1–3 are
> already committed.
> Read `pr_info/steps/summary.md` and `pr_info/steps/step_4.md` first.
> Update the three documentation surfaces exactly as step_4 describes:
> `README.md`'s tool table, a new Test 4.4 plus a reference-project step in
> `tests/LLM_Test.md`, and `.claude/CLAUDE.md`'s tool-mapping table. Match each
> file's existing style and keep the prose short. Do not change
> `docs/ARCHITECTURE.md` — it documents neither mixins nor individual tools.
> Then run `run_format_code` followed by pylint, pytest (`extra_args=["-n","auto"]`),
> mypy, vulture, ruff and lint-imports, and make one commit.
