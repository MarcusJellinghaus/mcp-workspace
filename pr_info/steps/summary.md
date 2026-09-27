# Summary — Issue #295: name the dirty files when a rebase fails

## Goal

When `rebase_onto_branch` fails for a reason that is neither "already up to date" nor a
merge conflict, it logs git's raw stderr and nothing else. If the cause was a dirty working
tree, git says *what* was wrong (`error: cannot rebase: You have unstaged changes.`) but
never *which files*, so diagnosing a Jenkins log means tracing caller code to find what was
left uncommitted.

Append the working-tree file list to that one warning. Log-message-only change: no
signature, return-value, or control-flow change.

## Architectural / design changes

None to the architecture. This adds one private helper and one module-level constant inside
an existing module, and edits one existing log call.

- **No new module edge.** `remotes.py:13` already imports `is_git_repository` from
  `.repository_status`; this extends that same import with `get_full_status`. Both modules
  sit in the `git_operations` layer, which `docs/ARCHITECTURE.md` places at "Tools (lower)"
  and permits to depend on Utilities only. No `tach` / `lint-imports` impact.
- **No new public surface.** `_format_dirty_tree` is private to `remotes.py` and is not
  exported from `git_operations/__init__.py`.
- **No new dependency.** `get_full_status` is reused as-is; it already returns
  root-relative paths in three buckets and never raises.

### Design decisions carried from the issue

| Topic | Decision | Why |
|-------|----------|-----|
| Placement | In the `except GitCommandError` fall-through, not as a pre-rebase check | An eager `is_dirty` check warns on runs that then rebase cleanly — any run with a `.scratch/` dir or stale build artifact. A warning that fires on healthy runs trains the reader to skip it |
| Which branches are touched | Only the fall-through | The conflict branch (`remotes.py:338-348`) would list conflicted files mid-rebase, which is actively misleading; the outer handler (`remotes.py:354`) sees fetch/repo-open errors, not tree state |
| Gating | None — call `get_full_status` unconditionally, suppress output when clean | Keeps `test_rebase_onto_branch_invalid_target_branch` logging exactly what it does today, with no error-text heuristic to maintain |
| Buckets | All three: staged, modified, untracked | "untracked working tree files would be overwritten by checkout" is a real rebase failure that only the untracked list explains |
| Cap | 20 per bucket, one shared constant | A single total cap applied in order lets a large `staged` bucket crowd out `modified` — and `modified` is what explains the "unstaged changes" refusal |
| Truncation wording | Bare `... showing N of M {label}`, no escape hatch | The house `_MAX_*` idiom points at a parameter the caller can raise; a log line has none |

### Rendering shape

One line per non-empty bucket, paths comma-joined, truncation clause appended inline:

```
Skipping rebase: Cmd('git') failed due to: exit code(1)
  cmdline: git rebase origin/main
  stderr: 'error: cannot rebase: You have unstaged changes.
error: Please commit or stash them.'
Working tree:
  modified: pr_info/review_log_2.md
```

Chosen over a heading-plus-indented-list-plus-truncation-line layout: same information, one
rendering concept instead of three, and three log lines instead of sixty on a large dirty
tree.

## Accepted costs

- **Nested `safe_repo_context` is confirmed safe**, verified by scratch probe on Windows
  with real git (recorded in the issue): `get_full_status` called inside the outer context
  returned the correct buckets, and the outer repo was still usable afterwards. No
  porcelain-parsing fallback is needed.
- **The nesting is not free, and that is accepted.** One `get_full_status` call opens
  roughly five `Repo` objects, and each close runs `gc.collect()` on Windows. This is the
  failure path only. Recorded so it isn't re-litigated in review.
- **`get_full_status` can emit its own WARNING** (`"Unexpected error getting full git
  status: %s"`), so on a pathological repo this change can produce two warning lines rather
  than one. Harmless; the implementation must not assume its line is the only new output.

## Out of scope

- **Sibling failure paths in `remotes.py`.** `git_push` and friends log bare git stderr the
  same way, but they are similar-looking rather than confirmed gaps — a push failure's
  stderr already names the ref and the reason.
- **Improving the `mcp_coder` logs.** `mcp_coder` #1158 item 2 adds an
  `is_working_directory_clean` pre-check to `_attempt_rebase_and_push` that returns `False`
  *without* calling `rebase_onto_branch`, so the dirty case never reaches this code from the
  `review` / `implement` paths. This issue is hardening for arbitrary callers of the
  library. Recorded so a future reader does not assume #1158's Jenkins-log gap was closed
  here.

## Files created or modified

| Path | Change |
|------|--------|
| `src/mcp_workspace/git_operations/remotes.py` | Modified — extend the `.repository_status` import, add `_MAX_DIRTY_PATHS_PER_BUCKET`, add `_format_dirty_tree`, edit one `logger.warning` call |
| `tests/git_operations/test_remotes.py` | Modified — one new integration case in `TestRebaseOntoBranch`, plus unit tests for `_format_dirty_tree` (per-bucket truncation, all buckets, empty tree) |

No new folders or modules. No fixture changes: `git_repo_with_remote`
(`tests/git_operations/conftest.py`) already yields `(repo, project_dir, bare_remote_dir)`
with the default branch renamed to `main` and one committed tracked file, `README.md`.

## Steps

One step, one commit — see [step_1.md](./step_1.md). The change is a single helper plus its
call site plus two tests; there are no independent parts to split.
