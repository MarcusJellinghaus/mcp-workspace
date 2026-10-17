# Step 6 — README documentation

See `pr_info/steps/summary.md` for full context. Docs-only step; no test
changes, since there is nothing executable to assert on.

## Precondition

`README.md` must contain the usage synopsis line and flag bullet list exactly
as quoted below (around line 69 and following). If the wording has diverged,
write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `README.md` (modify)

## WHAT

No code. Two edits to existing prose.

## HOW

1. Usage synopsis (currently):
   ```
   mcp-workspace --project-dir /path/to/project [--reference-project NAME=/path/to/reference]... [--log-level LEVEL] [--log-file PATH] [--file-size-limit N]
   ```
   Append ` [--fail-on-reviews] [--enforce-base-branch-format]` (both missing
   today) before the closing backtick.

2. Flag bullet list (currently ends after `--file-size-limit`): add two
   bullets, matching the existing style:
   ```
   - `--fail-on-reviews`: (Optional) Default for `check_branch_status`' review gate; the tool parameter overrides per call. Off unless set.
   - `--enforce-base-branch-format` / `--no-enforce-base-branch-format`: (Optional) Reject a malformed `### Base Branch` section (more than one line) when creating or editing an issue body, in `github_issue_create` and `github_issue_edit`. On by default.
   ```

## ALGORITHM

None — documentation only.

## DATA

None.

## TDD order

Not applicable (no executable behavior). Still run the full check suite to
confirm the edit introduced no stray markdown issues that a linter catches,
and that nothing else broke.

## Checks and commit

Run `mcp__mcp-tools-py__run_pylint_check`, `mcp__mcp-tools-py__run_pytest_check`
(`extra_args: ["-n", "auto"]`), `mcp__mcp-tools-py__run_mypy_check` — all
should be unaffected and pass. Then one commit:

```
docs(readme): document --enforce-base-branch-format and --fail-on-reviews

Add both flags to the usage synopsis and the flag bullet list;
--fail-on-reviews was missing from both before this issue.
```

## LLM prompt for this step

```
Read pr_info/steps/summary.md for context, then implement
pr_info/steps/step_6.md exactly as written: update README.md's usage
synopsis and flag bullet list to document --enforce-base-branch-format /
--no-enforce-base-branch-format, and add the previously-missing
--fail-on-reviews bullet in the same edit. Make no code changes. Run pylint,
pytest (-n auto), and mypy to confirm nothing broke. If the precondition in
step_6.md does not hold, write one line to pr_info/.blocked.txt and stop.
Make exactly one commit.
```
