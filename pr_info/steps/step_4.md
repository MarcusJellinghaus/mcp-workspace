# Step 4 — Remove the `needs_rebase` self-comparison short-circuit

Makes a stale local default branch report its real behind-count. See
[summary.md](./summary.md) for context. Independent of steps 1–3 and 5.

## WHERE

- **Modify:** `src/mcp_workspace/git_operations/workflows.py` (function `needs_rebase`)
- **Modify:** `tests/git_operations/test_branches.py` (class `TestNeedsRebase`,
  already marked `@pytest.mark.git_integration`)

## WHAT

No signature changes:

```python
def needs_rebase(
    project_dir: Path, target_branch: Optional[str] = None
) -> Tuple[bool, str]: ...
```

Two edits inside the function: delete the `current_branch == target_branch`
short-circuit, and move its "up-to-date" outcome into the `rev_parse` failure
branch, gated on the same equality.

## HOW

- The short-circuit compares *names*, not commits, so on `main` it answers
  `up-to-date` without looking at `origin/main`. The code below it already does
  the right thing: `rev_parse --verify origin/<target>`, then count
  `HEAD..origin/<target>`.
- **The gate must be kept**, only moved. The short-circuit is also what makes a
  local-only branch (no `origin/<name>`) return `up-to-date` instead of falling
  into the "target branch not found" error path. Preserve that by returning
  `up-to-date` from the `except GitCommandError` branch **when
  `current_branch == target_branch`**.
- Do **not** return `up-to-date` for every missing `origin/<target>`: that would
  break `test_needs_rebase_nonexistent_target` (on `feature-branch`, target
  `nonexistent`, expects an error) and would silently swallow typo'd branch names.
- Nothing else changes: the fetch, the detached-HEAD check, the target
  auto-detection and the commit counting are all untouched.

## ALGORITHM

```
... fetch, resolve current_branch and target_branch (unchanged) ...
# (deleted) if current_branch == target_branch: return False, "up-to-date"
origin_target = f"origin/{target_branch}"
try: repo.git.rev_parse("--verify", origin_target)
except GitCommandError:
    if current_branch == target_branch: return False, "up-to-date"   # never pushed
    return False, f"error: target branch '{origin_target}' not found"
count HEAD..origin_target -> 0 = "up-to-date", 1 = "1 commit behind", n = "n commits behind"
```

## DATA

`Tuple[bool, str]` — unchanged shape. New reachable outcome:
`(True, "1 commit behind")` while checked out on the default branch.

## Reference implementation

Delete:

```python
            # Don't check rebase against self
            if current_branch == target_branch:
                logger.debug("Current branch is the target branch")
                return False, "up-to-date"
```

Replace the `rev_parse` guard with:

```python
            # Check if origin/target_branch exists
            origin_target = f"origin/{target_branch}"
            try:
                repo.git.rev_parse("--verify", origin_target)
            except GitCommandError:
                if current_branch == target_branch:
                    # Current branch was never pushed - nothing to compare
                    # against, so it cannot be behind.
                    logger.debug("No %s found - treating as up-to-date", origin_target)
                    return False, "up-to-date"
                error_msg = f"target branch '{origin_target}' not found"
                logger.debug("Target branch not found: %s", origin_target)
                return False, f"error: {error_msg}"
```

## TESTS (write first)

Add to `class TestNeedsRebase` in `tests/git_operations/test_branches.py`,
following the existing style in that class:

```python
    def test_needs_rebase_on_default_branch_behind_origin(
        self, git_repo_with_remote: tuple[Repo, Path, Path]
    ) -> None:
        """A stale local 'main' reports its real behind-count."""
        repo, project_dir, _bare_remote = git_repo_with_remote

        sha_a = str(repo.head.commit.hexsha)
        repo.git.push("-u", "origin", "main")

        (project_dir / "new_file.txt").write_text("new content")
        repo.index.add(["new_file.txt"])
        repo.index.commit("New commit on main")
        repo.git.push("origin", "main")  # origin/main is now ahead by one

        repo.git.reset("--hard", sha_a)  # local main falls behind

        needs_rebase_result, reason = needs_rebase(project_dir, "main")
        assert needs_rebase_result is True
        assert reason == "1 commit behind"

    def test_needs_rebase_current_branch_never_pushed(
        self, git_repo_with_remote: tuple[Repo, Path, Path]
    ) -> None:
        """No origin/<current branch> means up-to-date, not an error."""
        _repo, project_dir, _bare_remote = git_repo_with_remote

        # 'main' exists locally only; the bare origin has no refs at all.
        needs_rebase_result, reason = needs_rebase(project_dir, "main")
        assert needs_rebase_result is False
        assert reason == "up-to-date"
```

Notes:

- The first test fails before the change with `assert False is True` — the
  short-circuit returns `(False, "up-to-date")`.
- The second test passes both before and after; it is the regression guard for the
  local-only case that the short-circuit used to cover. Keep it.
- `fetch_remote` succeeds against an empty bare remote, so both tests reach the
  `rev_parse` guard.
- `test_needs_rebase_nonexistent_target` and the other four existing cases in the
  class must still pass unchanged.

## Definition of done

- Both new tests pass; the six existing `TestNeedsRebase` cases pass unchanged.
- `tests/checks/test_branch_status.py` (which mocks `needs_rebase`) is unaffected.
- pylint, mypy, pytest (fast subset **and** `markers=["git_integration"]`) all pass.
- `./tools/format_all.sh` run, then exactly one commit.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_4.md`, then implement
> step 4 only.
>
> Use the MCP tools exclusively (`mcp__workspace__read_file`,
> `mcp__workspace__edit_file`, `mcp__tools-py__run_pylint_check`,
> `mcp__tools-py__run_pytest_check`, `mcp__tools-py__run_mypy_check`) as required
> by `.claude/CLAUDE.md`.
>
> Work test-first: add the two cases from the step file to `class TestNeedsRebase`
> in `tests/git_operations/test_branches.py`, run with
> `markers=["git_integration"]` and confirm
> `test_needs_rebase_on_default_branch_behind_origin` fails. Then edit
> `needs_rebase` in `src/mcp_workspace/git_operations/workflows.py`: delete the
> `current_branch == target_branch` short-circuit and move its `up-to-date`
> outcome into the `except GitCommandError` branch of the `rev_parse` check, gated
> on `current_branch == target_branch`, exactly as in the step file.
>
> Keep the "target branch not found" error for every other missing
> `origin/<target>` — `test_needs_rebase_nonexistent_target` must still pass. Do
> not touch `parent_branch_detection.py` or `branch_status.py`.
>
> Then run pylint, mypy, the fast pytest subset and the `git_integration` pytest
> run. Fix anything that fails. Finally run `./tools/format_all.sh` and make one
> commit.
