# Step 3 — `_is_stale_ci_run` staleness predicate

Read `pr_info/steps/summary.md` first for overall context. This step implements
design change (3) from that summary and depends on step 2 being complete
(`get_remote_branch_commit_sha` must exist).

## Precondition

If `src/mcp_workspace/git_operations/branch_queries.py` does not export
`get_remote_branch_commit_sha`, or `src/mcp_workspace/git_operations/commits.py`
does not export `get_latest_commit_sha`, write one line to
`pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/checks/branch_status.py` (modify — add one private function)
- `tests/checks/test_branch_status_sha_check.py` (create)

## WHAT

```python
def _is_stale_ci_run(
    project_dir: Path, branch_name: str, run_commit_sha: Optional[str]
) -> bool:
    """Return True only when HEAD is pushed and the run predates it."""
```

This is the one shared sha-check helper required by the issue, used by both
`_collect_ci_status` (step 4) and `_wait_for_ci` (step 6). It lives here, not
in `branch_status_polling.py`, so `branch_status_polling.py` can import it
without `branch_status.py` ever importing back from `branch_status_polling.py`.

## HOW

- Add to the existing `from mcp_workspace.git_operations.branch_queries import (...)`
  block in `branch_status.py`: `get_remote_branch_commit_sha`.
- Add a new import line: `from mcp_workspace.git_operations.commits import get_latest_commit_sha`.
- No decorators — this is a plain function, same style as the other
  `_collect_*` helpers in this module.

## ALGORITHM

```
if not run_commit_sha: return False
head_sha = get_latest_commit_sha(project_dir)
if head_sha is None: return False
origin_sha = get_remote_branch_commit_sha(project_dir, branch_name)
if origin_sha is None or origin_sha != head_sha: return False  # unpushed / unresolvable
return run_commit_sha != head_sha
```

## DATA

Returns `bool`. `True` only when: `run_commit_sha` is present AND local HEAD is
resolvable AND `origin/<branch_name>` is resolvable AND HEAD == that remote sha
AND `run_commit_sha != HEAD`. Every other case (missing sha, non-repo, detached
HEAD, no origin, unpushed HEAD) returns `False` — "skip the check", which both
callers already treat identically to "not stale".

## Tests to write first (TDD)

Create `tests/checks/test_branch_status_sha_check.py`. Patch
`mcp_workspace.checks.branch_status.get_latest_commit_sha` and
`mcp_workspace.checks.branch_status.get_remote_branch_commit_sha` (both are
module-level names in `branch_status.py` after step 3's import, so patch them
there, not in their defining modules) with `unittest.mock.patch`. Use
`Path("/tmp")` and a dummy branch name as in the sibling CI test files.

1. `test_stale_when_pushed_and_mismatched` — head=`"abc"`, origin=`"abc"`,
   `run_commit_sha="old"` → `True`.
2. `test_not_stale_when_matching` — head=`"abc"`, origin=`"abc"`,
   `run_commit_sha="abc"` → `False`.
3. `test_skipped_when_head_unpushed` — head=`"abc"`, origin=`"def"` →
   `False`, regardless of `run_commit_sha`.
4. `test_skipped_when_origin_sha_unresolvable` — head=`"abc"`, origin=`None`
   → `False`.
5. `test_skipped_when_head_sha_unresolvable` — head=`None` → `False` (origin
   lookup need not even be asserted-called, but may be; don't assert
   non-call).
6. `test_skipped_when_run_commit_sha_missing` — `run_commit_sha=None` and
   separately `run_commit_sha=""` → `False` in both cases, without needing to
   mock the git helpers at all (early return).

Confirm all fail (ImportError — function doesn't exist yet) before
implementing, then implement and confirm all pass.

## Commit

One commit: tests + implementation + green checks.
Message: `feat(branch_status): add _is_stale_ci_run staleness predicate`
