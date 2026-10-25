# Step 4 — Record the read-only token permission check

## LLM prompt
> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_4.md`. Steps 1–3 are done.
> This step changes a docstring only. Run pylint, pytest (`-n auto`) and mypy through the MCP tools;
> all must pass. Format with `run_format_code`, then make exactly one commit.

## Precondition
Issue #350 (read it with `mcp__mcp-workspace__github_issue_view`) must contain a comment that
reports whether a read-only fine-grained token can read `GET /repos/{o}/{r}/rules/branches/{b}` and
`GET /repos/{o}/{r}/rulesets`, and which permission it needs. If no such comment exists, write one
line to `pr_info/.blocked.txt` and stop.

## WHERE
`src/mcp_workspace/github_operations/_ruleset_protection.py` (module docstring)

## WHAT
Replace the "not yet verified" `Token permissions:` paragraph from step 1 with the recorded result:
for each endpoint, the permission it needs and the observed status.

## HOW
Text only. No code or behaviour changes and no new tests. The PR description repeats the same
result (done when the PR is created).

## DATA
None.
