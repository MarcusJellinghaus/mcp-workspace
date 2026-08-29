# Summary — Issue #265: stale local `main` shadows `origin/main`

## Problem

`get_base_branch` (an exposed MCP tool) and `check_branch_status` report the wrong
base branch, producing a spurious `Rebase onto origin/main` recommendation on a
branch that is already fully up to date with `origin/main`.

Four distinct defects, all in the base-branch detection path:

1. **Ref shadowing (primary).** `detect_parent_branch_via_merge_base` scores local
   heads first and records each passing name in `checked_branch_names`; the remote
   loop compares `origin/`-stripped names and skips anything already in that set.
   A local `main` that passes the threshold therefore prevents `origin/main` from
   ever being scored. When local `main` is stale its merge-base with HEAD is older,
   its distance larger, and an unrelated `origin/*` branch wins. The default-branch
   tiebreak in the sort is unreachable in exactly this case.
2. **On the default branch.** `main` is skipped as its own candidate, every other
   candidate ties at distance 0, and ref enumeration order decides the winner.
3. **`needs_rebase` short-circuit.** `current_branch == target_branch` returns
   `up-to-date` without looking at commits, hiding a genuinely-behind local `main`.
4. **Recommendation wording.** `Rebase onto origin/main` is the wrong action when
   the current branch *is* `main`; there the action is a fast-forward pull.

## Design / architectural changes

No new modules, no new layers, no new dependencies. All changes are local to three
existing functions; the module boundaries in `docs/ARCHITECTURE.md` are unaffected.

### 1. Candidate scoring: two loops → one list, one loop

`detect_parent_branch_via_merge_base` currently has two near-identical scoring
loops (local heads, then `origin/*` refs) coupled by the `checked_branch_names`
dedupe set. Removing the dedupe removes the only reason for them to be separate,
so they collapse into: *collect all candidate refs, then score them in one loop*.

The set is deleted outright. Local and remote refs of the same branch are both
scored under the same stripped name. This is self-correcting rather than a new
preference rule: a stale local ref's merge-base is at or before the remote ref's,
so its distance is always ≥, and taking the minimum prefers the fresher ref by
construction. Net effect: `parent_branch_detection.py` gets ~30 lines *smaller*
while fixing the bug.

### 2. Winner selection: sort → min-per-name + explicit tie rule

The `candidates_passing.sort(key=lambda x: (x[1], 0 if x[0] == default_branch else 1))`
line is replaced by a `dict[branch_name, min_distance]` accumulated during scoring,
then three explicit rules: default branch among the minimum-distance names wins;
otherwise a single name wins; otherwise return `None` (ambiguous).

Accumulating the minimum *per name* is load-bearing, not incidental: change 1
deliberately puts `main` in the candidate set twice, and a naive count of
minimum-distance entries would read the normal "local and remote agree" case as a
two-way tie and wrongly trigger the fallback. Making the dict the accumulator
means that collapse is a property of the data structure rather than a separate
pass that a later edit could drop.

### 3. Detection returns `None` more often; the caller already handles it

Both the default-branch case and the ambiguous-tie case return `None`.
`detect_base_branch` needs **no change** — its existing step 4 → step 5
fall-through already supplies the default branch. `None` from detection now means
"I cannot say", not "no repository", and the conservative fallback is visible
rather than a coin flip decided by ref enumeration order.

Note the default-branch short-circuit is *not* redundant with the tie rule: with
exactly one other branch in the repository there is no tie, and that branch would
win.

### 4. Detection returns unprefixed names — unchanged, and load-bearing

`needs_rebase` builds `origin/{target_branch}`. Returning `origin/main` would
construct `origin/origin/main`, take the "target branch not found" path and
silently yield `rebase_needed=False` with an error string in the reason. Both refs
therefore enter the candidate set under the **stripped** name.

### 5. `_generate_recommendations` gains one input

It receives `report_data`, which carries only CI / rebase / task / PR fields and so
cannot currently see the branch. One new key, `is_default_branch`, is plumbed in
from `collect_branch_status`, read with `.get(..., False)` so every existing
dict-literal call site stays valid.

## Behaviour changes

| Situation | Before | After |
|---|---|---|
| Feature branch, local `main` stale, another `origin/*` at `origin/main`'s tip | base = the other branch | base = `main` |
| Checked out on `main` | base = first local branch enumerated | base = `main` (via fallback) |
| Two distinct non-default branches tied at the minimum distance | first enumerated wins | `None` → caller falls back to default branch |
| `needs_rebase` on `main`, `origin/main` ahead | `up-to-date` | `N commits behind` |
| `needs_rebase` when `origin/<target>` does not exist and target is the current branch | `up-to-date` | `up-to-date` (preserved) |
| `needs_rebase` when `origin/<target>` does not exist and target is another branch | `error: ... not found` | unchanged |
| Recommendation while on the default branch and behind | `Rebase onto origin/main` | `Pull origin/main` |

`check_branch_status` on `main` will now report `Rebase=BEHIND` where it previously
said up-to-date. That is the point of change 3, not a regression.

## Files created / modified

No new folders or modules.

**Modified — source**

| File | Step(s) | Change |
|---|---|---|
| `src/mcp_workspace/git_operations/parent_branch_detection.py` | 1, 2, 3 | drop dedupe + single scoring loop; default-branch short-circuit; min-per-name + tie rule |
| `src/mcp_workspace/git_operations/workflows.py` | 4 | remove `current_branch == target_branch` short-circuit in `needs_rebase` |
| `src/mcp_workspace/checks/branch_status.py` | 5 | plumb `is_default_branch`; `Pull origin/main` wording |

**Created — tests**

| File | Step(s) |
|---|---|
| `tests/git_operations/test_parent_branch_detection_git.py` | 1, 2, 3 |

**Modified — tests**

| File | Step |
|---|---|
| `tests/git_operations/test_branches.py` | 4 (two cases added to `TestNeedsRebase`) |
| `tests/checks/test_branch_status_recommendations.py` | 5 (one case added) |

**Read but not modified:** `src/mcp_workspace/git_operations/base_branch.py` (its
step 4 → step 5 fall-through is already correct), `src/mcp_workspace/server.py`
(`get_base_branch`), `tests/git_operations/conftest.py` (the
`git_repo_with_remote` fixture is reused as-is).

## Steps

Each step is exactly one commit: tests first (red), then implementation (green),
then all three checks passing.

| Step | Scope | Files |
|---|---|---|
| [step_1](./step_1.md) | Drop the local/remote dedupe; one scoring loop | `parent_branch_detection.py`, new real-git test file |
| [step_2](./step_2.md) | Return `None` when the current branch is the default branch | `parent_branch_detection.py`, real-git test file |
| [step_3](./step_3.md) | Min-distance-per-name + return `None` on an unresolved tie | `parent_branch_detection.py`, real-git test file |
| [step_4](./step_4.md) | Remove the `needs_rebase` short-circuit | `workflows.py`, `test_branches.py` |
| [step_5](./step_5.md) | `Pull origin/main` on the default branch | `branch_status.py`, `test_branch_status_recommendations.py` |

Steps 1 → 3 must run in order (step 3 replaces the winner-selection code that
step 1 leaves in place). Steps 4 and 5 are independent of the others.

## Testing strategy

Detection tests are **real-git** tests on the existing `git_repo_with_remote`
fixture, marked `@pytest.mark.git_integration`. The existing
`tests/git_operations/test_parent_branch_detection.py` stubs `merge_base` and
`iter_commits`, so a mock-based regression test could only assert that the sort
prefers the entry the mock was told to prefer. The defect is ref topology, so the
test must build the topology.

The 13 existing mock tests in `test_parent_branch_detection.py` must keep passing
unchanged — every one of them has either a unique minimum distance or the default
branch among the winners, so none of them are affected by steps 1–3. If one starts
failing, the implementation has drifted from this plan.

New real-git tests live in a separate file rather than being appended to the
500-line mock file, following the existing `test_compact_diffs_integration.py`
precedent and staying clear of the 750-line limit.

## Verification (run after every step)

```
mcp__tools-py__run_pylint_check
mcp__tools-py__run_mypy_check
mcp__tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])
mcp__tools-py__run_pytest_check(extra_args=["-n", "auto"], markers=["git_integration"])
```

Format with `./tools/format_all.sh` before committing.

## Out of scope (per the issue)

- No `fetch` is added before detection; a never-fetched `origin/main` is still
  scored stale. The alternative puts network I/O into a path that has none.
- `_generate_recommendations` still hardcodes `origin/main` regardless of the
  detected base, so a branch stacked on another feature branch is still told to
  rebase onto `main`. Step 5 only handles the default-branch case.
