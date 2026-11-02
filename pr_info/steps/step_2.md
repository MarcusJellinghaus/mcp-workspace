# Step 2 — Docs: README "Commenter trust" and release notes

Read [summary.md](./summary.md) first.

## LLM prompt

> Implement Step 2 of `pr_info/steps/summary.md` as described in `pr_info/steps/step_2.md`.
> Change documentation only: update the README and `docs/release-notes.md`. Keep the wording
> short and in the style of the surrounding text. Run pylint, pytest (`-n auto`) and mypy to
> confirm nothing broke, then make one commit.

## Precondition

`IssueManager.check_body_trust` exists in
`src/mcp_workspace/github_operations/issues/manager.py` (Step 1 is done). If not, write one
line to `pr_info/.blocked.txt` and stop.

## WHERE

- `README.md`: section "GitHub configuration" (the `trusted_commenters` bullet, around line
  94) and section "Commenter trust" (around lines 106–115).
- `docs/release-notes.md`: the top `## Next minor release` section (line 3), subsection
  `### New API`.

## WHAT

1. **`trusted_commenters` bullet:** describe logins as trusted as authors and as issue body
   editors, without tying editors to `### Base Branch` alone. For example: "…trusted as
   authors (their comments are shown to the agent) and as issue body editors (see
   [Commenter trust](#commenter-trust)). There is no environment-variable override."
2. **New bullet under "Commenter trust"**, placed after the "Base branch" bullet:
   - "Body trust: `IssueManager.check_body_trust(issue)` applies the same rule as Base
     branch (author trusted, or last body editor is the token user or in
     `trusted_commenters`)."
   - It returns `BodyTrustResult(status, reason)`, and `status` is `BodyTrust.TRUSTED`,
     `UNTRUSTED` or `LOOKUP_FAILED`.
   - A failed lookup is never trusted. Rate limits raise `GitHubRateLimitError`. `reason`
     is a fixed message or an exception type name, so it is safe to log.
3. **Release notes, `### New API` of the top section:** append bullets:
   - `IssueManager.check_body_trust(issue) -> BodyTrustResult`. It does no caching,
     makes one editor GraphQL request per untrusted-author call, and raises
     `GitHubRateLimitError` on rate limits.
   - `issues.BodyTrust`: enum `TRUSTED` / `UNTRUSTED` / `LOOKUP_FAILED`, with values
     `trusted` / `untrusted` / `lookup_failed`.
   - `issues.BodyTrustResult`: `NamedTuple` with `status: BodyTrust` and `reason: str`.

## HOW / ALGORITHM / DATA

Not applicable. This step changes documentation only and adds no code or tests.
