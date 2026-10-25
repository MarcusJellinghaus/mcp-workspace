# Step 5 — Record the read-only token permission check

## LLM prompt
> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_5.md`. Steps 1–4 are done.
> This step changes a docstring only. Run pylint, pytest (`-n auto`) and mypy through the MCP tools;
> all must pass. Format with `run_format_code`, then make exactly one commit.

## Context
The issue's Decisions table calls the token check a "Documentation task, not a gate". This step
never blocks.

## WHERE
`src/mcp_workspace/github_operations/_ruleset_protection.py` (module docstring)

## WHAT
Read issue #350 with `mcp__mcp-workspace__github_issue_view` and look for a comment that reports
whether a read-only fine-grained token can read `GET /repos/{o}/{r}/rules/branches/{b}` and
`GET /repos/{o}/{r}/rulesets`, and which permission each needs.
- **Result found:** replace step 1's "not yet verified" `Token permissions:` paragraph with that
  result: for each endpoint, the permission it needs and the observed status.
- **No result found:** keep step 1's "not yet verified" paragraph unchanged. Add a line to
  `pr_info/TASK_TRACKER.md` that says the token check is still open and must be flagged in the PR
  description. If nothing else changed, skip the commit.

## HOW
Text only. No code or behaviour changes and no new tests. The PR description repeats the recorded
result, or states that the check is still open (done when the PR is created).

## DATA
None.
