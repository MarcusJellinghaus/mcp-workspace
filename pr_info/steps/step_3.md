# Step 3 — Minimum distance per branch name, and `None` on an unresolved tie

Replaces the sort-based winner selection. See [summary.md](./summary.md) for context.
Depends on steps 1 and 2 being committed.

## WHERE

- **Modify:** `src/mcp_workspace/git_operations/parent_branch_detection.py`
  (function `detect_parent_branch_via_merge_base` — the scoring loop's accumulator
  and the winner-selection block)
- **Modify:** `tests/git_operations/test_parent_branch_detection_git.py`

## WHAT

No signature changes. The `candidates_passing: list[tuple[str, int]]` accumulator
becomes `best: dict[str, int]` (branch name → smallest distance seen for that
name), and the `candidates_passing.sort(key=...)` block becomes three explicit
selection rules.

## HOW

- **Why a dict, not a list plus a reduction pass:** step 1 deliberately puts
  `main` in the candidate set twice (local ref and remote ref). A tie rule that
  counted minimum-distance *entries* would read the normal "local and remote
  agree" case as a two-way tie and wrongly fall back. Accumulating the minimum per
  name makes that collapse a property of the data structure rather than a separate
  pass a later edit could drop. It also removes the list and the sort — one data
  structure instead of three.
- **Selection rules, in order:**
  1. `default_branch` is among the minimum-distance names → return it. This
     preserves the intent of the old sort key
     (`0 if x[0] == default_branch else 1`), which the shadowing bug made
     unreachable.
  2. Exactly one name at the minimum → return it.
  3. Two or more distinct names at the minimum → log and return `None`.
     `detect_base_branch` falls back to the default branch. Predictable and
     visibly conservative, rather than a coin flip decided by ref enumeration
     order.
- `default_branch` may be `None`; `None in winners` is `False`, so no extra guard
  is needed.
- Sort `winners` only so the debug log and the single-winner path are
  deterministic.
- Keep the empty-result path (`return None` when nothing passed the threshold) and
  its existing log message.

## ALGORITHM

```
for each candidate (name, ref_name, commit):
    distance = ...                                  # unchanged from step 1
    if distance > threshold: continue
    if name not in best or distance < best[name]: best[name] = distance   # min per NAME
minimum = min(best.values());  winners = sorted names whose distance == minimum
if default_branch in winners: return default_branch      # default wins ties
if len(winners) == 1:         return winners[0]
return None                                              # ambiguous -> caller falls back
```

## DATA

- `best: dict[str, int]` — unprefixed branch name → minimum distance across that
  branch's local and remote refs. Replaces `candidates_passing`.
- `minimum: int`, `winners: list[str]` (sorted).
- Return: `Optional[str]` — unprefixed branch name, or `None` for
  "no candidate" / "ambiguous".

## Reference implementation

Inside the scoring loop, replace the append:

```python
                    if distance > distance_threshold:
                        continue
                    if branch_name not in best or distance < best[branch_name]:
                        best[branch_name] = distance
```

Replace the whole `if candidates_passing: ... return winner[0]` block with:

```python
            if not best:
                logger.debug("No candidate branches found within threshold")
                return None

            minimum = min(best.values())
            winners = sorted(name for name, dist in best.items() if dist == minimum)

            if default_branch in winners:
                winner = default_branch
            elif len(winners) == 1:
                winner = winners[0]
            else:
                logger.debug(
                    "Ambiguous parent branch: %s tied at distance %d", winners, minimum
                )
                return None

            logger.debug(
                "Detected parent branch from merge-base: '%s' (distance=%d)",
                winner,
                minimum,
            )
            return winner
```

## TESTS (write first)

Append to `tests/git_operations/test_parent_branch_detection_git.py`:

```python
def test_returns_none_when_two_branches_tie(
    git_repo_with_remote: tuple[Repo, Path, Path]
) -> None:
    """Two distinct non-default names at the minimum distance: no answer."""
    repo, project_dir, _bare_remote = git_repo_with_remote

    sha_a = str(repo.head.commit.hexsha)
    repo.git.push("-u", "origin", "main")  # origin/main = A
    sha_b = _commit(repo, project_dir, "b.txt")  # local main = B, not pushed

    repo.git.checkout("-b", "x", sha_b)
    _commit(repo, project_dir, "x1.txt")
    repo.git.checkout("-b", "y", sha_b)
    _commit(repo, project_dir, "y1.txt")
    repo.git.checkout("-b", "feature", sha_b)
    _commit(repo, project_dir, "f1.txt")
    repo.git.branch("-f", "main", sha_a)

    # Distances to feature HEAD: x = 1, y = 1, main (local and remote, both A) = 2.
    assert detect_parent_branch_via_merge_base(project_dir, "feature") is None
    # Caller falls back to the default branch rather than picking x or y.
    assert detect_base_branch(project_dir, current_branch="feature") == "main"


def test_local_and_remote_ref_of_one_branch_are_not_a_tie(
    git_repo_with_remote: tuple[Repo, Path, Path]
) -> None:
    """A branch scored twice (local + remote) must not trigger the tie fallback."""
    repo, project_dir, _bare_remote = git_repo_with_remote

    repo.git.push("-u", "origin", "main")
    repo.git.checkout("-b", "develop")
    _commit(repo, project_dir, "d1.txt")
    repo.git.push("-u", "origin", "develop")  # local develop == origin/develop
    repo.git.checkout("-b", "feature")
    _commit(repo, project_dir, "f1.txt")

    # 'develop' is scored twice at distance 1; 'main' twice at distance 2.
    assert detect_parent_branch_via_merge_base(project_dir, "feature") == "develop"
```

Notes:

- The first test fails before the change with `assert 'x' is None` (the sort is
  stable, so `x` wins on enumeration order).
- The second test passes both before *and* after a correct implementation — it is
  a trap guard, not a red test. It fails only if the tie rule is implemented over
  raw entries instead of distinct names, which is the specific mistake the issue
  warns about.

## Definition of done

- All four real-git tests pass; all 13 mock tests in
  `test_parent_branch_detection.py` still pass **unchanged** (each has either a
  unique minimum or the default branch among the winners — if one fails, the
  implementation has drifted from this plan).
- `candidates_passing` and the `.sort(...)` call no longer appear in the file.
- pylint, mypy, pytest (fast subset **and** `markers=["git_integration"]`) all pass.
- `./tools/format_all.sh` run, then exactly one commit.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`, then implement
> step 3 only. Steps 1 and 2 are already committed.
>
> Use the MCP tools exclusively (`mcp__workspace__read_file`,
> `mcp__workspace__edit_file`, `mcp__tools-py__run_pylint_check`,
> `mcp__tools-py__run_pytest_check`, `mcp__tools-py__run_mypy_check`) as required
> by `.claude/CLAUDE.md`.
>
> Work test-first: append the two tests from the step file to
> `tests/git_operations/test_parent_branch_detection_git.py`, run with
> `markers=["git_integration"]` and confirm `test_returns_none_when_two_branches_tie`
> fails while `test_local_and_remote_ref_of_one_branch_are_not_a_tie` already
> passes. Then in `detect_parent_branch_via_merge_base` replace the
> `candidates_passing` list with a `best: dict[str, int]` accumulated as
> minimum-per-branch-name, and replace the sort-based winner selection with the
> three rules in the step file.
>
> Do not modify the existing mock tests in `test_parent_branch_detection.py` — all
> 13 must still pass. Do not touch `workflows.py` or `branch_status.py`.
>
> Then run pylint, mypy, the fast pytest subset and the `git_integration` pytest
> run. Fix anything that fails. Finally run `./tools/format_all.sh` and make one
> commit.
