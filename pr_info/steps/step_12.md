# Step 12 — Rebase flow: `is_rebase_in_progress`, `rebase_start/continue/skip/abort`

## LLM prompt
Read `pr_info/steps/summary.md` (sections 1, 2, 5) and this file. Implement step 12 only,
tests first, in `rebase.py`. Leave `rebase_onto_branch` untouched (its inline check stays
until #355). Run the checks from the summary, format, commit as one commit.

## WHERE
- `src/mcp_workspace/git_operations/core.py` (add `RebaseResult`)
- `src/mcp_workspace/git_operations/rebase.py`
- `src/mcp_workspace/git_operations/__init__.py` (5 functions + `RebaseResult`; count +6)
- `tests/git_operations/conftest.py` (reuse `make_conflict_repo`; add helpers only if needed)
- `tests/git_operations/test_rebase.py` (new)

## WHAT
```python
class RebaseResult(GitResult):
    status: Literal["completed", "stopped_on_conflict", "error"]

def _rebase_dir_exists(repo: Repo) -> bool:     # repo.git_dir / "rebase-merge" | "rebase-apply"
def is_rebase_in_progress(project_dir: Path) -> bool: ...
def _run_rebase(project_dir: Path, *args: str) -> RebaseResult: ...
def rebase_start(project_dir: Path, onto_ref: str) -> RebaseResult: ...  # _run_rebase(onto_ref)
def rebase_continue(project_dir: Path) -> RebaseResult: ...  # _run_rebase("--continue")
def rebase_skip(project_dir: Path) -> RebaseResult: ...      # _run_rebase("--skip")
def rebase_abort(project_dir: Path) -> GitResult: ...
```

## HOW
- `is_rebase_in_progress` uses `open_repo_for_query` (non-repo → `ValueError`) and
  `repo.git_dir`, so it works in worktrees and submodules.
- All rebase git calls use `env=GIT_NONINTERACTIVE_ENV` (no editor ever opens).
- No fetch, no auto-abort. `onto_ref` starting with `-` → `status="error"`, no git call.
- `rebase_start` checks `_rebase_dir_exists` before calling git: a rebase already in
  progress → `status="error"`, `error="A rebase is already in progress"`, `returncode=None`,
  no git call. Otherwise git's refusal would leave the old rebase dir in place and
  `_run_rebase` would misreport it as `stopped_on_conflict`.
- `rebase_continue` does not stage (summary section 5).
- Docstring of `RebaseResult` / `_run_rebase` states: `stopped_on_conflict` means "rebase
  stopped and is still in progress", including a stop with no unmerged paths (empty commit,
  hook); use `list_unmerged_paths` to tell. A failed command is `stopped_on_conflict` only
  if git left the rebase in progress, otherwise `error`.

## ALGORITHM
```
_run_rebase: open repo (non-repo -> status=error)
  rc, _, err = run_git_raw(repo, "rebase", *args, env=ENV)
  rc == 0 -> completed, success=True
  _rebase_dir_exists(repo) -> stopped_on_conflict, success=False, error=None, rc, err
  else -> error, success=False, error=f"git rebase {args} failed (exit {rc})", rc, err
rebase_start: validate onto_ref; open repo; _rebase_dir_exists -> error (no git call)
  else _run_rebase(onto_ref)
rebase_abort: open repo; not _rebase_dir_exists -> success (returncode=None)
  rc, _, err = run_git_raw(repo, "rebase", "--abort", env=ENV) -> success iff rc == 0
```

## DATA
`RebaseResult` (`success` True only for `completed`); `rebase_abort` → `GitResult`.

## Tests (real repos via `make_conflict_repo`)
- Already up to date → `completed`. Clean rebase → `completed`.
- Text conflict → `stopped_on_conflict`, `error is None`, `is_rebase_in_progress` True.
- Multi-commit feature (two commits, each conflicting) → start stops, resolve + stage
  (`stage_all_changes`) + continue stops again (`stopped_on_conflict` both times), resolve +
  stage + continue → `completed`. This also proves `stage_all_changes` covers `add -A`.
- Empty-commit stop: resolve the conflict by taking the `main` side (index equals HEAD),
  stage, `rebase_continue` → `stopped_on_conflict` with no unmerged paths
  (`ls-files -u` empty via `run_git_raw`), then `rebase_skip` → `completed`.
  Before writing this test, check with a scratch probe (CLAUDE.md "Scratch probes") whether
  `rebase --continue` with a clean index actually stops under the default merge backend
  (the sequencer may drop the now-empty commit and finish). If it does not stop, force the
  stop in the test setup: set `rebase.backend=apply` in the test repo config (the apply
  backend stops with "No changes"), or use another method that reliably stops. If no method
  produces the stop, write the reason as one line to `pr_info/.blocked.txt` and stop.
- Abort during conflict → success, not in progress, HEAD back at the feature tip.
  Abort with nothing in progress → success.
- `rebase_continue` with nothing in progress → `error`.
- Dirty tree refusing to start → `error`, not in progress.
- `rebase_start` while a rebase is stopped on a conflict → `status == "error"`, rebase
  still in progress.
- Worktree: `make_conflict_repo` leaves `feature` checked out, so create the worktree on a
  new branch: `git worktree add -b feature2 <dir> feature`. `rebase_start(<dir>, "main")`
  stops on the conflict there → `is_rebase_in_progress(<dir>)` True; main checkout False.
- `onto_ref="-x"` → `error`; non-repo: `rebase_start` → `error`,
  `is_rebase_in_progress` → `ValueError`.
