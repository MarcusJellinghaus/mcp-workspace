# Step 9 — Documentation: `CLAUDE.md` and `LLM_Test.md`

## Prompt for LLM

> Read `pr_info/steps/summary.md`, then implement this step
> (`pr_info/steps/step_9.md`) only. No code changes and no new tests — this is a
> documentation commit. Use MCP tools for all file operations.
> One commit at the end.

Depends on steps 3–7 (all five tools must exist).

---

## WHERE

- `.claude/CLAUDE.md` — the "Tool mapping" table and the "Allowed commands via
  Bash tool" block
- `tests/LLM_Test.md` — new Section 4, appended after Section 3 (the file
  currently ends at line 151)

## WHAT

### `.claude/CLAUDE.md`

Add five rows to the tool-mapping table, after `Search GitHub`:

| Task | MCP tool |
|------|----------|
| Create GitHub issue | `mcp__mcp-workspace__github_issue_create` |
| Edit GitHub issue | `mcp__mcp-workspace__github_issue_edit` |
| Comment on GitHub issue | `mcp__mcp-workspace__github_issue_comment` |
| Create GitHub PR | `mcp__mcp-workspace__github_pr_create` |
| List GitHub labels | `mcp__mcp-workspace__github_label_list` |

Remove from the Bash allowlist block:

```
gh issue create / edit / comment (labels only via set-status)
gh pr create
```

**Keep** `gh issue view (cross-repo only)`, `gh run view`, the `git` commands,
and `mcp-coder gh-tool set-status <label>` — none of those has an MCP
equivalent. The existing "Status labels" paragraph directly under the block
stays as written.

The table and the allowlist are one statement read from two directions, so both
change in this commit.

### `tests/LLM_Test.md`

New Section 4, appended at the end:

```markdown
## Section 4: GitHub write tools (MUTATING — opt-in)

**These tools create and modify real GitHub objects.** Run only when you intend
to write to the repository. GitHub has no issue-delete API, so the test issue is
closed rather than removed.

### Test 4.1: Issue create → edit → comment → close

1. `github_label_list()` — expect one line per label with name, `#color` and description
2. `github_label_list(search="bug")` — expect the filtered subset
3. `github_issue_create(title="LLM test - safe to close", body="Created by tests/LLM_Test.md Section 4.")` — expect `Created issue #N — <url>`
4. `github_issue_comment(number=<N from step 3>, body="Test comment.\nSecond line.")` — expect `Added comment to issue #N — <url>`
5. `github_issue_edit(number=<N>, title="LLM test - edited", add_labels=["<a real label from step 1>"])` — expect `Updated issue #N`, then a `Labels:` line containing that label
6. `github_issue_edit(number=<N>, remove_labels=["<a label NOT on the issue>"])` — expect success, not an error: the no-op removal is filtered out
7. `github_issue_edit(number=<N>, add_labels=["status-01:created"])` — expect an error naming `mcp-coder gh-tool set-status`, and no change to the issue
8. `github_issue_edit(number=<N>, add_labels=["definitely-not-a-real-label"])` — expect an error naming the unknown label
9. `github_issue_edit(number=<N>, state="closed")` — expect `(state: closed)`

### Test 4.2: PR creation guards (no PR is created)

Only the rejection paths are scripted — creating a real PR needs a real branch.

1. `github_pr_create(title="")` — expect an empty-title error
2. `github_pr_create(title="x", head="main", base="main")` — expect a head/base error
3. `github_pr_create(title="x", head="bad~name")` — expect an invalid-branch-name error
```

## HOW

- Section 4 is **not** folded into Section 3, which must stay safe to run
  casually.
- `.claude/settings.local.json` is **not** touched. The five write tools stay off
  the permission allowlist deliberately — that is the local half of the
  "hidden per-client" story, and adding them would undo it.

## ALGORITHM

None — documentation only.

## DATA

None.

## Tests

None. Verify by reading the rendered markdown: the five rows are present in the
tool table, the two `gh` lines are gone from the allowlist, and
`git diff .claude/settings.local.json` is empty.

## Checks

`run_pytest_check` once to confirm nothing regressed. Pylint, mypy and vulture
are unaffected by markdown.

## Commit

`Document GitHub write tools in CLAUDE.md and LLM_Test.md`
