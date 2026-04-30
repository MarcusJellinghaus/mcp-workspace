# Step 1 — Harden test fixtures against global `commit.gpgsign`

> **LLM prompt** — Read `pr_info/steps/summary.md` for context, then implement
> exactly this step. Make one commit at the end. Run `pylint`, `mypy`, and
> `pytest` (with `-n auto -m "not git_integration and not github_integration"`
> for fast iteration; then with `markers=["git_integration"]` to verify the
> integration tests still pass).

## Why this step exists

Step 3 will switch `commit_staged_files()` to porcelain (`repo.git.commit`),
which inherits `~/.gitconfig`. Contributors or CI runners with `commit.gpgsign=
true` set globally would silently start trying to sign during integration tests
across `test_commits.py`, `test_diffs.py`, and `test_file_tracking.py`. This
step neutralizes that risk **before** the production change lands, so step 3
can be reviewed without fixture-noise concerns.

This is the only step whose verification is "existing tests still pass" — there
is no new test to write because fixture changes have no observable behavior
beyond not-failing-in-hostile-environments.

## WHERE

```
tests/git_operations/conftest.py          # modify
```

## WHAT

Update each of the three fixtures (`git_repo`, `git_repo_with_remote`,
`git_repo_with_commit`) to set two extra repo-local config values inside the
existing `with repo.config_writer() as config:` block:

```python
config.set_value("commit", "gpgsign", "false")
config.set_value("tag", "gpgsign", "false")
```

Place these **inside the existing `config_writer` block**, alongside the
existing `user.name` / `user.email` settings. Do not introduce a second
`config_writer` block.

For `git_repo_with_remote` and `git_repo_with_commit`, the existing fixture
calls `repo.index.commit("Initial commit")` after the config block. Since
`repo.index.commit` is plumbing and ignores `commit.gpgsign` anyway, ordering
is not load-bearing for the fixture's own initial commit — but the new
`gpgsign=false` setting takes effect for any commits produced by tests that
use the fixture.

## HOW

No imports change. No signature changes. No new fixtures. No `__all__`
adjustments.

## ALGORITHM

```
for each of the three git_repo* fixtures:
    inside the existing `with repo.config_writer() as config:` block:
        add config.set_value("commit", "gpgsign", "false")
        add config.set_value("tag", "gpgsign", "false")
```

## DATA

No data structure changes. Fixture return signatures unchanged:
- `git_repo` → `tuple[Repo, Path]`
- `git_repo_with_remote` → `tuple[Repo, Path, Path]`
- `git_repo_with_commit` → `tuple[Repo, Path]`

## Verification

- `pylint` clean.
- `mypy` clean.
- `pytest -m "git_integration"` — all existing integration tests still pass.
- Fast unit test suite still passes.

## Commit message

```
test(git_operations): disable gpg signing in git_repo fixtures

Set repo-local commit.gpgsign=false and tag.gpgsign=false in all three
git_repo* fixtures so integration tests don't pick up a contributor's
global signing config when commit_staged_files switches to porcelain
(refs #180).
```
