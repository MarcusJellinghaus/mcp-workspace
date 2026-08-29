# Implementation review log 3

Issue: [#255](https://github.com/MarcusJellinghaus/mcp-workspace/issues/255) — GitHub read tools: support reference projects for cross-repo reads

Branch: `255-github-read-tools-reference-projects-v2`

Supervised review run 3. Earlier runs: [log 1](./implementation_review_log_1.md), [log 2](./implementation_review_log_2.md).

**Branch changed since run 2.** The original branch
(`255-github-read-tools-support-reference-projects-for-cross-repo-reads`) could not be
rebased onto main: main had added the GitHub write tools (`9245ad9`, `server.py` +637),
rewritten the `github_search` query builder (`c4a88d7`), and split
`test_github_read_tools.py` into `test_github_read_tools_issues.py` and
`test_github_read_tools_pr_search.py`. Replaying the 18 commits conflicted on `server.py`
and on a modify/deleted test file in five of them, so the net diff was re-applied once onto
`origin/main` as a single commit on a new branch. The old branch is retained until this
review completes.

## Round 1 — 2026-08-29

Reviewed `origin/main..HEAD` on the new branch. Checks: pytest 2096 passed / 2 skipped,
mypy clean, pylint clean, ruff clean, vulture clean, lint-imports 9/9 kept.

**Re-application verified.** Nothing from main was dropped: `github_issue_list` still
over-fetches by one and passes the unincremented cap to the formatter, and main's rewritten
`github_search` query builder is untouched apart from the `_issue_manager()` and
`_repo_access_error()` call sites. Nothing from the old branch was lost. The three helper
bodies in `_github_read_tools_helpers.py` are identical to the local copies they replace, and
all four "Could not access repository" assertion sites were updated.

**Findings**:

- `README.md:460` — medium — "Reads only — there are no GitHub write tools" was true on the
  branch's old base and is false on main, which added five GitHub write tools in `9245ad9`.
  Carried across verbatim in the README re-application.
- `README.md:213-229` — low — the Available Tools table gained rows for the four read tools
  but has none for main's five write tools.

**Decisions**:

- Accept the first. The statement is factually wrong on this base and this branch introduced
  it; it is also the only place in `README.md` or `docs/` that describes GitHub write access.
- Skip the second. Main added the write tools without README rows, so the omission is
  pre-existing, and documenting another feature is out of scope for this issue.
- Dismissals from runs 1 and 2 stay dismissed: the `get_reference_projects()` docstring
  wording, the unreachable `if repo_full_name else ""` fallback, and the `github_pr_view` 404
  asymmetry.

**Changes**: `README.md` — the bullet now states that `reference_name` is accepted by these
four tools alone and that every other GitHub tool targets the workspace repository, which
stays accurate without misclassifying `github_label_list` as a write tool.

**Status**: committed

## Final Status

One round, one accepted finding — a documentation line, so no further round was run.

| Check | Result |
|---|---|
| pytest | 2096 passed, 2 skipped, 0 failed |
| mypy | clean |
| pylint | clean |
| vulture | no output |
| lint-imports | 9 kept, 0 broken |
| CI | PASSED |

`check_branch_status` reports `Rebase=BEHIND`, which is a false positive: it detects the base
as the stale local branch `232-expose-github-write-mcp-tools-…` rather than `main`, and
`git log HEAD..origin/main` is empty.

The superseded branch `255-github-read-tools-support-reference-projects-for-cross-repo-reads`
still exists locally and on origin, to be deleted once this work merges.
