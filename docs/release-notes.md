# Release notes

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
- `origin_has_branch` raises `GitCommandError` when origin can't answer (previously any
  GitPython error, e.g. `InvalidGitRepositoryError` for a non-repo).
- `rebase_onto_branch` is unchanged (keeps its inline rebase-dir check until #355).

### Migration traps

- `rev-parse --verify origin/<base>` → `get_remote_branch_commit_sha(project_dir, branch_name)`
  (`git_operations.branch_queries`); returns the full sha.
- `git diff HEAD --stat` → `git_diff(project_dir, ["HEAD", "--stat"])`
  (`git_operations.read_operations`) truncates at 100 lines and returns
  `"No changes found"` when the diff is empty.
- `get_remote_url` returns `None` both for "no origin" and "not a git repository".
