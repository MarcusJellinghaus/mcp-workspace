# Summary — #355: remove duplication left over from #352

Every concern in `git_operations` gets one implementation. Each old entry point that #352
kept beside a new primitive is either deleted (no consumer, no internal caller) or rebuilt
on that primitive.

| Concern | Single implementation | Old entry point | Fate |
|---|---|---|---|
| Working-tree status | `get_working_tree_status` (`-z` parser) | `get_staged_changes`, `get_unstaged_changes` | deleted |
| | | `get_full_status` | rebuilt, same contract |
| Origin branch probe | `probe_origin_branch` | `origin_has_branch` | deleted |
| Rebase | `rebase_start` / `rebase_abort` | `rebase_onto_branch` | rebuilt, same contract |

The issue (#355) is the source of truth for requirements; this plan does not repeat its
consumer check or rationale.

## Architectural / design changes

- **One status parser.** The non-`-z` `git status --porcelain` and `git diff --cached
  --name-only` parsing in `repository_status.py` disappears. Every internal status read goes
  through `get_working_tree_status` (or `has_staged_changes` for the staged-only question).
  `get_full_status` becomes a thin fail-open adapter over it: same signature, same
  `{staged, modified, untracked}` dict, still never raises.
- **Fail-open callers now fail closed.**
  - `commit_all_changes`: a status failure is `success=False, error_category="commit_failed"`
    instead of "nothing to commit".
  - `commit_staged_files`: a `GitCommandError` from the staged-changes precheck is
    `commit_failed` (with `returncode` / `stderr`).
  - `stage_all_changes`: no precheck at all. `git add --all` is already a no-op on a clean
    tree, so a status error can no longer report success without staging.
- **One origin probe.** `server.github_pr_create` and `base_branch._detect_from_merge_base`
  read the `BranchProbe` dict (`exists` True / False / None) instead of a bool-or-raise
  wrapper. Each wraps only the probe call. `_detect_from_merge_base` catches
  `(GitCommandNotFound, OSError)`. `server.py` keeps its existing `except Exception`, scoped
  to the call, because it may not import `git.exc` (`gitpython_isolation` contract).
- **One rebase implementation.** `rebase_onto_branch` becomes
  `fetch_remote` → `rebase_start` → (`rebase_abort` on a stop). The duplicate inline
  rebase-dir check is gone. Side effect, a bug fix: a rebase already in progress is now
  refused (`rebase_start` returns `error`) instead of being aborted.
- **Import direction:** `remotes.py` newly imports from `rebase.py`. `rebase.py` imports
  only `core` and `porcelain_parsers`, so there is no cycle. All edges stay inside
  `git_operations`, so the layer contracts are unaffected.
- **Public API:** nothing exported from `git_operations.__init__` changes. The deleted
  symbols were never exported.

## Files modified

```
src/mcp_workspace/server.py                              # step 1
src/mcp_workspace/git_operations/base_branch.py          # step 2
src/mcp_workspace/git_operations/repository_status.py    # steps 3, 8
src/mcp_workspace/git_operations/remotes.py              # steps 4, 9
src/mcp_workspace/git_operations/commits.py              # step 5
src/mcp_workspace/git_operations/staging.py              # step 6
src/mcp_workspace/git_operations/workflows.py            # step 7
docs/release-notes.md                                    # steps 2, 3, 6, 7, 9

tests/github_operations/test_github_pr_create_base.py    # step 1
tests/github_operations/test_github_write_tools_labels_pr.py  # step 1
tests/git_operations/test_base_branch_git.py             # step 2
tests/git_operations/test_remote_queries.py              # step 2
tests/git_operations/test_repository_status.py           # steps 3, 8
tests/git_operations/test_remotes.py                     # steps 4, 9
tests/git_operations/test_commits.py                     # steps 5, 7
tests/git_operations/test_staging.py                     # step 6
```

No files or folders are created or deleted (apart from these plan files).

## Steps (one commit each)

1. `github_pr_create` → `probe_origin_branch`
2. `_detect_from_merge_base` → `probe_origin_branch`; delete `origin_has_branch`
3. Rebuild `get_full_status` on `get_working_tree_status` (+ parity test)
4. `_format_dirty_tree` → `get_working_tree_status`
5. `commit_staged_files` precheck → `has_staged_changes`
6. `stage_all_changes`: drop the precheck
7. `commit_all_changes` precheck → `get_working_tree_status`, fail closed
8. Delete `get_staged_changes` / `get_unstaged_changes`
9. Rebuild `rebase_onto_branch` on `rebase_start` / `rebase_abort`

## Checks per step

Before each commit: `run_format_code`, then `run_pylint_check`,
`run_pytest_check(extra_args=["-n", "auto"])` and `run_mypy_check`. Run
`run_lint_imports_check` too in steps that change imports (1, 2, 4, 8, 9), and
`run_vulture_check` in steps that delete code (2, 8). All must pass.

Not in scope: `repo.head.commit` / `# TODO: narrow` blocks in `commits.py`,
`detect_base_branch`, mcp-coder's own callers.
