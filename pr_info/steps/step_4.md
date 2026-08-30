# Step 4 — Documentation

**Goal:** the two non-code files that describe `check_branch_status`' output
mention the new line.

Depends on step 3 (the wording must match what actually renders).
Documentation only — no source changes.

## WHERE

| File | Change |
|---|---|
| `.claude/skills/check_branch_status/SKILL.md` | One row in the status→action table |
| `tests/LLM_Test.md` | Test 3.2 expectation |

## WHAT / HOW

### a. `SKILL.md`

The file is a short skill definition whose *Follow-Up Actions* table maps a
reported status to the action to take. Add a row for the new state, keeping the
existing two-column format and terse style:

```
| Linked branch not OK | Relink the branch in the issue's Development panel |
```

Place it with the other blocking rows, above the two "ready" rows at the bottom
of the table. Do not touch the frontmatter (`description`, `allowed-tools`).

### b. `tests/LLM_Test.md`

Test 3.2 (`tests/LLM_Test.md:149-155`) lists the line prefixes a live
`check_branch_status(ci_timeout=0, pr_timeout=0)` call must produce. The four
existing prefixes are unconditional.

`Linked Branch:` is **not** unconditional — the state is `NOT_CHECKED` and the
line is suppressed entirely on `main` and on any branch whose name does not
start with `<digits>-`. So it must be added as a conditional expectation, not
as a fifth bullet in the mandatory list. For example, after the existing list:

```
   Additionally, when run on an issue-numbered branch (`<number>-...`), expect a
   `"Linked Branch:"` line; it is absent on `main` and other non-issue branches.
```

Keep the existing four bullets exactly as they are.

## DATA

None — prose only.

## Definition of done

- Both files updated; the SKILL.md table still renders as valid Markdown.
- No source or test-code changes in this commit.
- Run `mcp__tools-py__run_pytest_check` once to confirm the docs commit changed
  nothing (`tests/checks/test_file_sizes.py` and any docs-adjacent test still
  pass). Pylint and mypy have nothing to do here but cost nothing to run.
- One commit.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_4.md`. Steps 1-3 are
> done and the `Linked Branch:` line now renders.
>
> Implement step 4: documentation only. Add a relink row to the *Follow-Up
> Actions* table in `.claude/skills/check_branch_status/SKILL.md`, and add the
> new line to Test 3.2 in `tests/LLM_Test.md` as a **conditional** expectation —
> the line is suppressed on `main` and other non-issue branches, so it must not
> join the four unconditional prefixes.
>
> Check the wording you document against what `_format_linked_branch_line`
> actually produces in `src/mcp_workspace/checks/branch_status_rendering.py`.
>
> Change no source or test code in this commit. Use `mcp__workspace__*` for file
> operations per `.claude/CLAUDE.md`, run
> `mcp__tools-py__run_pytest_check` once to confirm nothing regressed, and
> produce exactly one commit.
