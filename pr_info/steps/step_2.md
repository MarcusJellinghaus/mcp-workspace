# Step 2 — `push_current_branch`

## LLM prompt

> Read `pr_info/steps/summary.md` (design points 4, 5, 7) and this file. Implement step 2 only:
> tests first, then the library changes. Run format, pylint, pytest (`-n auto`), mypy,
> lint-imports and ruff; all must pass. Make exactly one commit.

## WHERE

- `src/mcp_workspace/git_operations/rebase.py`: rename `_git_version` → `git_version`
  (public, same signature; update its use in `probe_rebase_conflicts`).
- `tests/git_operations/test_rebase_probe.py`: `VERSION` patch target → `...rebase.git_version`.
- `src/mcp_workspace/git_operations/remotes.py`: new `push_current_branch`,
  private `_remote_tracking_reflog_exists`. (remotes.py is ~576 lines; stay under 750.)
- New tests: `tests/git_operations/test_push_current_branch.py`
- `tests/conftest.py`: new fixtures `origin_clone`, `make_clone` (shared by steps 2, 3, 5, 9–13).

## Fixtures (`tests/conftest.py`)

- `origin_clone(tmp_path) -> Path`: bare `origin.git` (HEAD → `refs/heads/main`), seeded with one
  commit on `main` from a seed repo, then a real `git clone` into `work/`; user name/email set,
  `commit.gpgsign=false`. Returns the clone dir (has `origin/HEAD`, fresh-clone reflog state).
- `make_clone(tmp_path) -> Callable[[str], Path]`: makes another configured clone of the same
  origin under the given dir name.

Existing `git_repo_with_remote` in `tests/git_operations/conftest.py` stays unchanged.

## WHAT

```python
# rebase.py
def git_version(repo: Repo) -> tuple[int, int]: ...          # renamed, unchanged body

# remotes.py
_FORCE_IF_INCLUDES_MIN_VERSION = (2, 30)

def _remote_tracking_reflog_exists(repo: Repo, branch: str) -> bool:
    """True if refs/remotes/origin/<branch> has a reflog (`git reflog exists`)."""

def push_current_branch(project_dir: Path, force: bool = False) -> GitResult:
    """Push the current branch to origin with -u and a full refspec."""
```

## HOW

- `from ._subprocess_git import run_git_timed`; `from .rebase import git_version`
  (remotes already imports from `.rebase`).
- `_remote_tracking_reflog_exists`: `run_git_raw(repo, "reflog", "exists",
  f"refs/remotes/origin/{branch}", env=GIT_NONINTERACTIVE_ENV)` → `rc == 0`.
- Current branch: `get_current_branch_name(project_dir)` (from `.branch_queries`).
- Not exported from `__init__.py`.

## ALGORITHM

```
branch = get_current_branch_name(project_dir); None -> error "HEAD is detached; check out a branch first"
if force:
    with safe_repo_context: if git_version(repo) < (2, 30) -> error "git_push_force needs git 2.30+ (--force-if-includes)"
                            if not _remote_tracking_reflog_exists(repo, branch) -> error (fresh-clone text below)
refspec = f"refs/heads/{branch}:refs/heads/{branch}"
args = ["push", "-u", *(["--force-with-lease", "--force-if-includes"] if force else []), "origin", refspec]
return run_git_timed(project_dir, *args) as GitResult (drop stdout; on failure keep error + scrubbed stderr)
```

Fresh-clone error text: `"refs/remotes/origin/<b> has no reflog (fresh clone?); --force-if-includes
would refuse falsely. Force-push via Bash after checking the remote branch"`.

Non-repository: `get_current_branch_name` returns None → treat via an explicit
`is_git_repository` check first → error `"Not a git repository: <dir>"`, returncode/stderr None.

## DATA

`GitResult`; `stderr` holds git's (scrubbed) push output on success too, so the tool can show it.

## Tests (write first)

Unit (patch `run_git_timed`, `get_current_branch_name`, `git_version`, reflog helper):
- argv for `force=False` is exactly `push -u origin refs/heads/b:refs/heads/b`.
- argv for `force=True` contains `--force-with-lease --force-if-includes`, never `--force`.
- detached HEAD → error, `run_git_timed` not called.
- `force=True` with version (2, 29) → error, not called; with no reflog → error, not called.
- timeout result from `run_git_timed` is passed through (`success=False`, timeout text).

Integration (`git_integration`; `origin_clone` / `make_clone` fixtures):
- push of a new branch → success; `git rev-parse --abbrev-ref @{u}` is `origin/<b>`.
  **Precondition:** if the upstream is *not* set by `-u` with a full refspec,
  write one line to `pr_info/.blocked.txt` and stop.
- a tag with the same name as the branch exists → push still succeeds.
- after a pushed branch is amended in the pushing clone, `force=True` succeeds.
- in a fresh clone (`origin_clone` / `make_clone`, no new fetch), `force=True` → reflog error.

## Commit

`feat(git_operations): add push_current_branch with full refspec and force-if-includes`
