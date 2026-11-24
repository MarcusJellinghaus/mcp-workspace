# Step 5 — Fewer `Repo` objects in test helpers (task 3, decision 4)

## LLM prompt

Read `pr_info/steps/summary.md`, then implement this step (`pr_info/steps/step_5.md`) only. Change test helpers that open `Repo(path)` only to run a git command so they use `git.Git(path)` instead. Start with `test_ref_snapshot._git`, then the candidate list below. Apply decision 4 where reading the code shows a cheap config fix. Run only the changed test files, then ruff, vulture, pylint and mypy, and produce exactly one commit.

## WHERE

Primary:
- `tests/git_operations/test_ref_snapshot.py`: `_git` (line ~43), `_repo` (line ~34), `_init_repo` (line ~73)

Candidate helpers (module-level functions that open `Repo(path)`). Convert to `git.Git` only those whose `Repo` is used **solely** for `repo.git.<cmd>(...)`. Apply the one-`Repo`-per-test rule (HOW) to the others:
- `tests/_reference_at_ref_helpers.py` (~24)
- `tests/git_operations/test_origin_fetch.py` (~26)
- `tests/git_operations/test_push_current_branch.py` (~216)
- `tests/git_operations/test_branch_writes.py` (~19–30)
- `tests/toolset/test_git_branch.py` (~182–187)
- `tests/toolset/test_git_branch_delete.py` (~294–307)
- `tests/toolset/test_git_commit.py` (~284–315)
- `tests/toolset/test_git_push.py` (~137–147)
- `tests/toolset/test_git_push_force.py` (~124–133)

## WHAT

```python
# tests/git_operations/test_ref_snapshot.py
def _git(path: Path, *args: str) -> str:
    """Run a git command in ``path`` and return its stdout."""
    return str(git.Git(path).execute(["git", *args]))
```

Helpers converted to `git.Git` keep their signature and return type. Helpers switched to one `Repo` per test change their first parameter from `project_dir: Path` to `repo: Repo`, and keep their return type.

## HOW

- `Repo(p).git.<cmd>(*a)` → `git.Git(p).<cmd>(*a)`: same git process and same `str` output, but no `Repo` object (so no `gc.collect()`).
- **Do not convert** helpers to `git.Git` when they need the object model (`.branches`, `.active_branch`, `.head.commit`, `.untracked_files`, `.index`, `config_writer()`). `git.Git` has no object model. Some of these start git themselves (`.head.commit` → `git cat-file`, `.untracked_files` → `git status`; see summary), so the test's marker stays as it is.
- **One `Repo` per test:** if an object-model helper is called 2 or more times in one test (e.g. `_current` / `_upstream` in `tests/git_operations/test_branch_writes.py` and `tests/toolset/test_git_branch.py`), open one `Repo` in the test and pass it to the helper. Change the helper's parameter from `project_dir: Path` to `repo: Repo` and update all its callers. A helper that no test calls more than once stays unchanged.
- `test_ref_snapshot._init_repo`: replace `Repo.init(path).close()` with `path.mkdir(parents=True, exist_ok=True)` followed by `git.Git(path).init()`, so no throwaway `Repo` object is created. The `mkdir` is needed because `Repo.init` creates the directory itself, while `git.Git(path)` needs it to exist as its working directory.
- A `with Repo(...)` block is **not** a fix (root cause 1).
- `test_ref_snapshot`: delete `_repo` if `_git` was its only user. Otherwise keep it for the remaining users. `_close_repo_safely` call counts are unaffected: they count `src` calls, not test helper closes.
- Import style: `import git` (module) where `git.Git` is used. Drop `from git import Repo` if unused.
- Inline `Repo(x).git.<cmd>` one-liners inside test bodies are left alone (KISS; decision 3 spirit).
- **Decision 4** (unmarked tests that open `Repo` but start no git): find candidates by reading unit-group files that use `Repo(`, `safe_repo_context` or reference-project tools. Where the test creates the `Repo`, apply the same techniques. Where `src` opens it and that behaviour isn't under test, reduce it via configuration (e.g. `reference_fetch_interval_minutes=0`). Otherwise leave it. Profile a file only when reading is inconclusive: a cProfile plugin in `.scratch/`, single file, `-n 0`. Delete `.scratch/` before committing.

## ALGORITHM

```
for each candidate helper:
    if Repo used only as repo.git.<cmd>:
        replace Repo(path).git.<cmd>(...) with git.Git(path).<cmd>(...)
    elif called >= 2 times in one test:
        take repo: Repo; callers open one Repo per test and pass it
    else:
        leave unchanged
remove helpers/imports that became unused
```

## DATA

Helper return values unchanged (`str` from git stdout).

## Tests / checks

Existing tests are the spec; assertions stay unchanged.

- `run_pytest_check(extra_args=["-n", "auto", <each changed test file>])`. For `tests/_reference_at_ref_helpers.py`, run its users (`tests/test_reference_reads_at_ref.py`, `tests/test_reference_search_at_ref.py`).
- `run_ruff_check`, `run_vulture_check`, `run_pylint_check`, `run_mypy_check`, `run_format_code`.
- `.scratch/` must not exist at commit time.

## Commit

`test: run git via git.Git in helpers instead of opening Repo per call`
