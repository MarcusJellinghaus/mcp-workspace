# Step 1 — Discard a merge-base winner that was deleted on origin

See [summary.md](./summary.md) for the problem, the design decisions, and the file inventory.

One commit: tests + implementation + checks passing.

## WHERE

| Path | Action |
|---|---|
| `tests/git_operations/test_base_branch_git.py` | create |
| `src/mcp_workspace/git_operations/base_branch.py` | modify |

## WHAT

**New private helper** in `base_branch.py`, placed directly above `_detect_from_merge_base`:

```python
def _origin_still_has_branch(project_dir: Path, branch_name: str) -> Optional[bool]:
```

**Modified** (signature unchanged):

```python
def _detect_from_merge_base(project_dir: Path, current_branch: str) -> Optional[str]:
```

Its docstring `Returns:` section currently reads "Parent branch name, or None if not found
within threshold", which no longer covers the new outcome. Extend it to name both `None` cases:
no candidate within the threshold, **or** the winning candidate was rejected because origin no
longer has that branch (the caller then falls back to the default branch).

## HOW — integration points

Imports in `base_branch.py` (keep the file's absolute-import style; its siblings use relative):

```python
from mcp_workspace.git_operations.branch_queries import (
    extract_issue_number_from_branch,
    get_current_branch_name,
    get_default_branch_name,
    remote_branch_exists,          # added
)
from mcp_workspace.git_operations.core import safe_repo_context   # added
```

No new `git` import is needed — the single broad `except Exception` covers `GitCommandError`
(see the deviation note in summary.md). `detect_base_branch` is **not** modified: a discarded
winner returns `None` and its existing step 5 supplies the default branch.

Keep the helper lean. The siblings in `branch_queries.py` open with an `is_git_repository` guard
and an "is there an origin remote" check; `_origin_still_has_branch` needs neither, because guard 1
of the gate only passes when a local `origin/<name>` ref exists, which proves both.

## ALGORITHM

Module constant, next to the helper — the environment for the one network call:

```python
# ls-remote must fail fast, never wait on a human. Passed per call via the
# `env=` kwarg so nothing leaks into the shared Git object's environment.
_LS_REMOTE_ENV = {
    "GIT_TERMINAL_PROMPT": "0",   # no credential prompt on the terminal
    "GIT_ASKPASS": "",            # and no GUI/askpass helper either
    "SSH_ASKPASS": "",
    "GIT_SSH_COMMAND": "ssh -oBatchMode=yes -oConnectTimeout=10",
    # Abort a stalled HTTP transfer (config via env, git 2.31+).
    "GIT_CONFIG_COUNT": "2",
    "GIT_CONFIG_KEY_0": "http.lowSpeedLimit",
    "GIT_CONFIG_VALUE_0": "1000",
    "GIT_CONFIG_KEY_1": "http.lowSpeedTime",
    "GIT_CONFIG_VALUE_1": "10",
}
```

Helper:

```
try:
    with safe_repo_context(project_dir) as repo:
        output = str(
            repo.git.ls_remote(
                "--heads", "origin", f"refs/heads/{branch_name}", env=_LS_REMOTE_ENV
            )
        )
        return bool(output.strip())        # empty output means the branch is gone
except Exception:                          # pylint: disable=broad-exception-caught
    log at debug; return None              # unknown, never "gone"
```

The pattern is the **full ref**, not the bare name. `ls-remote` matches a bare `feature-A`
against any ref whose path ends in `/feature-A`, so an unrelated `refs/heads/team/feature-A`
would mask the deletion of `feature-A`. `refs/heads/<branch_name>` matches exactly one ref.

Every hardening above turns a hang into an exception, which the `except` already maps to `None`
— the winner is kept, matching the `ls-remote` failure rule. Do **not** use GitPython's
`kill_after_timeout`: it is documented as having no effect on Windows, this project's primary
platform. The env dict is not separately tested — without mocks a prompt that never happens is
unobservable, and `test_unreachable_origin_keeps_the_winner` already pins the failure path.

Gate, appended to `_detect_from_merge_base` after the existing detection call:

```
if result is None: return None
if not remote_branch_exists(project_dir, result): return result   # never pushed
default = get_default_branch_name(project_dir)
if default is None or default == result: return result            # nothing better to fall back to
if _origin_still_has_branch(project_dir, result) is False:
    logger.debug("Discarding merge-base winner '%s': deleted on origin", result)
    return None                                                   # gone upstream
return result
```

**Logging.** The existing `logger.debug("Detected base branch from merge-base: '%s'", result)`
(`base_branch.py:134`) fires before the gate, so after this change it can announce a branch that
is then discarded — the misleading trace for exactly the bug being fixed. Reword it to
`logger.debug("Merge-base elected candidate branch: '%s'", result)`, which stays true on every
path, and let the new debug line above be the record of a rejection. No test asserts either
message.

`str(...)` around `ls_remote` matters for `mypy --strict` (GitPython returns `Any`), matching
`str(repo.git.symbolic_ref(...))` at `branch_queries.py:204`. `remote_branch_exists` returns a
plain `bool`, so `if not ...` is correct there; `_origin_still_has_branch` is tri-state and must
be compared with `is False`.

## DATA

| Symbol | Returns |
|---|---|
| `_origin_still_has_branch` | `True` — origin still lists the branch. `False` — origin answered and the branch is gone. `None` — the question could not be answered (no origin, offline, unreadable repo); the caller keeps its current answer. |
| `_detect_from_merge_base` | Unchanged type `Optional[str]`. New `None` case: the winner was rejected as gone upstream. Callers already treat every `None` the same way. |

No new data structures, no state, no config.

## TDD order

1. Write `tests/git_operations/test_base_branch_git.py` in full and run it. Exactly one test
   fails — `test_winner_deleted_upstream_falls_back_to_default_branch` returns `feature-A`
   today. The other three pass against current behaviour and must stay green; they are what
   pins the gate's three keep-the-winner paths.
2. Add `_origin_still_has_branch` and the gate.
3. Re-run: all four green.

## Test file

`pytestmark = pytest.mark.git_integration` at module level — CI splits on that marker
(`ci.yml:111-112`), and an unmarked real-git test would land in the unit job. Built on the
existing `git_repo_with_remote` fixture (`tests/git_operations/conftest.py:36`), which yields
`(repo, project_dir, bare_remote_dir)` with a real bare origin on disk. No mocks anywhere.

Two module-level helpers keep each test to three or four lines:

```python
def _commit(repo: Repo, project_dir: Path, filename: str) -> str:
    """Create and commit a file; return the new commit sha."""

def _stack_on_feature_a(
    repo: Repo, project_dir: Path, push_feature_a: bool = True
) -> None:
    """Push main, branch feature-A off it, stack feature-B on feature-A.

    Leaves HEAD on feature-B. Merge-base scoring elects 'feature-A' at
    distance 1 over 'main' at distance 2.
    """
```

`_commit` is a four-line copy of the one in `test_parent_branch_detection_git.py:21` — copy it
rather than importing a private across test modules, which is the existing idiom.

Every test calls `detect_base_branch(project_dir, current_branch="feature-B")` with no
`issue_manager` or `pr_manager`, so detection steps 2 and 3 are skipped and the merge-base path
is what is under test.

| Test | Setup | Assert |
|---|---|---|
| `test_winner_deleted_upstream_falls_back_to_default_branch` | stack, then `Repo(bare_remote_dir).delete_head("feature-A", force=True)` with no fetch, so `origin/feature-A` survives locally | `"main"` — returns `"feature-A"` before the fix |
| `test_winner_still_on_origin_is_kept` | stack, no deletion | `"feature-A"` |
| `test_never_pushed_winner_is_kept` | `_stack_on_feature_a(..., push_feature_a=False)` | `"feature-A"` |
| `test_unreachable_origin_keeps_the_winner` | stack, then `repo.git.remote("set-url", "origin", str(tmp_path / "gone.git"))` — leaves `origin/feature-A` intact while `ls_remote` fails instantly | `"feature-A"` |

The never-pushed test does not assert that no round trip fires: with no mocks that is
unobservable, the gate order guarantees it, and the unreachable-origin test already covers the
network path.

In the deletion test the local `feature-A` head still exists, which is deliberate — a surviving
local head must not rescue a branch deleted upstream. The default branch resolves to `"main"`
through `get_default_branch_name`'s local fallback, since the fixture sets no `origin/HEAD`.

## Verification

```
mcp__mcp-tools-py__run_format_code
mcp__mcp-tools-py__run_pylint_check
mcp__mcp-tools-py__run_pytest_check   extra_args: ["-n", "auto"]
mcp__mcp-tools-py__run_mypy_check
```

The full pytest run must confirm — by running, not by assuming — that these three existing tests
still pass unchanged. All three now traverse the gate, and each pins a different guard. If any
fails, the gate is what needs revisiting — do not edit these tests.

| Test | Why it now matters |
|---|---|
| `test_falls_back_to_merge_base` (`tests/git_operations/test_base_branch.py:306-317`) | Ends in `mock_default.assert_not_called()`. Its `Path("/repo")` is not a repository, so `remote_branch_exists` is `False` and the gate returns at guard 1 before any default-branch lookup. |
| `TestDetectFromMergeBase::test_returns_parent_branch` (`test_base_branch.py:183-187`) | Same `Path("/repo")`, same guard-1 exit; asserts the winner still comes back. |
| `test_tie_without_a_resolvable_default_branch_still_picks_a_candidate` (`tests/git_operations/test_parent_branch_detection_git.py:129-155`) | Its final assertion `detect_base_branch(project_dir, current_branch="feature") == "trunk"` runs on a real repo where `origin/trunk` exists but `get_default_branch_name` is `None` — the **only** coverage of guard 2's `default is None` path, and the cascade guard summary.md relies on. It is `git_integration`-marked, so a `-m 'not git_integration'` run will not show it. |

Commit message:

```
fix(base_branch): discard merge-base winner deleted on origin (#269)
```

## LLM prompt

> Implement step 1 of the plan for issue #269 in the `mcp-workspace` repo.
>
> Read `pr_info/steps/summary.md` for the design and rationale, then `pr_info/steps/step_1.md`
> for the specification. Follow the project's `.claude/CLAUDE.md` rules — use the
> `mcp__mcp-workspace__*` and `mcp__mcp-tools-py__*` tools, not native file or Bash tools.
>
> Work in TDD order: create `tests/git_operations/test_base_branch_git.py` first and run it,
> confirming that exactly one test (`test_winner_deleted_upstream_falls_back_to_default_branch`)
> fails and the other three pass. Then add `_origin_still_has_branch` and the three-guard gate in
> `_detect_from_merge_base` in `src/mcp_workspace/git_operations/base_branch.py` as specified
> under WHAT / HOW / ALGORITHM. Change nothing else — in particular not
> `parent_branch_detection.py`, `detect_base_branch`, the conftest, or the existing
> `test_base_branch.py`.
>
> Then run format, pylint, pytest (`-n auto`) and mypy, all of which must pass, and report the
> actual output of the failing-then-passing test run. Commit once with the message given above.
> If any existing test breaks, report it rather than editing the test to suit the change.
