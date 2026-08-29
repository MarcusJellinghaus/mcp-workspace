# Step 1 — Drop the local/remote dedupe; score every ref in one loop

Fixes the primary defect of issue #265. See [summary.md](./summary.md) for context.

## WHERE

- **Modify:** `src/mcp_workspace/git_operations/parent_branch_detection.py`
  (function `detect_parent_branch_via_merge_base`)
- **Create:** `tests/git_operations/test_parent_branch_detection_git.py`
- **Unchanged:** `tests/git_operations/conftest.py` — reuse the existing
  `git_repo_with_remote` fixture as-is.

## WHAT

No signature changes:

```python
def detect_parent_branch_via_merge_base(
    project_dir: Path,
    current_branch: str,
    distance_threshold: int = MERGE_BASE_DISTANCE_THRESHOLD,
) -> Optional[str]: ...
```

New test helper (module-private, in the new test file):

```python
def _commit(repo: Repo, project_dir: Path, filename: str) -> str:
    """Create and commit a file; return the new commit sha."""
```

## HOW

- Delete the `checked_branch_names: set[str]` variable and both places that read
  or write it. This is the bug.
- Because the dedupe is gone, the two near-identical scoring loops have no reason
  to remain separate: collect all candidate refs into one list, then score in a
  single loop. Roughly 35 duplicated lines disappear.
- Add `from git import Commit` to the imports (used only for the candidate list
  annotation). `GitCommandError` / `InvalidGitRepositoryError` imports stay.
- Keep the winner selection (`candidates_passing.sort(...)`) exactly as it is —
  step 3 replaces it. With duplicate names present the existing sort still picks
  the right winner: `[("main", 3), ("other", 2), ("main", 2)]` sorts to
  `("main", 2)` first.
- Keep the skips: `current_branch` for local heads, `current_branch` and `HEAD`
  for remote refs. Scoring `origin/<current_branch>` would nominate the branch as
  its own base.
- Keep the existing broad `except Exception` around remote access, but narrow its
  span to the *collection* of remote refs only.
- Candidate names stay **unprefixed** (`ref.name.replace("origin/", "", 1)`) —
  `needs_rebase` builds `origin/{target}` and would otherwise produce
  `origin/origin/main`.
- Keep `ref.name` alongside the stripped name so debug logs still distinguish
  `main` from `origin/main`; that is the diagnostic for this whole class of bug.

## ALGORITHM

```
current_commit  = repo.heads[current_branch].commit
default_branch  = get_default_branch_name(project_dir)
candidates      = [(head.name, head.name, head.commit) for head in repo.heads if head.name != current_branch]
candidates     += [(strip(ref.name), ref.name, ref.commit) for ref in origin.refs if strip(ref.name) not in (current_branch, "HEAD")]
for name, ref_name, commit in candidates:          # both refs of a branch are scored
    distance = count(merge_base(current_commit, commit) .. current_commit)
    if distance <= distance_threshold: candidates_passing.append((name, distance))
sort by (distance, default_branch first) and return the first name    # unchanged in this step
```

## DATA

- `candidates: list[tuple[str, str, Commit]]` — `(candidate_name, ref_name, commit)`.
  `candidate_name` is the unprefixed branch name used for the result;
  `ref_name` is for logging only.
- `candidates_passing: list[tuple[str, int]]` — unchanged; may now contain the
  same name twice (once per ref), which is intentional.
- Return: `Optional[str]` — unprefixed branch name, or `None`.

## Reference implementation (body of the `with safe_repo_context(...)` block)

```python
            default_branch = get_default_branch_name(project_dir)

            # Collect candidates. Local and remote refs of the same branch are
            # BOTH scored: they point at different commits when the local ref is
            # stale, and the stale one is not the answer (issue #265).
            candidates: list[tuple[str, str, Commit]] = [
                (head.name, head.name, head.commit)
                for head in repo.heads
                if head.name != current_branch
            ]
            try:
                if "origin" in [r.name for r in repo.remotes]:
                    for ref in repo.remotes.origin.refs:
                        branch_name = ref.name.replace("origin/", "", 1)
                        if branch_name in (current_branch, "HEAD"):
                            continue
                        candidates.append((branch_name, ref.name, ref.commit))
            except (
                Exception
            ) as e:  # pylint: disable=broad-exception-caught  # TODO: narrow to GitCommandError
                logger.debug("Error collecting remote branches: %s", e)

            candidates_passing: list[tuple[str, int]] = []
            for branch_name, ref_name, candidate_commit in candidates:
                try:
                    merge_base_list = repo.merge_base(current_commit, candidate_commit)
                    if not merge_base_list:
                        logger.debug("No merge-base found for '%s'", ref_name)
                        continue

                    merge_base = merge_base_list[0]
                    distance = sum(
                        1
                        for _ in repo.iter_commits(
                            f"{merge_base.hexsha}..{current_commit.hexsha}"
                        )
                    )
                    logger.debug(
                        "Candidate '%s': merge-base distance = %d", ref_name, distance
                    )

                    if distance <= distance_threshold:
                        candidates_passing.append((branch_name, distance))

                except GitCommandError as e:
                    logger.debug("Git error checking '%s': %s", ref_name, e)
                    continue

            # (winner selection below is unchanged in this step)
```

## TESTS (write first — they must fail before the change)

Create `tests/git_operations/test_parent_branch_detection_git.py`:

```python
"""Real-git regression tests for parent branch detection (issue #265).

Complements the mock-based tests in test_parent_branch_detection.py: the
defects fixed in #265 are ref topology, which mocks cannot express.
"""

from pathlib import Path

import pytest
from git import Repo

from mcp_workspace.git_operations.parent_branch_detection import (
    detect_parent_branch_via_merge_base,
)

pytestmark = pytest.mark.git_integration


def _commit(repo: Repo, project_dir: Path, filename: str) -> str:
    """Create and commit a file; return the new commit sha."""
    (project_dir / filename).write_text(filename)
    repo.index.add([filename])
    return str(repo.index.commit(f"Add {filename}").hexsha)


def test_stale_local_main_does_not_shadow_origin_main(
    git_repo_with_remote: tuple[Repo, Path, Path]
) -> None:
    """A stale local 'main' must not stop origin/main from being scored."""
    repo, project_dir, _bare_remote = git_repo_with_remote

    sha_a = str(repo.head.commit.hexsha)  # A: initial commit on main
    _commit(repo, project_dir, "b.txt")  # B on main
    repo.git.push("-u", "origin", "main")  # origin/main = B

    repo.git.checkout("-b", "other")  # unrelated branch off B
    _commit(repo, project_dir, "o1.txt")
    repo.git.push("-u", "origin", "other")

    repo.git.checkout("main")
    repo.git.checkout("-b", "feature")  # feature off B
    _commit(repo, project_dir, "f1.txt")
    _commit(repo, project_dir, "f2.txt")

    repo.git.branch("-D", "other")  # only origin/other remains
    repo.git.branch("-f", "main", sha_a)  # local main falls behind by one

    # Distances to feature HEAD: local main (A) = 3, origin/main (B) = 2,
    # origin/other (B) = 2. The old dedupe never scored origin/main, so
    # "other" won at 2. origin/main ties at 2 and wins on the default-branch
    # tiebreak.
    assert detect_parent_branch_via_merge_base(project_dir, "feature") == "main"


def test_feature_branch_off_current_main_detects_main(
    git_repo_with_remote: tuple[Repo, Path, Path]
) -> None:
    """Common case still works: local and remote main agree."""
    repo, project_dir, _bare_remote = git_repo_with_remote

    repo.git.push("-u", "origin", "main")
    repo.git.checkout("-b", "feature")
    _commit(repo, project_dir, "f1.txt")

    assert detect_parent_branch_via_merge_base(project_dir, "feature") == "main"
```

Notes for whoever runs this:

- `get_default_branch_name` resolves `main` through its
  `_check_local_default_branches` fallback, because the bare fixture has no
  `origin/HEAD` symbolic ref. That is expected.
- `git branch -f main <sha>` moves the stale ref without a checkout.
- The first test fails on current `main` with `assert 'other' == 'main'`. Confirm
  that red state before implementing.

## Definition of done

- Both new tests pass; all 13 existing tests in
  `tests/git_operations/test_parent_branch_detection.py` still pass unchanged.
- `checked_branch_names` no longer appears anywhere in the file.
- pylint, mypy, pytest (fast subset **and** `markers=["git_integration"]`) all pass.
- `./tools/format_all.sh` run, then exactly one commit.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`, then implement
> step 1 only.
>
> Use the MCP tools exclusively (`mcp__workspace__read_file`,
> `mcp__workspace__edit_file`, `mcp__workspace__save_file`,
> `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_pytest_check`,
> `mcp__tools-py__run_mypy_check`) as required by `.claude/CLAUDE.md`.
>
> Work test-first: create
> `tests/git_operations/test_parent_branch_detection_git.py` exactly as specified,
> run it with `markers=["git_integration"]`, and confirm
> `test_stale_local_main_does_not_shadow_origin_main` fails with `'other' != 'main'`.
> Then edit `detect_parent_branch_via_merge_base` in
> `src/mcp_workspace/git_operations/parent_branch_detection.py`: delete
> `checked_branch_names` and merge the two scoring loops into one candidate list
> plus one scoring loop, per the reference implementation in the step file. Leave
> the `candidates_passing.sort(...)` winner selection untouched — step 3 replaces
> it.
>
> Do not change `base_branch.py`, `workflows.py` or `branch_status.py` in this
> step. Do not modify the existing mock tests; they must all still pass.
>
> Then run pylint, mypy, the fast pytest subset and the `git_integration` pytest
> run. Fix anything that fails. Finally run `./tools/format_all.sh` and make one
> commit.
