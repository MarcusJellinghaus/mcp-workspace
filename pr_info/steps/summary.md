# Summary — #220 Expose guarded git-write MCP tools

## Goal

Add five workspace-only MCP tools that cover the routine branch → commit → push loop and the
post-rebase force push, each protected by in-tool guardrails:

| Tool | Behaviour (short) |
|---|---|
| `git_branch(name, create=False, base=None)` | switch to a local branch / create a tracking branch from local `origin/<name>`; `create=True` = `checkout -b` from HEAD or `base` |
| `git_branch_delete(name)` | `git branch -D`, only if the tip is provably on GitHub |
| `git_commit(message, paths=None, all=False)` | commit exactly `paths` (`commit --only`) or everything (`add -A`) |
| `git_push()` | `push -u origin refs/heads/<b>:refs/heads/<b>` for the current branch |
| `git_push_force()` | same, with `--force-with-lease --force-if-includes` |

All return `str`: first line machine-readable, `Error: <reason>` on failure, never raise.
Full behaviour, guardrails and output formats are specified in issue #220; the step files
repeat what each step needs.

## Architectural / design changes

1. **First mutating git tools.** Until now the only git tool was the read-only `git`
   (`read_only=True`). The new tools live in a new toolset module `toolset/git_write.py`, group
   `workspace.git`, `read_only=False`, registered in `toolset/__init__.py` `_GROUPS` right after
   `git.register`. Gating is client-side (allowlist), no server flag.
2. **Thin tool closures, sync orchestration in a helper module.** `git_write.py` holds only the
   tool signatures/descriptions, the lock and `asyncio.to_thread`. All guardrail logic and
   result formatting lives in `toolset/_git_write_helpers.py` as plain sync functions
   (`do_git_branch(ctx, ...) -> str`, ...). `git_write.py` imports the helper module **lazily
   inside each closure**, so GitPython stays off the startup path
   (`tests/toolset/test_toolset_imports.py`) and the tool named `git_push` never shadows the
   library's `git_operations.git_push`. The helper module may import `git_operations` at top level.
3. **Serialised git writes.** `WorkspaceContext` gains
   `git_write_lock: asyncio.Lock = field(default_factory=asyncio.Lock)`; every write tool holds
   it, so a `git_commit` + `git_push` issued in the same turn run in order. One lock per
   `tool_specs()` call, like `file_locks`.
4. **Timeout-bounded network git.** New `git_operations/_subprocess_git.py`: the single place
   that runs network git (`push`, `ls-remote`) through `subprocess.run(..., timeout=120)` with
   `GIT_NONINTERACTIVE_ENV` merged into `os.environ`, and `scrub_credentials` on all output.
   GitPython's `kill_after_timeout` is not used (raises on Windows). `.importlinter`
   `subprocess_ban` gets one `ignore_imports` line for it.
5. **New library functions return results, existing ones unchanged.** Mutations and network
   calls return `GitResult` (or a `GitResult` subtype) so the failure reason reaches the user.
   Local predicates return plain values (`bool`, `bool | None`, `str | None`) — they have no
   reason to lose. Existing bare-bool functions (`create_branch`, `checkout_branch`,
   `delete_branch`, `push_branch`, `git_push`) and their callers are untouched.
6. **New functions are placed in the existing thematic modules** (no new library modules besides
   `_subprocess_git.py`) and are **not** added to `git_operations/__init__.__all__`; the toolset
   imports them from their modules. The public library API (`__all__`, 70 symbols) is unchanged.
7. **Force-push preconditions live in the library.** `push_current_branch(project_dir, force=True)`
   itself refuses on git < 2.30 (via `git_version`, made public from `rebase._git_version`) and
   when `refs/remotes/origin/<b>` has no reflog (fresh clone). The toolset only adds the
   branch-level guards (detached HEAD, default branch).
8. **New GitHub query.** `PullRequestManager.find_merged_pr_by_head_sha(sha) -> int | None`
   (`repo.get_commit(sha).get_pulls()`), used by the tip-on-GitHub check of `git_branch_delete`.
9. **`_format_dirty_tree` becomes public `format_dirty_tree`** (remotes.py) and is reused for the
   capped "remaining changes" block of `git_commit`.
10. **Policy change.** "Git mutation is Bash-only" no longer holds for these five tools.
    `reset`, `rebase`, `clean`, `checkout <path>`, `--amend`, plain `--force` stay Bash-only.

## KISS decisions taken during planning

- No staging tool; `git_commit` stages and commits in one call.
- `git_commit(paths)` stages only the untracked files under `paths`, listed by
  `git ls-files --others --exclude-standard -z -- <paths>`; on a failed commit exactly those
  files are unstaged (they had no prior index state, so nothing the user staged is touched).
- Tests: a new fixture in `tests/toolset/conftest.py` (bare origin + real `git clone`, plus a
  factory for further clones) instead of promoting `git_repo_with_remote`. Real clones give
  `origin/HEAD` (default-branch detection) and the real fresh-clone "no reflog" state.
- The git ≥ 2.30 version check is kept as the issue specifies (inside `push_current_branch`).

## Files

### Created

| Path | Purpose |
|---|---|
| `src/mcp_workspace/git_operations/_subprocess_git.py` | timeout-bounded `subprocess` git runner |
| `src/mcp_workspace/toolset/git_write.py` | the five tool closures + `register` |
| `src/mcp_workspace/toolset/_git_write_helpers.py` | guardrails, orchestration, result formatting |
| `tests/git_operations/test_subprocess_git.py` | step 1 |
| `tests/git_operations/test_push_current_branch.py` | step 2 |
| `tests/git_operations/test_remote_head_sha.py` | step 3 |
| `tests/git_operations/test_guard_queries.py` | step 4 |
| `tests/git_operations/test_branch_writes.py` | step 5 |
| `tests/git_operations/test_stage_paths.py` | step 6 |
| `tests/git_operations/test_commit_reporting.py` | step 7 |
| `tests/github_operations/test_pr_manager_merged_by_sha.py` | step 8 |
| `tests/toolset/conftest.py` | `origin_clone` / `make_clone` fixtures |
| `tests/toolset/test_git_branch.py` | step 9 |
| `tests/toolset/test_git_branch_delete.py` | step 10 |
| `tests/toolset/test_git_commit.py` | step 11 |
| `tests/toolset/test_git_push.py` | step 12 |
| `tests/toolset/test_git_push_force.py` | step 13 |
| `tests/toolset/tool_schemas/git_branch.json`, `git_branch_delete.json`, `git_commit.json`, `git_push.json`, `git_push_force.json` | schema snapshots |

### Modified

| Path | Change |
|---|---|
| `.importlinter` | `subprocess_ban`: ignore line for `_subprocess_git`, comment update |
| `src/mcp_workspace/git_operations/core.py` | `RemoteHeadResult` TypedDict |
| `src/mcp_workspace/git_operations/rebase.py` | `_git_version` → `git_version`; `operation_in_progress` |
| `src/mcp_workspace/git_operations/remotes.py` | `push_current_branch`, `remote_head_sha`, `_remote_tracking_reflog_exists`; `_format_dirty_tree` → `format_dirty_tree` |
| `src/mcp_workspace/git_operations/branch_queries.py` | `is_valid_branch_name_strict`, `resolve_base_ref`, `resolve_commit`, `is_ancestor` |
| `src/mcp_workspace/git_operations/branches.py` | `create_and_switch_branch`, `switch_branch`, `delete_local_branch_force` |
| `src/mcp_workspace/git_operations/staging.py` | `list_untracked_paths`, `stage_paths` |
| `src/mcp_workspace/git_operations/commits.py` | `committed_files` |
| `src/mcp_workspace/github_operations/pr_manager.py` | `find_merged_pr_by_head_sha` |
| `src/mcp_workspace/toolset/_context.py` | `git_write_lock` field |
| `src/mcp_workspace/toolset/__init__.py` | import `git_write`, add to `_GROUPS` |
| `tests/git_operations/test_remotes.py`, `tests/git_operations/test_rebase_probe.py` | follow the two renames (`format_dirty_tree`, `git_version`) |
| `tests/toolset/test_toolset.py` | `EXPECTED`, `ASYNC_TOOLS` |
| `README.md`, `docs/LIBRARY_USE.md`, `docs/ARCHITECTURE.md`, `SECURITY.md` | docs |
| `tests/LLM_Test.md` | new local-only mutating section |
| `.claude/settings.local.json`, `.claude/CLAUDE.md` | allowlist, tool table, Bash git list |

## Steps (one commit each)

1. Subprocess timeout helper (`_subprocess_git.py`, `.importlinter`)
2. `push_current_branch` (+ public `git_version`, reflog check)
3. `remote_head_sha`
4. Guardrail queries (`is_valid_branch_name_strict`, `resolve_base_ref`, `resolve_commit`, `is_ancestor`, `operation_in_progress`)
5. Branch mutations (`create_and_switch_branch`, `switch_branch`, `delete_local_branch_force`)
6. Staging (`list_untracked_paths`, `stage_paths`)
7. Commit reporting (`committed_files`, public `format_dirty_tree`)
8. `PullRequestManager.find_merged_pr_by_head_sha`
9. Tool `git_branch` (+ `git_write.py`, helpers module, lock, fixture, registration)
10. Tool `git_branch_delete`
11. Tool `git_commit`
12. Tool `git_push`
13. Tool `git_push_force`
14. Docs: README, LIBRARY_USE, ARCHITECTURE, SECURITY
15. LLM_Test section, `.claude/settings.local.json`, `.claude/CLAUDE.md`

The mcp_coder companion (MarcusJellinghaus/mcp_coder#1415) is out of scope; it merges after an
mcp-workspace release.

## Conventions for every step

- Use the MCP tools listed in `.claude/CLAUDE.md` (no native file tools).
- Before committing: `run_format_code`, then pylint, `run_pytest_check(extra_args=["-n", "auto"])`,
  mypy, `run_lint_imports_check`, `run_ruff_check`; all must pass.
- Every file stays under 750 lines (`check_file_size(max_lines=750)`).
- New git integration tests carry `@pytest.mark.git_integration`.
- Scratch probes go in `.scratch/` and are deleted before the commit.
- If a stated precondition does not hold, write one line to `pr_info/.blocked.txt` and stop.
