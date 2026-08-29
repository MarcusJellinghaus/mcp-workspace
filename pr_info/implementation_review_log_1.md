# review-implementation review log 1

## Round 1 — 2026-08-30
**Findings**:
I'll start by loading the tool schemas I need.I'll gather context in parallel: knowledge base files, the issue, and the branch state.Now let me read the knowledge base, plan files, and compute the diff.Ironically, there's no local `main` ref. Let me check available refs.All 5 steps are committed. Let me diff against `origin/main`.Implementation changes present. Let me read the source diffs.Let me read the full implementation files and the new tests.Now let me run the quality checks and inspect `get_default_branch_name`.All tests pass (367 git-integration, 1716 unit). Let me run the remaining checks and find `needs_rebase` callers.`src/mcp_workspace/git_operations/parent_branch_detection.py:137` — medium — `default_branch in winners` has no `None` guard (unlike line 71); when `get_default_branch_name()` returns `None` — origin/HEAD unset and no local `main`/`master`, since `_check_local_default_branches` scans only `repo.branches` — the default-branch tiebreak silently cannot apply, so any tie returns `None`, `detect_base_branch` step 5 also returns `None`, `collect_branch_status` sets `base_branch="unknown"`, and rebase status degrades to `error: target branch 'origin/unknown' not found`. Previously the sort still returned a candidate name in this configuration.

`src/mcp_workspace/git_operations/parent_branch_detection.py:81` — low — `head.commit` is now evaluated in a list comprehension outside any per-candidate error handling, whereas the remote collection at lines 86-96 kept its `try`/`except`; one broken local ref now aborts the entire detection via the outer broad `except` at line 157 (returns `None`) instead of skipping just that candidate, which the pre-change per-branch `try` did.

`src/mcp_workspace/checks/branch_status.py:453` — low — the new `Pull origin/main` message hardcodes `origin/main`, so a repository whose default branch is `master` is told to pull a branch that does not exist; the real default branch name is already computed one call away at line 588 and could be interpolated.

`src/mcp_workspace/server.py:37` — low — unrelated cosmetic reformat of a single-name import into parenthesized form; no behavior change and outside the scope of issue #265.
**Decisions**:
Verdict(decision='tasks', tasks=["In src/mcp_workspace/git_operations/parent_branch_detection.py:137, guard the default-branch tiebreak against a None result from get_default_branch_name() the same way line 71 does, so that when no default branch can be resolved the tie still resolves to a candidate name instead of returning None (which cascades to base_branch='unknown' and a bogus 'origin/unknown' rebase error).", 'In src/mcp_workspace/git_operations/parent_branch_detection.py:81, restore per-candidate error handling around the local-branch head.commit access (matching the try/except used for remotes at lines 86-96) so a single broken local ref is skipped rather than aborting all detection via the broad except at line 157.', "In src/mcp_workspace/checks/branch_status.py:453, interpolate the actual detected default branch name into the 'Pull origin/<branch>' message instead of hardcoding 'origin/main', using the value already computed at line 588, so repositories whose default branch is 'master' get a valid instruction.", 'Add a test covering the tie case where get_default_branch_name() returns None, asserting detect_base_branch still returns a candidate branch rather than None.'], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-08-30
**Findings**:
I'll start by loading the tools I need and gathering context.`src/mcp_workspace/checks/branch_status.py:456` — medium — the non-default-branch arm of the same ternary still hardcodes `"Rebase onto origin/main"` while the sibling arm (line 454) now interpolates `report_data["default_branch_name"]`; in a repo whose default branch is `master`, every feature branch is told to rebase onto a branch that does not exist, and the correct name is already in scope on the adjacent line.

`src/mcp_workspace/git_operations/parent_branch_detection.py:110` — medium — the scoring loop now runs `repo.merge_base` + `repo.iter_commits` (two git subprocesses each) for both the local and the remote ref of every branch, roughly doubling the git work of `get_base_branch`/`check_branch_status`; in the common case the two refs point at the same commit, so skipping a candidate whose `candidate_commit.hexsha` was already scored would remove the duplication without weakening the #265 fix (which only needs the two refs scored when they *differ*).

`src/mcp_workspace/git_operations/parent_branch_detection.py:94` — low — remote candidate collection is guarded by a single `try` around the whole loop, while local collection now guards per ref (lines 87-93); one unreadable `origin/*` ref silently drops every remaining remote candidate, which can include `origin/main` — the exact shadowing failure this issue fixes.

`src/mcp_workspace/git_operations/workflows.py:143` — low — the `Returns:` docstring of `needs_rebase` is unchanged although the contract changed: `current_branch == target_branch` no longer returns `"up-to-date"` unconditionally and now reports a real behind-count, with `"up-to-date"` retained only when `origin/<target>` is missing (lines 180-184).

`src/mcp_workspace/server.py:37` — low — unrelated cosmetic reformat of a single-name import into parenthesized form; no behaviour change and outside the scope of issue #265 (raised in round 1, still present).
**Decisions**:
Verdict(decision='tasks', tasks=['In src/mcp_workspace/checks/branch_status.py:456, replace the hardcoded "Rebase onto origin/main" in the non-default-branch arm of the ternary with the interpolated report_data["default_branch_name"], matching the sibling arm at line 454, so repositories whose default branch is \'master\' get a valid rebase target.', 'In src/mcp_workspace/git_operations/parent_branch_detection.py:110, skip scoring a candidate whose candidate_commit.hexsha has already been scored so the local and remote refs of the same branch are not both walked with merge_base + iter_commits when they point at the same commit; the two refs must still be scored independently when they differ.', 'In src/mcp_workspace/git_operations/parent_branch_detection.py:94, move the try/except inside the remote candidate loop so it guards each ref individually (mirroring the local collection at lines 87-93), preventing one unreadable origin/* ref from dropping the remaining remote candidates including origin/main.', 'In src/mcp_workspace/git_operations/workflows.py:143, update the Returns: docstring of needs_rebase to reflect the new contract: current_branch == target_branch now reports the real behind-count, and "up-to-date" is returned only when origin/<target> is missing (lines 180-184).'], escalate_reason=None)
**Changes**:
applied

## Round 3 — 2026-08-30
**Findings**:
I'll gather context first.`src/mcp_workspace/server.py:37` — low — unrelated cosmetic reformat of the single-name `set_reference_projects` import into parenthesized form; no behaviour change and outside the scope of issue #265 (raised in rounds 1 and 2, still present in the diff).
**Decisions**:
Verdict(decision='dismiss', tasks=[], escalate_reason=None)
**Changes**:
rebase-needed
**Escalate reason**: rebase
