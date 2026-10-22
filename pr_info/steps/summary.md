# Summary — #341: label the last ❌ issue comment and mark it when older than HEAD

## Problem

`check_branch_status` prints the newest ❌-marked trusted issue comment verbatim. Nothing labels it as an
issue comment or says when it was posted, so an old "could not be rebased" note can contradict
`Rebase=UP_TO_DATE` (mcp_coder#1166).

## Outcome

The comment body is always prefixed with one header line:

```
Last ❌ issue comment (by <user>, <YYYY-MM-DD HH:MM:SS UTC>; HEAD <sha7> committed <YYYY-MM-DD HH:MM:SS UTC> — may be outdated):
<full body>
```

- ` — may be outdated` appears only when the comment's `created_at` is **strictly** older than the
  committer date of local `HEAD`.
- Fallbacks: missing user → `unknown user`; missing/unparseable `created_at` → `unknown time`;
  HEAD lookup fails → `HEAD unknown`. Any fallback → no stale marker. The report never fails.
- Full body is always shown. Recommendations unchanged. Selection logic unchanged.

## Architectural / design changes

| Area | Change |
|------|--------|
| `github_operations.formatters` | `find_latest_marked_comment` returns the matched `CommentData` instead of the body string. Selection rule unchanged. |
| `git_operations.commits` | New `get_head_commit_info(project_dir) -> Optional[tuple[str, datetime]]`: HEAD short SHA (7 chars) + **committer** datetime converted to UTC. Swallows the same errors as `get_latest_commit_sha` and returns `None`. Exported from `git_operations/__init__.py`. |
| `checks.branch_status` (data) | `BranchStatusReport.last_automated_note: Optional[str]` replaced by five defaulted fields: `last_marked_comment`, `marked_comment_created_at`, `head_short_sha`, `head_committed_at`, `marked_comment_stale`. |
| `checks.branch_status` (collection) | New private helper `_marked_comment_context(project_dir, comment)` parses `created_at`, looks up HEAD and computes the stale verdict, owning all its own error handling. Called only when a marked comment was found. |
| `checks.branch_status_rendering` | `_format_last_automated_note_lines` → `_format_last_marked_comment_lines` builds header + full body; small `_format_utc` helper. Renderers stay pure (no git, no parsing) and read only report fields — never `last_marked_comment["created_at"]`. |
| `tach.toml` | `mcp_workspace.checks` may depend on `mcp_workspace.utils` (for `parse_iso_timestamp`). `.importlinter` already allows it. |

Design principles kept:
- **Compute in collection, render purely.** Stale verdict and HEAD info live on the report.
- **Committer date, local HEAD, no GitHub API.** A rebase rewrites committer date only.
- **No uncaught exceptions in collection.** `collect_branch_status` has one broad try/except whose fallback
  is an empty report; the new code must never reach it.
- `last_automated_note` has no external consumers — the rename is internal.

## Files

Created:
- `pr_info/steps/summary.md`, `pr_info/steps/step_1.md` … `step_3.md`

Modified:
- `src/mcp_workspace/git_operations/commits.py` — add `get_head_commit_info`
- `src/mcp_workspace/git_operations/__init__.py` — export it
- `src/mcp_workspace/github_operations/formatters.py` — `find_latest_marked_comment` return type
- `src/mcp_workspace/checks/branch_status.py` — report fields, `_marked_comment_context`, collection wiring
- `src/mcp_workspace/checks/branch_status_rendering.py` — header rendering
- `tach.toml` — `checks → utils` dependency
- `tests/git_operations/test_commits.py`
- `tests/github_operations/test_formatters.py`
- `tests/checks/test_branch_status.py`

No new source modules or packages.

## Steps

1. `get_head_commit_info` git helper + tests.
2. `find_latest_marked_comment` returns `CommentData`; report fields replace `last_automated_note`;
   renderer builds the header. Collection stores only the comment (header shows `unknown time` /
   `HEAD unknown` until step 3).
3. Collection fills timestamps, HEAD and stale verdict; `tach.toml` dependency; collection tests.

## Checks after every step

`mcp__mcp-tools-py__run_pylint_check`, `mcp__mcp-tools-py__run_mypy_check`,
`mcp__mcp-tools-py__run_pytest_check` (`extra_args: ["-n", "auto", "-k", "not github_search_live"]`),
`mcp__mcp-tools-py__run_tach_check`, `mcp__mcp-tools-py__run_lint_imports_check`, then
`mcp__mcp-tools-py__run_format_code` before committing.

The `-k` filter deselects the live GitHub search tests: search API indexing lag makes them flaky, this
issue doesn't touch search, and the CI github-integration job still runs them. All other GitHub
integration tests stay in.

`src/mcp_workspace/checks/branch_status.py` must stay ≤ 750 lines (`mcp__mcp-workspace__check_file_size`).
