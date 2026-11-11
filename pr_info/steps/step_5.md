# Step 5 — Branch mutations returning `GitResult`

## LLM prompt

> Read `pr_info/steps/summary.md` (design point 5) and this file. Implement step 5 only:
> tests first, then the three functions in `branches.py`. Existing functions in that module
> stay unchanged. Run format, pylint, pytest (`-n auto`), mypy, lint-imports and ruff; all
> must pass. Make exactly one commit.

## WHERE

- `src/mcp_workspace/git_operations/branches.py`
- New tests: `tests/git_operations/test_branch_writes.py`

Not exported from `__init__.py`.

## WHAT

```python
def create_and_switch_branch(
    project_dir: Path, name: str, start_ref: str | None = None, no_track: bool = False
) -> GitResult: ...

def switch_branch(project_dir: Path, name: str) -> GitResult: ...

def delete_local_branch_force(project_dir: Path, name: str) -> GitResult: ...
```

## HOW

- `run_git_raw(repo, ..., env=GIT_NONINTERACTIVE_ENV)` inside `safe_repo_context`; catch
  `InvalidGitRepositoryError` / `NoSuchPathError` → `"Not a git repository: <dir>"` result
  (pattern of `remotes.pull`).
- Option-like `name`/`start_ref` → validation error result without running git
  (`is_option_like` from `.core`). Full name validation is the caller's job (step 4 validator).
- Ref existence via `show_ref --verify --quiet` (same as `resolve_base_ref`).
- A small private `_result(rc, err, error_text)` builder keeps the three functions short.
- Never fetches.

## ALGORITHM

```
create_and_switch_branch:
    args = ["checkout", *(["--no-track"] if no_track else []), "-b", name, *([start_ref] if start_ref else [])]
    rc, _, err = run_git_raw(repo, *args); rc != 0 -> error f"git checkout -b failed (exit {rc})"
switch_branch:
    if refs/heads/<name> exists: run_git_raw(repo, "checkout", name, "--")
    elif refs/remotes/origin/<name> exists: run_git_raw(repo, "checkout", "--track", "-b", name, f"refs/remotes/origin/{name}")
    else -> error f"Branch '{name}' not found locally or as origin/{name}; run git fetch first"
delete_local_branch_force: run_git_raw(repo, "branch", "-D", name)
```

## DATA

`GitResult`; on failure `stderr` carries git's message (e.g. "would be overwritten by checkout").

## Tests (write first)

Integration (`git_integration`, bare origin + clone):
- create from HEAD → on new branch, no upstream.
- create from `refs/heads/main` → on new branch at main's tip.
- create from `refs/remotes/origin/main` with `no_track=True` → no upstream configured.
- create an existing name → `success=False`, stderr mentions "already exists".
- switch to an existing local branch → current branch changes.
- switch to a name only present as `origin/<name>` → local branch created, upstream `origin/<name>`.
- switch to an unknown name → error contains "run git fetch first", no branch created.
- switch blocked by a conflicting dirty file → `success=False`, stderr from git.
- force-delete an unmerged branch → gone; deleting the current branch → `success=False`.

Unit: option-like name → error, no git call (patch `run_git_raw`).

## Commit

`feat(git_operations): add GitResult branch create/switch/delete functions`
