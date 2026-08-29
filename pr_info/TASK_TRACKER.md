# Task Status Tracker

## Instructions for LLM

This tracks **Feature Implementation** consisting of multiple **Tasks**.

**Summary:** See [summary.md](./steps/summary.md) for implementation overview.

**How to update tasks:**
1. Change [ ] to [x] when implementation step is fully complete (code + checks pass)
2. Change [x] to [ ] if task needs to be reopened
3. Add brief notes in the linked detail files if needed
4. Keep it simple - just GitHub-style checkboxes

**Task format:**
- [x] = Task complete (code + all checks pass)
- [ ] = Task not complete
- Each task links to a detail file in steps/ folder

---

## Tasks

### Step 1: Drop the local/remote dedupe; score every ref in one loop

Detail: [step_1.md](./steps/step_1.md)

- [x] Implementation: create `tests/git_operations/test_parent_branch_detection_git.py` with the two real-git tests, then delete `checked_branch_names` in `detect_parent_branch_via_merge_base` and merge the two scoring loops into one candidate list plus one scoring loop
- [x] Quality checks: pylint, pytest (fast subset + `markers=["git_integration"]`), mypy — fix all issues
- [x] Commit message prepared (text drafted and used for commit d2470a8; `pr_info/.commit_message.txt` is gitignored and rejected by the MCP workspace tools, so the file itself cannot be written)

### Step 2: Return `None` when the current branch is the default branch

Detail: [step_2.md](./steps/step_2.md)

- [x] Implementation: add `test_returns_none_on_the_default_branch`, then add the default-branch guard after `default_branch` is resolved and update the docstring `Returns:` block
- [x] Quality checks: pylint, pytest (fast subset + `markers=["git_integration"]`), mypy — fix all issues
- [x] Commit message prepared (text drafted below; `pr_info/.commit_message.txt` is gitignored and rejected by the MCP workspace tools, so the file itself cannot be written)

  ```
  Return None from parent detection on the default branch

  On the default branch there is no meaningful parent to detect: the
  default branch is skipped as its own candidate and every other branch
  ties at distance 0, so ref enumeration order picked an arbitrary
  winner (issue #265, second defect).

  Add a guard in detect_parent_branch_via_merge_base that returns None
  immediately after default_branch is resolved when the current branch
  is the default branch, and widen the docstring Returns: block to name
  both meanings of None.

  base_branch.py is unchanged: detect_base_branch already falls through
  to the default branch name when detection returns None, so
  get_base_branch still returns "main" while on "main".

  Add test_returns_none_on_the_default_branch to
  tests/git_operations/test_parent_branch_detection_git.py, covering
  both the direct None result and the caller's fallback.
  ```

### Step 3: Minimum distance per branch name, and `None` on an unresolved tie

Detail: [step_3.md](./steps/step_3.md)

- [x] Implementation: add the two tie tests, then replace `candidates_passing` with `best: dict[str, int]`, replace the sort-based winner selection with the three selection rules, and finalize the docstring `Returns:` block
- [x] Quality checks: pylint, pytest (fast subset + `markers=["git_integration"]`), mypy — fix all issues
- [x] Commit message prepared (text drafted below; `pr_info/.commit_message.txt` is gitignored and rejected by the MCP workspace tools, so the file itself cannot be written)

  ```
  Score minimum distance per branch name and return None on a tie

  The winner was chosen by sorting (distance, default-branch-first) and
  taking the first entry, so ref enumeration order silently decided every
  tie between equally close branches (issue #265, third defect).

  Replace candidates_passing with best: dict[str, int], accumulating the
  smallest distance per unprefixed branch name. Keying by name is
  load-bearing: step 1 deliberately scores a branch's local and remote ref
  separately, and a tie rule counting raw entries would read the normal
  "local and remote agree" case as a two-way tie and wrongly fall back.

  Replace the sort with three explicit selection rules: the default branch
  wins if it is among the minimum-distance names; otherwise a single name
  wins; otherwise log the ambiguity and return None, letting
  detect_base_branch fall back to the default branch. Rule 1 preserves the
  intent of the old sort key, which the shadowing bug made unreachable.

  Extend the docstring Returns: block to list all three meanings of None.

  Add test_returns_none_when_two_branches_tie and
  test_local_and_remote_ref_of_one_branch_are_not_a_tie to
  tests/git_operations/test_parent_branch_detection_git.py; the second is a
  trap guard against implementing the tie rule over entries rather than
  distinct names.
  ```

### Step 4: Remove the `needs_rebase` self-comparison short-circuit

Detail: [step_4.md](./steps/step_4.md)

- [x] Implementation: add the two `TestNeedsRebase` cases, then delete the `current_branch == target_branch` short-circuit in `needs_rebase` and move its up-to-date outcome into the `rev_parse` `GitCommandError` branch
- [x] Quality checks: pylint, pytest (fast subset + `markers=["git_integration"]`), mypy — fix all issues
- [x] Commit message prepared (text drafted below; `pr_info/.commit_message.txt` is gitignored and rejected by the MCP workspace tools, so the file itself cannot be written)

  ```
  Remove the needs_rebase self-comparison short-circuit

  needs_rebase short-circuited on current_branch == target_branch and
  returned "up-to-date" without looking at any commits, so a stale local
  main was reported as current even when origin/main was ahead (issue
  #265, fourth defect).

  Delete the short-circuit and move its up-to-date outcome into the
  except GitCommandError branch of the origin/<target> rev_parse check,
  still gated on current_branch == target_branch. That gate is
  load-bearing, not incidental: it is what makes a never-pushed local
  branch return "up-to-date" instead of falling into the "target branch
  not found" error path. Every other missing origin/<target> keeps
  returning the error, so a typo'd target branch is not silently
  swallowed.

  The fetch, the detached-HEAD check, the target auto-detection and the
  commit counting are unchanged. check_branch_status on main will now
  report Rebase=BEHIND where it previously said up-to-date; that is the
  point of the change.

  Add test_needs_rebase_on_default_branch_behind_origin (a stale local
  main reports "1 commit behind") and
  test_needs_rebase_current_branch_never_pushed (the regression guard for
  the local-only case the short-circuit used to cover) to class
  TestNeedsRebase in tests/git_operations/test_branches.py.
  ```

### Step 5: Say `Pull origin/main` when the current branch is the default branch

Detail: [step_5.md](./steps/step_5.md)

- [ ] Implementation: add the recommendation test and the end-to-end `test_on_default_branch_recommends_pull`, then plumb `is_default_branch` through `report_data` and switch the wording in `_generate_recommendations`
- [ ] Quality checks: pylint, pytest (fast subset + `markers=["git_integration"]`), mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: verify all steps implemented, check for regressions and leftover defects
- [ ] PR summary prepared
