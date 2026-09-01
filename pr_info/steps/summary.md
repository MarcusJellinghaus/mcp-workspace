# Summary — Issue #269: a branch deleted on origin can win merge-base detection

## Problem

When HEAD is stacked on `feature-A`, `merge_base(HEAD, origin/feature-A)` is `feature-A`'s tip,
so its distance counts only the current branch's own commits and it beats `origin/main` by
construction. Once `feature-A` is merged and deleted on GitHub, the local `origin/feature-A` ref
survives until something prunes it, and `detect_parent_branch_via_merge_base` keeps electing a
branch that no longer exists.

Both exposed entry points inherit the wrong answer silently:

- `get_base_branch` (`server.py:1524` → `detect_base_branch` at `:1551`) reports a branch that is gone.
- `needs_rebase` builds `origin/feature-A`, resolves it from that same stale ref
  (`workflows.py:185`), finds nothing to be behind, and reports "up-to-date".

`check_branch_status` reaches `detect_base_branch` too (via `async_poll_branch_status` →
`collect_branch_status`, `checks/branch_status.py:586`), so it inherits the fix along with
`get_base_branch`.

The originally reported local/remote dedupe defect is the same as #265 and already landed in
`82e6b5a` (PR #276). This plan covers the residual defect only.

## Solution

Validate **the winner, not the whole field**, where the merge-base guess enters `detect_base_branch`.

A new private helper asks origin whether the branch still exists. A three-guard gate in
`_detect_from_merge_base` decides when that question is worth asking. A rejected winner returns
`None`, so `detect_base_branch` falls through to its existing step 5 (`base_branch.py:190-194`)
and supplies the default branch.

## Architectural / design changes

No layer, module, or public-API change: everything stays inside `git_operations`, both new
symbols are private, and no existing signature moves. `docs/ARCHITECTURE.md` needs no update.
The design decisions worth recording:

| Decision | Rationale |
|---|---|
| Gate lives in `_detect_from_merge_base`, not in `detect_parent_branch_via_merge_base` | #265 deliberately kept the scoring function free of network I/O so it stays real-git testable, and it is exported for direct use. `_detect_from_merge_base` is a shim inside an orchestrator that already does GitHub I/O in steps 2 and 3 — the natural seam, and both entry points pass through it. |
| Only the merge-base source is validated | The issue's `### Base Branch` section and a PR base are *statements*; merge-base is a guess. Rewriting explicit user intent to `main` would convert a visible mistake into an invisible one, and GitHub already guarantees a PR base exists. |
| Two existence checks, not one | An empty `ls-remote` is ambiguous on its own: "deleted upstream" or "never pushed", which need opposite outcomes. The local `origin/<name>` ref disambiguates — it only exists because a fetch put it there. |
| Guards in cost order: local ref lookup → default branch → `ls-remote` | A never-pushed base costs one ref lookup and no round trip; base = `main`, the common answer, costs no round trip either. |
| A failed `ls-remote` returns `None`, never `False` | Offline or an unreachable origin must never silently rewrite a correct base to `main`. Tested as `is False`; `if not exists:` would collapse `None` into "gone". |
| An unresolvable default branch skips validation | A "gone" verdict would cascade: step 5 also yields `None`, and `collect_branch_status` renders `Base: unknown` with a spurious `origin/unknown not found`. `test_tie_without_a_resolvable_default_branch_still_picks_a_candidate` guards exactly this. |
| A rejected winner is not replaced by the runner-up | A branch gone upstream has its commits in the default branch already, so for a stack one deep the default branch *is* the next-best answer. A deeper stack would have elected the nearer live branch in the first place. |
| Helper named `_origin_still_has_branch` | `remote_branch_exists` is taken by the local-cache check this module already imports. Two names differing by a leading underscore, one cached and one live, would be a trap. |

**Cost:** one `ls-remote` per `get_base_branch` / `check_branch_status` call, and only when the
winner is a non-default branch that has a local `origin/<name>` ref. `collect_branch_status` runs
once after polling completes, not per poll interval. That call runs with `GIT_TERMINAL_PROMPT=0`
(`_LS_REMOTE_ENV`, step_1), which suppresses git's *own* terminal credential prompt so the usual
unauthenticated case errors out and falls into the `None` path. It is not a hard guarantee: an
interactive credential helper such as Git Credential Manager on Windows is not disabled by it,
and GitPython's `kill_after_timeout` does not work on Windows, so the call is not guaranteed to
fail fast. `fetch_remote`, already reached from the same `check_branch_status` flow, makes an
unhardened network call today, so this is the existing exposure rather than a new one.

## Files created / modified

| Path | Action | Notes |
|---|---|---|
| `src/mcp_workspace/git_operations/base_branch.py` | modified | Add `_origin_still_has_branch`; add the gate to `_detect_from_merge_base`; extend the `branch_queries` import with `remote_branch_exists` and add `safe_repo_context` from `core`; add the `_LS_REMOTE_ENV` constant that keeps the one network call non-interactive. ~50 lines. |
| `tests/git_operations/test_base_branch_git.py` | created | Four real-git tests, `git_integration`-marked, no mocks. ~85 lines. |
| `pr_info/steps/summary.md`, `pr_info/steps/step_1.md` | created | This plan. |

Deliberately untouched: `parent_branch_detection.py`, `branch_queries.py`, `workflows.py`,
`server.py`, `tests/git_operations/conftest.py`, `tests/git_operations/test_base_branch.py`,
`pyproject.toml`, `.github/workflows/ci.yml`, `vulture_whitelist.py`, `docs/`.

`tests/git_operations/test_base_branch.py` needs no edit: `test_falls_back_to_merge_base` ends
with `mock_default.assert_not_called()`, and its `Path("/repo")` is not a repository, so
`remote_branch_exists` is `False` and the gate returns at guard 1 before any default-branch
lookup. Step 1 verifies this by running, not by assuming.

## Implementation steps

- [step_1.md](./step_1.md) — validate the merge-base winner against origin.

**One step, one commit.** The helper and the gate are not independent parts: a helper with no
caller is dead code in an intermediate commit, and testing it directly would duplicate the
coverage the gate tests already give through the public path. Total source diff is ~35 lines.

## Rejected alternatives (from the issue, not to be revisited here)

- Ancestry-based "already merged" filtering — verified against this repo: everything is
  squash-merged, so a merged branch tip is never an ancestor of `main` and the filter catches nothing.
- `--prune` in the `/rebase` skill, or pruning inside `fetch_remote` — the fix is correct
  regardless of pruning; `get_base_branch` never fetches at all.
- Reporting stale refs from `check_branch_status` — tells the caller the `Base:` field may be
  wrong instead of making it right.

## Deviation from the issue text

The issue's Approach step 1 asks for `except GitCommandError` *plus* a broad `except Exception`
in the helper. Both branches would return `None` and log at debug, so this plan uses a single
broad `except Exception` with the `pylint: disable` comment the sibling modules already carry.
Behaviour is identical — any failure reads as "unknown" — and it is the requirement the issue's
sentence exists to state ("`GitCommandError` alone does not cover a missing or unreadable
origin"). Flagged here because it is a visible departure from the literal wording; restoring the
two-clause form is a one-line change if preferred.
