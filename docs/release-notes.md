# Release notes

## Next minor release — github_operations: fingerprint-based PR and branch-lookup caches (#361)

### Summary

Adds the `mcp_workspace.github_operations.caching` subpackage: disk caches for open PRs,
per-PR results and issue → branch lookups, valid while a fingerprint is unchanged, so
mcp_coder's per-minute `vscodeclaude` runs stop re-querying GitHub
(MarcusJellinghaus/mcp_coder#1300). Rate limits now raise a dedicated exception instead of
being swallowed. See the README section "GitHub caches" for files, validity rules and what
stays live.

### New API

- `GitHubRateLimitError` — exported from `mcp_workspace.github_operations`; attributes `message: str`, `reset_at: datetime | None`. Raised by all caches on a rate limit; nothing is saved for that run.
- `caching.pull_requests.PullRequestCache` — `load(pr_manager)`, `find_pr(branch)`, `base_tip(base_branch)`, `mergeable_state(pr, issue)`, `ci_status(pr, issue)`, `feedback(pr, issue)`, `label_events(pr, issue)`, `save()`.
- `caching.branches.BranchLookupCache` — `load(manager)`, `lookup(issue) -> BranchLookup`, `save()`.
- `caching.branches.invalidate_branch_entry(repo_identifier, issue_number)` — called by `create_remote_branch_for_issue` on success.
- `IssueBranchManager.resolve_branch_for_issue(issue_number, repo_owner, repo_name) -> BranchLookup` — raises on every error (`ValueError`, `BranchLookupError`, `GitHubRateLimitError`, `GithubException`) instead of returning `None`. `BranchLookupError` is exported from `github_operations.issues`.
- `issues.BranchLookup` — `NamedTuple`: `status: "found" | "not_found" | "ambiguous"`, `branch: str | None`.
- `issues.get_issue_cache_last_checked(repo_identifier) -> datetime | None`.

### Behaviour changes

- `get_all_cached_issues` raises `GitHubRateLimitError` on a rate limit instead of
  returning stale data, and saves nothing. Other errors keep the stale-return path.
- `get_branch_with_pr_fallback` returns `None` when the linked-branch query fails, instead
  of continuing with the timeline fallback.

### Deprecations

- `_get_cache_file_path`, `_load_cache_file`, `_save_cache_file` and
  `_log_stale_cache_entries` exports from `github_operations.issues` will be removed after
  MarcusJellinghaus/mcp_coder#1300 ships. Use `get_issue_cache_last_checked`.

### Assumptions still to verify against live GitHub

- New comments and reviews bump the PR's `updated_at`.
- Resolving a review thread may **not** bump the PR's `updated_at`; the issue `updated_at`
  in the fingerprint and the maximum age cover this.
- A CI run finishing and the base branch moving do **not** bump the PR's `updated_at`
  (hence the CI and base-tip fingerprints).
- Linking a branch to an issue, or a PR cross-referencing it, bumps the issue's `updated_at`.

## Next minor release — git_operations: missing operations, remote queries, rebase primitives (#352)

### Summary

Adds the `mcp_workspace.git_operations` primitives mcp-coder needs so it can stop running
git directly (MarcusJellinghaus/mcp_coder#1299): commit/stage/pull operations, remote
queries without fetch, a rebase-conflict probe, and the building blocks for driving a
rebase that has stopped mid-flight. All additions are exported from
`mcp_workspace.git_operations`. Minor release; the compatibility notes below list the
small behaviour changes to existing functions.

### New functions

All take `project_dir: Path` (the repository) unless noted.

- `pull(project_dir) -> GitResult` — `git pull --no-edit` from the upstream; honors `pull.rebase`.
- `commit_paths(message: str, paths: list[Path], project_dir) -> CommitResult` — commit only `paths` (`git commit --only`).
- `unstage_paths(paths: list[Path], project_dir) -> GitResult` — remove `paths` from the index, keep working-tree content.
- `get_working_tree_status(project_dir) -> StatusResult` — staged, modified and untracked files in one call.
- `probe_rebase_conflicts(project_dir, base_ref: str) -> RebaseProbe` — predict a rebase conflict via `git merge-tree --write-tree` (git 2.38+).
- `probe_origin_branch(project_dir, branch: str) -> BranchProbe` — does `refs/heads/<branch>` exist on origin (ls-remote, no fetch).
- `list_remote_branches(project_dir) -> RemoteBranchesResult` — every head on origin (ls-remote, no fetch).
- `detect_base_branch_with_source(project_dir, current_branch=None, issue_data=None, pr_manager=None, issue_manager=None) -> Optional[tuple[str, BaseBranchSource]]` — base branch plus how it was found.
- `is_rebase_in_progress(project_dir) -> bool`
- `rebase_start(project_dir, onto_ref: str) -> RebaseResult` — no fetch, no auto-abort.
- `rebase_continue(project_dir) -> RebaseResult` — does not stage first.
- `rebase_skip(project_dir) -> RebaseResult`
- `rebase_abort(project_dir) -> GitResult` — success no-op when no rebase is running.
- `reset_hard(project_dir, sha: str) -> GitResult`
- `list_unmerged_paths(project_dir) -> list[str]` — repo-relative, forward slashes.
- `get_conflict_blob_info(project_dir) -> ConflictBlobInfoResult` — stages present and binary flag per unmerged path.
- `read_conflict_stage(project_dir, stage: int, path: str) -> ConflictStageResult` — content of stage 1/2/3.
- `resolve_take_theirs_or_remove(project_dir, path: str) -> GitResult` — take stage 3 (the replayed feature commit) and stage it, or remove the path if stage 3 is absent.
- `has_staged_changes(project_dir) -> bool` — index differs from HEAD (empty tree on an unborn HEAD).
- `list_tree(project_dir, ref: str, path: str) -> TreeListing` — direct contents of a directory at any ref.

Paths are matched literally (`*`, `[`, `:(` have no special meaning). Refs/shas starting
with `-` are rejected.

### New types

`TypedDict`s unless noted; every `*Result`/`*Probe`/`TreeListing` extends `GitResult`.

- `GitResult` — `success: bool`, `error: Optional[str]`, `returncode: Optional[int]`, `stderr: Optional[str]` (`returncode`/`stderr` are `None` when no git process ran).
- `StatusResult` — `clean`, `staged`, `modified`, `untracked`.
- `RebaseProbe` — `status: "conflict" | "clean" | "unsupported" | "error"`, `files`.
- `BranchProbe` — `exists: Optional[bool]` (`None` when origin couldn't answer).
- `RemoteBranchesResult` — `branches` (empty on failure).
- `BaseBranchSource` — `Enum`: `ISSUE="issue"`, `PR="pr"`, `MERGE_BASE="merge_base"`, `DEFAULT="default"`.
- `RebaseResult` — `status: "completed" | "stopped_on_conflict" | "error"`.
- `ConflictBlobEntry` — plain: `path`, `stages: list[int]`, `is_binary`.
- `ConflictBlobInfoResult` — `entries: list[ConflictBlobEntry]`.
- `ConflictStageResult` — `content: Optional[str]` (`None` for a binary blob or an absent side), `is_binary`.
- `TreeEntry` — plain: `mode`, `type`, `sha`, `path`.
- `TreeListing` — `entries: list[TreeEntry]`.

### Result contract

- `success` means the goal was reached, so `if result["success"]:` is always safe.
- Conflict outcomes (a rebase stopped on a conflict, a probe that found one) are
  `success=False, error=None`; read `status` to tell them apart from real errors.
- `GitResult` functions don't raise for routine failures, including "not a git
  repository" — they return an error result.
- Plain-value queries (`is_rebase_in_progress`, `has_staged_changes`,
  `list_unmerged_paths`) raise `ValueError` for a non-repo and `GitCommandError` for any
  other git failure. Nothing fails open.

### Compatibility

- `CommitResult` is now a `GitResult` subtype with required `returncode` and `stderr`.
  Code that builds a `CommitResult` literal must add both keys (mcp-coder:
  `tests/test_module_integration.py:90`). New `error_category` value
  `"nothing_to_commit"`.
- `clone_repo` accepts an existing empty directory (previously `ValueError`). Clone errors
  no longer chain the original exception, and credentials are scrubbed from URLs in the
  message.
- `detect_base_branch` gains an optional trailing `issue_manager`; return type unchanged.
- `get_full_status` reads the `-z` status: paths are raw UTF-8 (no C-quoting), a
  staged-renamed-then-modified file is reported by its new path (not `old -> new`), and a
  status failure gives all-empty lists (never partial).
- `rebase_onto_branch` no longer aborts a rebase that was already in progress; it returns
  `False` and leaves it alone.
- `stage_all_changes` no longer reports success when it cannot read the status; it runs
  `git add --all` directly, so any git failure is `False`.
- `commit_all_changes` returns `success=False` (`error_category="commit_failed"`) when
  `git status` fails, instead of reporting "nothing to commit".

### Migration traps

- `rev-parse --verify origin/<base>` → `get_remote_branch_commit_sha(project_dir, branch_name)`
  (`git_operations.branch_queries`); returns the full sha.
- `git diff HEAD --stat` → `git_diff(project_dir, ["HEAD", "--stat"])`
  (`git_operations.read_operations`) truncates at 100 lines and returns
  `"No changes found"` when the diff is empty.
- `get_remote_url` returns `None` both for "no origin" and "not a git repository".
