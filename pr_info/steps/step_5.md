# Step 5 — Fewer `Repo` objects in test helpers (task 3, decision 4)

## LLM prompt

Read `pr_info/steps/summary.md`, then implement this step (`pr_info/steps/step_5.md`) only. Change test helpers that open `Repo(path)` only to run a git command so they use `git.Git(path)` instead. Start with `test_ref_snapshot._git`, then the candidate list below. Apply decision 4 where reading the code shows a cheap config fix. Run only the changed test files, then ruff, vulture, pylint and mypy, and produce exactly one commit.

## WHERE

Primary:
- `tests/git_operations/test_ref_snapshot.py`: `_git` (line ~43), `_repo` (line ~34)

Candidate helpers (module-level functions that open `Repo(path)`). Convert only those whose `Repo` is used **solely** for `repo.git.<cmd>(...)`:
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

Other converted helpers keep their signature and return type.

## HOW

- `Repo(p).git.<cmd>(*a)` → `git.Git(p).<cmd>(*a)`: same git process and same `str` output, but no `Repo` object (so no `gc.collect()`).
- **Do not convert** helpers that use the object model (`.branches`, `.active_branch`, `.head.commit`, `.untracked_files`, `.index`, `config_writer()`). Those read files without starting git, and converting them to git commands would add a process. Where one test calls such helpers repeatedly, passing in one `Repo` opened per test is allowed, but not required.
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
