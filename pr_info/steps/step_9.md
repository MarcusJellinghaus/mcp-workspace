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
- `.claude/skills/issue_create/SKILL.md` — `allowed-tools` (line ~6) and the
  create command (line ~43)
- `.claude/skills/issue_update/SKILL.md` — `allowed-tools` (line ~6) and the
  four-step `--body-file` tempfile flow (lines ~29-41)
- `.claude/skills/issue_approve/SKILL.md` — `allowed-tools` (line ~8) and the
  comment command (line ~48)
- `tests/LLM_Test.md` — new Section 4, appended after Section 3 (the file
  currently ends at line 151)

The three skills are in scope because the allowlist edit below is what makes
them wrong: each one *declares* and *instructs* a `gh` command this commit
removes from the sanctioned list. Changing CLAUDE.md alone would leave the
repository telling itself two different things.

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

Replace the Bash allowlist line

```
gh issue create / edit / comment (labels only via set-status)
```

with

```
gh issue comment (cross-repo only — otherwise use the MCP tool)
```

and remove

```
gh pr create
```

The cross-repo carve-out mirrors the existing
`gh issue view (cross-repo only)` line and matches this step's own
`issue_approve` edit below, which keeps `gh issue comment` for the
`--repo owner/repo` path: the MCP tools are repo-auto-detected and cannot reach
another repository, so that one use has no MCP equivalent.

**Keep** `gh issue view (cross-repo only)`, `gh run view`, the `git` commands,
and `mcp-coder gh-tool set-status <label>` — none of those has an MCP
equivalent. The existing "Status labels" paragraph directly under the block
stays as written.

The table and the allowlist are one statement read from two directions, so both
change in this commit.

### `.claude/skills/issue_create/SKILL.md`

- `allowed-tools`: replace `"Bash(gh issue create *)"` with
  `mcp__mcp-workspace__github_issue_create`. Keep `mcp__mcp-workspace__git`
  (used for the base-branch `ls_remote` check).
- Replace the create command with the tool call:

  ```python
  mcp__mcp-workspace__github_issue_create(title="TITLE", body="BODY")
  ```

  Note in the skill that the body is passed inline — no escaping, no heredoc.

### `.claude/skills/issue_update/SKILL.md`

- `allowed-tools`: replace `"Bash(gh issue edit *)"` with
  `mcp__mcp-workspace__github_issue_edit`.
- **Delete the whole tempfile dance** — current steps 4, 5 and 6 (`save_file` to
  `.scratch/issue_body_temp.md` → `gh issue edit --body-file` →
  `delete_this_file`) collapse into one call:

  ```python
  mcp__mcp-workspace__github_issue_edit(number=<issue_number>, title="NEW_TITLE", body=body_content)
  ```

  This is the concrete instance of the issue's "eliminates the
  `cat > /tmp/issue_body.md <<EOF` heredocs" claim, so it should not survive
  this PR. `mcp__mcp-workspace__delete_this_file` can then come off that skill's
  `allowed-tools` too, unless it is used elsewhere in the file — check before
  removing.
- The `### Base Branch` guidance and everything below it is unaffected.

### `.claude/skills/issue_approve/SKILL.md`

- `allowed-tools`: **add** `mcp__mcp-workspace__github_issue_comment`;
  **keep** `"Bash(MSYS_NO_PATHCONV=1 gh issue comment *)"` and
  `"Bash(gh issue view *)"`.
- Step 3 becomes: use `mcp__mcp-workspace__github_issue_comment(number=…,
  body="/approve")` for the current repo, and keep the `gh issue comment` form
  **only** for the documented `--repo owner/repo` cross-repo path — the MCP
  tools are repo-auto-detected and cannot reach another repository, exactly as
  the skill's own "Cross-Repo Issues" section already says about
  `github_issue_view`.
- The `MSYS_NO_PATHCONV=1` note stays with the Bash form; it is a Git Bash
  path-rewriting workaround and is irrelevant to the MCP call, which is worth
  saying since `/approve` is precisely the slash-prefixed argument that needed
  it.

**Not changed:** `.claude/skills/plan_review*`, `implementation_review*` and the
other skills reference only read tools.

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
- **The skill edits do not undo that.** A skill's `allowed-tools` frontmatter
  grants a tool *inside that skill's invocation only*; the global allowlist
  grants it everywhere. Naming `github_issue_create` in `issue_create`'s
  frontmatter is the same narrow grant `"Bash(gh issue create *)"` was, moved to
  a better tool. Outside those three skills the write tools still require
  per-call approval.

## ALGORITHM

None — documentation only.

## DATA

None.

## Tests

None. Verify by reading the rendered markdown:

- the five rows are present in the tool table;
- `gh issue create`, `gh issue edit` and `gh pr create` are gone from the
  allowlist, and `gh issue comment` now carries the cross-repo carve-out;
- `grep -r "gh issue create\|gh issue edit\|gh issue comment\|gh pr create" .claude/`
  returns nothing outside the cross-repo exceptions in `issue_approve` and the
  matching `gh issue comment (cross-repo only)` allowlist line in `CLAUDE.md`;
- `.scratch/issue_body_temp.md` is no longer referenced anywhere;
- `git diff .claude/settings.local.json` is empty.

## Checks

`run_pytest_check` once to confirm nothing regressed. Pylint, mypy and vulture
are unaffected by markdown.

## Commit

`Document GitHub write tools and switch issue skills to them`
