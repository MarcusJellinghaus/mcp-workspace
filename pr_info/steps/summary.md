# Summary — #352 git_operations: missing operations, remote queries, rebase primitives

mcp-coder (MarcusJellinghaus/mcp_coder#1299) wants `mcp_workspace.git_operations` to be the
only place that runs git. This PR adds the missing operations (Part A) and the primitives for
driving a rebase that has stopped mid-flight (Part B). Everything is additive; cleanup of
leftovers is #355. One minor release at the end.

The issue text (#352) is the source of truth for contracts. This file fixes the design
choices that the issue leaves open, so that every step makes them the same way.

## Architectural / design changes

### 1. Result type family (`core.py`)

```python
class GitResult(TypedDict):
    success: bool              # True only when the goal was reached
    error: Optional[str]       # None for a normal-but-not-done outcome (conflict stop/probe)
    returncode: Optional[int]  # None when no git process ran
    stderr: Optional[str]      # None when no git process ran

class CommitResult(GitResult):   # existing type, now a subtype (gains returncode, stderr)
    commit_hash: Optional[str]
    error_category: Optional[Literal["signing_failed", "commit_failed",
                                     "validation_failed", "nothing_to_commit"]]
```

All other new result types are `GitResult` subtypes, also defined in `core.py` (next to the
existing `CommitResult` / `PushResult`), each added in the step that first uses it:
`StatusResult`, `RebaseProbe`, `BranchProbe`, `RemoteBranchesResult`, `RebaseResult`,
`ConflictBlobEntry` (plain TypedDict), `ConflictBlobInfoResult`, `ConflictStageResult`,
`TreeEntry` (plain TypedDict), `TreeListing`. No dataclasses, no `__bool__`.

Rules:
- `success` means "goal reached". A rebase stopped on a conflict, or a probe that found a
  conflict, is `success=False, error=None`; callers read `status` to tell it apart from a
  real error. `if result["success"]:` is always safe.
- `GitResult` functions never raise for routine failures, including "not a git repository"
  (→ error result).
- Plain-value local-state queries (`is_rebase_in_progress`, `has_staged_changes`,
  `list_unmerged_paths`) raise: `ValueError` for a non-repo, `GitCommandError` for any other
  git failure. Nothing fails open.
- Log once: new functions log at debug level only; the caller receives the failure.

### 2. One git runner for all new code (`core.py`)

```python
GIT_NONINTERACTIVE_ENV: dict[str, str] = {"GIT_TERMINAL_PROMPT": "0", "GIT_EDITOR": "true"}

def run_git_raw(repo: Repo, command: str, *args: str,
                env: Optional[dict[str, str]] = None,
                literal_paths: bool = False,
                strip_newline: bool = True) -> tuple[int, bytes, str]:
```

- Wraps `getattr(repo.git, command)(*args, with_extended_output=True,
  with_exceptions=False, stdout_as_string=False, strip_newline_in_stdout=strip_newline,
  env=...)`. Returns `(returncode, stdout_bytes, stderr_text)`; stderr is decoded UTF-8
  (`errors="replace"`) if GitPython hands back bytes.
- `literal_paths=True` adds `GIT_LITERAL_PATHSPECS=1` to the per-call env.
- New functions branch on the exit code; they never catch `GitCommandError` from git calls
  and never read `GitCommandError.stdout/stderr`.
- `strip_newline=False` is mandatory where blob content is returned (`cat-file blob`).
- `GIT_NONINTERACTIVE_ENV` replaces `_LS_REMOTE_ENV` in `base_branch.py`. Used by `pull`,
  the `ls-remote` queries, `rebase_start`, `rebase_continue`, `rebase_skip`, `rebase_abort`.
  `fetch_remote` stays unchanged.

Small shared helpers in `core.py` (step 1):
- `is_option_like(value: str) -> bool` — True if a caller-supplied ref/sha starts with `-`.
- `to_git_paths(paths: Sequence[Path], project_dir: Path) -> list[str]` — absolute or
  `project_dir`-relative paths → repo-relative, forward-slash strings; `ValueError` for a
  path outside `project_dir` (built on the existing `_normalize_git_path`, both sides
  `.resolve()`d).
- `open_repo_for_query(project_dir)` — context manager around `safe_repo_context` that turns
  `InvalidGitRepositoryError` / `NoSuchPathError` into `ValueError` (plain-value queries only).

### 3. Pure `-z` parsers (`porcelain_parsers.py`, new)

No git, no repos, unit-tested on byte strings. Each parser is added with its first consumer:
`parse_status_z` (step 5), `parse_merge_tree_z` (step 6), `parse_ls_remote_heads` (step 7),
`parse_ls_files_u_z` (step 14), `parse_ls_tree_z` (step 18). Output is decoded as UTF-8;
`-z` is used wherever paths are parsed, so non-ASCII paths round-trip.

### 4. Git layer rules (all new code)

- Only the git CLI via `repo.git.*` (through `run_git_raw`). No `repo.index`, no object
  APIs, no `repo.head.commit` (use `rev-parse HEAD`). Only non-CLI use: `repo.git_dir`.
- Functions taking paths use `literal_paths=True` and put `--` before the paths.
  `unstage_paths` chunks long lists with the existing `staging._chunk_paths`;
  `commit_paths` does not chunk.
- Caller-supplied refs/shas starting with `-` are rejected (error result, or `ValueError`
  for plain-value functions).

### 5. Part B: free functions, two new modules

- `rebase.py`: `probe_rebase_conflicts` (Part A, step 6), `_git_version`,
  `is_rebase_in_progress`, `rebase_start` / `rebase_continue` / `rebase_skip` (all three are
  one-liners over one private `_run_rebase`), `rebase_abort`, `reset_hard`.
- `conflicts.py`: `list_unmerged_paths`, `get_conflict_blob_info`, `read_conflict_stage`,
  `resolve_take_theirs_or_remove`, `list_tree`.
- `has_staged_changes` goes to `repository_status.py` (it is not rebase-specific).
- `rebase_continue` does **not** stage. Callers stage with the existing `stage_all_changes`
  (covers `add -A`) or `resolve_take_theirs_or_remove`; commits use `commit_all_changes` /
  `commit_staged_files` (cover `commit -m`). Step 12 has a test proving the sequence.

### 6. Base branch detection

`detect_base_branch_with_source(...) -> Optional[tuple[str, BaseBranchSource]]` becomes the
implementation; `detect_base_branch` becomes a thin wrapper returning only the name. Both gain
an optional trailing `issue_manager` (duck-typed; `TYPE_CHECKING` import only, matching the
existing `IssueData` / `PullRequestManager` imports — tach allows `git_operations` to depend
only on `log_utils` and `utils`). `origin_has_branch` becomes a wrapper over
`probe_origin_branch` that raises `GitCommandError` when origin couldn't answer.

### 7. Decisions fixed by this plan (where the issue is silent)

- `commit_paths` → `nothing_to_commit` is `success=False`, `error="Nothing to commit for the
  given paths"`, `error_category="nothing_to_commit"`. Decided only by the
  `status --porcelain -z -- <paths>` precheck (empty output), so a path that is neither
  tracked nor on disk is also `nothing_to_commit` (documented in the docstring).
- `list_remote_branches` failure: `success=False`, `branches=[]`.
- `resolve_take_theirs_or_remove` on a path with no unmerged entries → error result.
- `read_conflict_stage(project_dir, stage, path)`: `path` is a repo-relative `str` as returned
  by `list_unmerged_paths`; content decoded with `errors="replace"`.
- `BaseBranchSource` is an `Enum` with values `"issue"`, `"pr"`, `"merge_base"`, `"default"`.
- Release notes go to a new `docs/release-notes.md` (one section for this minor release),
  because `pr_info/` is deleted before merge. That file is also the source for the PR
  description and the GitHub release text.

## Files created / modified

### Created
| File | Purpose |
|------|---------|
| `src/mcp_workspace/git_operations/porcelain_parsers.py` | Pure `-z` / ls-remote parsers |
| `src/mcp_workspace/git_operations/rebase.py` | `probe_rebase_conflicts`, rebase flow, `reset_hard` |
| `src/mcp_workspace/git_operations/conflicts.py` | Conflict inspection/resolution, `list_tree` |
| `tests/git_operations/test_core_runner.py` | Runner + shared helpers |
| `tests/git_operations/test_porcelain_parsers.py` | Parser unit tests (no repos) |
| `tests/git_operations/test_pull.py` | `pull` |
| `tests/git_operations/test_commit_paths.py` | `commit_paths` |
| `tests/git_operations/test_unstage_paths.py` | `unstage_paths` |
| `tests/git_operations/test_working_tree_status.py` | `get_working_tree_status` |
| `tests/git_operations/test_rebase_probe.py` | `probe_rebase_conflicts` |
| `tests/git_operations/test_remote_queries.py` | `probe_origin_branch`, wrapper, `list_remote_branches` |
| `tests/git_operations/test_base_branch_source.py` | `detect_base_branch_with_source` |
| `tests/git_operations/test_rebase.py` | Rebase flow, `reset_hard` |
| `tests/git_operations/test_conflicts.py` | Conflict functions |
| `tests/git_operations/test_list_tree.py` | `list_tree` |
| `docs/release-notes.md` | Release notes (step 19); survives the `pr_info/` deletion |

### Modified
| File | Change |
|------|--------|
| `src/mcp_workspace/git_operations/core.py` | Result types, env constant, runner, helpers |
| `src/mcp_workspace/git_operations/commits.py` | New `CommitResult` keys; `commit_paths`; shared commit-failure classifier |
| `src/mcp_workspace/git_operations/workflows.py` | New `CommitResult` keys in `commit_all_changes` |
| `src/mcp_workspace/git_operations/staging.py` | `unstage_paths` |
| `src/mcp_workspace/git_operations/repository_status.py` | `get_working_tree_status`, `has_staged_changes`, A4 docstrings |
| `src/mcp_workspace/git_operations/remotes.py` | `pull`, `probe_origin_branch`, `list_remote_branches`, `clone_repo` relaxation |
| `src/mcp_workspace/git_operations/base_branch.py` | env import, `origin_has_branch` wrapper, `BaseBranchSource`, `detect_base_branch_with_source` |
| `src/mcp_workspace/git_operations/branch_queries.py` | A4 docstrings |
| `src/mcp_workspace/git_operations/__init__.py` | Exports (every step that adds public API) |
| `tests/git_operations/conftest.py` | `commit_files` helper, `make_conflict_repo` builder |
| `tests/git_operations/test_init_exports.py` | Expected export count |
| `tests/git_operations/test_remotes.py` | `clone_repo` tests (~line 531) |
| `vulture_whitelist.py` | New TypedDict keys |

## Steps

| # | Step | Public API added |
|---|------|------------------|
| 1 | Foundations: `GitResult`, `CommitResult` extension, env, runner, helpers | `GitResult` |
| 2 | `pull` | `pull` |
| 3 | `commit_paths` | `commit_paths` |
| 4 | `unstage_paths` | `unstage_paths` |
| 5 | `get_working_tree_status` | `get_working_tree_status`, `StatusResult` |
| 6 | `probe_rebase_conflicts` (+ conflict-repo test builder) | `probe_rebase_conflicts`, `RebaseProbe` |
| 7 | `probe_origin_branch` + `origin_has_branch` wrapper | `probe_origin_branch`, `BranchProbe` |
| 8 | `list_remote_branches` | `list_remote_branches`, `RemoteBranchesResult` |
| 9 | `detect_base_branch_with_source` | `detect_base_branch_with_source`, `BaseBranchSource` |
| 10 | `clone_repo` relaxation + credential scrubbing | — |
| 11 | A4 docstrings | — |
| 12 | Rebase flow | `is_rebase_in_progress`, `rebase_start`, `rebase_continue`, `rebase_skip`, `rebase_abort`, `RebaseResult` |
| 13 | `reset_hard` | `reset_hard` |
| 14 | `list_unmerged_paths` | `list_unmerged_paths` |
| 15 | `get_conflict_blob_info`, `read_conflict_stage` | both + `ConflictBlobEntry`, `ConflictBlobInfoResult`, `ConflictStageResult` |
| 16 | `resolve_take_theirs_or_remove` | `resolve_take_theirs_or_remove` |
| 17 | `has_staged_changes` | `has_staged_changes` |
| 18 | `list_tree` | `list_tree`, `TreeEntry`, `TreeListing` |
| 19 | Release notes | — |

## Every step

- Tests first, then implementation; exactly one commit per step.
- Export new public names from `git_operations/__init__.py` (keep `__all__` sorted) and raise
  the expected count in `tests/git_operations/test_init_exports.py` by the number added.
- Add new TypedDict keys to `vulture_whitelist.py` (section "git_operations result TypedDict
  fields - accessed via subscript").
- Run `mcp__mcp-tools-py__run_pylint_check`, `mcp__mcp-tools-py__run_pytest_check`
  (`extra_args: ["-n", "auto"]`), `mcp__mcp-tools-py__run_mypy_check`, and
  `mcp__mcp-tools-py__run_vulture_check`; all must pass. Run
  `mcp__mcp-tools-py__run_format_code` before committing.
- Keep every file under 750 lines (`.large-files-allowlist`); split test files rather than
  growing them.
- Windows: test non-ASCII paths/messages/content where the step parses output; paths with
  `[`, `*` and `:(` must be treated literally where the step takes paths.
