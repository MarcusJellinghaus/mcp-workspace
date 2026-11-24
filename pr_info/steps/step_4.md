# Step 4 — One push for 120 branches (task 2)

## LLM prompt

Read `pr_info/steps/summary.md`, then implement this step (`pr_info/steps/step_4.md`) only. In `test_many_branches_not_truncated`, replace the 119 `update_ref` calls and `push --all` with a single `git push` of 120 refspecs. Run only that test file, then pylint and mypy, and produce exactly one commit.

## WHERE

- `tests/git_operations/test_remote_queries.py::TestListRemoteBranches::test_many_branches_not_truncated` (~lines 115–132)

## WHAT

Only the setup lines change; the test signature and assertions stay unchanged.

## HOW

- Origin starts empty: `git_repo_with_remote` doesn't push `main`, and the test asserts 120 branches including `main`. So the refspecs are `main` plus 119 `HEAD:refs/heads/feature-NNN`.
- Use `repo.git.push("origin", *refspecs)`.
- Not loose ref files (they break with `init.defaultRefFormat=reftable`). Not `update-ref --stdin` via GitPython's `istream` (needs a real file handle).
- `head_sha` / `rev_parse` is then unused; remove it (one git process fewer).

## ALGORITHM

```
repo, project_dir, _ = git_repo_with_remote
features = [f"feature-{i:03d}" for i in range(119)]
expected = set(features) | {"main"}
repo.git.push("origin", "main", *[f"HEAD:refs/heads/{name}" for name in features])
result = list_remote_branches(project_dir)   # assertions unchanged
```

## DATA

`expected: set[str]` with 120 names. Assertions unchanged.

## Tests / checks

- `run_pytest_check(extra_args=["-n", "auto", "tests/git_operations/test_remote_queries.py"])`
- `run_pylint_check`, `run_mypy_check`, `run_format_code`.
- If the single push fails (e.g. command-line length), write one line to `pr_info/.blocked.txt` with the error and stop.

## Commit

`test(git_operations): create 120 remote branches with one push`
