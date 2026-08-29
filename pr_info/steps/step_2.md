# Step 2 — Return `None` when the current branch is the default branch

Fixes the "second defect" of issue #265. See [summary.md](./summary.md) for context.
Depends on step 1 being committed.

## WHERE

- **Modify:** `src/mcp_workspace/git_operations/parent_branch_detection.py`
  (function `detect_parent_branch_via_merge_base`)
- **Modify:** `tests/git_operations/test_parent_branch_detection_git.py`
  (created in step 1)
- **Unchanged:** `src/mcp_workspace/git_operations/base_branch.py` — its existing
  step 4 → step 5 fall-through already supplies the default branch when detection
  returns `None`.

## WHAT

No signature changes. A four-line guard added to
`detect_parent_branch_via_merge_base`, placed immediately after `default_branch`
is resolved and before any candidate is collected or scored.

## HOW

- On the default branch, `main` is skipped as its own candidate and every other
  candidate ties at distance 0, so ref enumeration order picks the winner. There
  is no meaningful parent to detect: say so.
- Guard on `default_branch is not None and current_branch == default_branch`.
  Without the `is not None` check a repository with no detectable default branch
  would be unaffected anyway, but the explicit check keeps the intent readable and
  keeps the existing mock tests (which patch `get_default_branch_name` to return
  `None`) obviously unaffected.
- Returning early — rather than letting `detect_base_branch` special-case it —
  states a true fact at the layer where the ambiguity lives.
  `detect_parent_branch_via_merge_base` is exported and can be called directly.
- This is **not** made redundant by step 3's tie rule: with exactly one other
  branch in the repository there is no tie, and that branch would win.

## ALGORITHM

```
default_branch = get_default_branch_name(project_dir)
if default_branch is not None and current_branch == default_branch:
    log "current branch is the default branch - no parent to detect"
    return None
... existing candidate collection and scoring ...
```

## DATA

Return value only: `None` instead of an arbitrary branch name.
`detect_base_branch` turns that `None` into the default branch name at its step 5,
so `get_base_branch` returns `"main"` when you are on `main`.

## Reference implementation

Insert directly below the existing `default_branch = get_default_branch_name(project_dir)`:

```python
            if default_branch is not None and current_branch == default_branch:
                logger.debug(
                    "Current branch '%s' is the default branch - no parent branch",
                    current_branch,
                )
                return None
```

## TESTS (write first)

Append to `tests/git_operations/test_parent_branch_detection_git.py`, and add the
import `from mcp_workspace.git_operations.base_branch import detect_base_branch`:

```python
def test_returns_none_on_the_default_branch(
    git_repo_with_remote: tuple[Repo, Path, Path]
) -> None:
    """On 'main' there is no parent branch to detect."""
    repo, project_dir, _bare_remote = git_repo_with_remote

    repo.git.push("-u", "origin", "main")
    repo.git.checkout("-b", "feature")
    _commit(repo, project_dir, "f1.txt")
    repo.git.push("-u", "origin", "feature")
    repo.git.checkout("main")

    # Old behaviour: 'feature' ties at distance 0 and wins on enumeration order.
    assert detect_parent_branch_via_merge_base(project_dir, "main") is None
    # The caller's existing fallback supplies the default branch.
    assert detect_base_branch(project_dir, current_branch="main") == "main"
```

Notes:

- `detect_base_branch` is called with no `issue_manager` / `pr_manager`, so it
  makes no GitHub calls — the issue and PR steps return `None` immediately.
- Before the change the first assertion fails with `'feature' is not None`.

## Definition of done

- The new test passes; the two step-1 tests and all mock tests still pass.
- pylint, mypy, pytest (fast subset **and** `markers=["git_integration"]`) all pass.
- `./tools/format_all.sh` run, then exactly one commit.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`, then implement
> step 2 only. Step 1 is already committed.
>
> Use the MCP tools exclusively (`mcp__workspace__read_file`,
> `mcp__workspace__edit_file`, `mcp__tools-py__run_pylint_check`,
> `mcp__tools-py__run_pytest_check`, `mcp__tools-py__run_mypy_check`) as required
> by `.claude/CLAUDE.md`.
>
> Work test-first: append `test_returns_none_on_the_default_branch` to
> `tests/git_operations/test_parent_branch_detection_git.py` (adding the
> `detect_base_branch` import), run it with `markers=["git_integration"]` and
> confirm it fails. Then add the four-line default-branch guard to
> `detect_parent_branch_via_merge_base` immediately after `default_branch` is
> resolved, exactly as in the step file.
>
> Do not change `base_branch.py` — its fall-through is already correct. Do not
> touch the winner-selection code; step 3 handles that.
>
> Then run pylint, mypy, the fast pytest subset and the `git_integration` pytest
> run. Fix anything that fails. Finally run `./tools/format_all.sh` and make one
> commit.
