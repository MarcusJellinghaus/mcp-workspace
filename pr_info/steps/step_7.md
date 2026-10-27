# Step 7: README + release notes

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_7.md` exactly.
> Docs only. Run pylint, pytest (`-n auto`) and mypy to confirm nothing broke. One commit.

## WHERE

- Modify `README.md` — new section `## GitHub caches` after `## GitHub configuration`
  (and its `### Commenter trust` subsection).
- Modify `docs/release-notes.md` — new entry at the top.

## WHAT

### README section (short, tables over prose)

- **Files**: `<app-data>/mcp_coder/coordinator_cache/<owner_repo>.issues.json`,
  `.prs.json`, `.branches.json`. Safe to delete; rebuilt on next run.
- **Validity rule**: fingerprints; 6 h maximum age as safety net; not-final results never stored;
  errors never stored; on rate limit `GitHubRateLimitError` and nothing saved.
- **What is cached** — the layer-2 table from `summary.md` (slot → fingerprint → not final)
  plus the open-PR snapshot (60 s duplicate protection) and the branch lookup
  (found / not found / ambiguous, fingerprint = issue `updated_at`).
- **What stays live**: `set_status`, label transitions, `create_plan` prerequisites,
  `fix_conflict` mergeability polling, CI wait loops in `check_branch_status` / `create_pr`,
  CI status for a branch without an open PR, all MCP server tools.
- **Concurrency**: save reloads and merges per entry; no lock.

### Release-notes entry

- New: `GitHubRateLimitError` (exported from `mcp_workspace.github_operations`; `message`, `reset_at`).
- New: `caching.pull_requests.PullRequestCache`, `caching.branches.BranchLookupCache`,
  `invalidate_branch_entry`, `IssueBranchManager.resolve_branch_for_issue`, `BranchLookup`,
  `get_issue_cache_last_checked`.
- Behaviour change: `get_all_cached_issues` raises `GitHubRateLimitError` on a rate limit
  instead of returning stale data (other errors unchanged).
- Behaviour change: `get_branch_with_pr_fallback` returns `None` when the linked-branch
  query fails, instead of continuing with the timeline fallback.
- Deprecation: `_get_cache_file_path`, `_load_cache_file`, `_save_cache_file`,
  `_log_stale_cache_entries` exports from `issues/__init__` will be removed after
  MarcusJellinghaus/mcp_coder#1300 ships; use `get_issue_cache_last_checked`.
- Assumptions still to verify against live GitHub (copy the list from issue #361).

## HOW / ALGORITHM / DATA

N/A — documentation only. Match the heading style and tone of existing entries.
