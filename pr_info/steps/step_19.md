# Step 19 — Release notes

## LLM prompt
Read `pr_info/steps/summary.md` and this file. Implement step 19 only: write
`pr_info/release_notes.md` from the actual exports in
`src/mcp_workspace/git_operations/__init__.py` (verify each name exists there). If any
function or type listed in the summary's step table is missing from `__all__`, write one
line to `pr_info/.blocked.txt` and stop. Run the checks from the summary, commit as one
commit.

## WHERE
- `pr_info/release_notes.md` (new) — source for the PR description and GitHub release text.

## WHAT (sections)
1. **Summary** — one paragraph: new `git_operations` primitives so mcp-coder can stop
   running git directly (MarcusJellinghaus/mcp_coder#1299). Minor release.
2. **New functions** — one line each with signature and return type:
   `pull`, `commit_paths`, `unstage_paths`, `get_working_tree_status`,
   `probe_rebase_conflicts`, `probe_origin_branch`, `list_remote_branches`,
   `detect_base_branch_with_source`, `is_rebase_in_progress`, `rebase_start`,
   `rebase_continue`, `rebase_skip`, `rebase_abort`, `reset_hard`, `list_unmerged_paths`,
   `get_conflict_blob_info`, `read_conflict_stage`, `resolve_take_theirs_or_remove`,
   `has_staged_changes`, `list_tree`.
3. **New types** — `GitResult`, `StatusResult`, `RebaseProbe`, `BranchProbe`,
   `RemoteBranchesResult`, `BaseBranchSource`, `RebaseResult`, `ConflictBlobEntry`,
   `ConflictBlobInfoResult`, `ConflictStageResult`, `TreeEntry`, `TreeListing`.
4. **Result contract** — `success` means goal reached; conflict outcomes are
   `success=False, error=None` with a `status`; plain-value queries raise `ValueError`
   (non-repo) / `GitCommandError`.
5. **Compatibility** —
   - `CommitResult` is now a `GitResult` subtype with required `returncode` and `stderr`;
     code constructing a `CommitResult` literal must add them (mcp-coder
     `tests/test_module_integration.py:90`). New `error_category` value `"nothing_to_commit"`.
   - `clone_repo` accepts an existing empty directory (previously `ValueError`); clone
     errors no longer chain the original exception and have credentials scrubbed.
   - `detect_base_branch` gains optional trailing `issue_manager`; return type unchanged.
   - `origin_has_branch` raises `GitCommandError` when origin can't answer (previously any
     GitPython error, e.g. `InvalidGitRepositoryError` for a non-repo).
   - `rebase_onto_branch` unchanged (keeps its inline rebase-dir check until #355).
6. **Migration traps (A3)** — `get_remote_branch_commit_sha` for `rev-parse --verify
   origin/<base>` (full sha); `git_diff(project_dir, ["HEAD", "--stat"])` truncates at 100
   lines and returns `"No changes found"` when empty; `get_remote_url` returns `None` for
   both "no origin" and "not a repo".

## HOW / ALGORITHM / DATA
Markdown only; no code changes.
