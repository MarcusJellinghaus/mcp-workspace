# Step 4 — Guardrail queries

## LLM prompt

> Read `pr_info/steps/summary.md` (design point 5) and this file. Implement step 4 only:
> tests first, then the five read-only query functions. Run format, pylint, pytest
> (`-n auto`), mypy, lint-imports and ruff; all must pass. Make exactly one commit.

## WHERE

- `src/mcp_workspace/git_operations/branch_queries.py`: `is_valid_branch_name_strict`,
  `resolve_base_ref`, `resolve_commit`, `is_ancestor`.
- `src/mcp_workspace/git_operations/rebase.py`: `operation_in_progress` (next to `is_rebase_in_progress`).
- New tests: `tests/git_operations/test_guard_queries.py`

None of them is exported from `__init__.py`; `validate_branch_name` stays unchanged.

## WHAT

```python
def is_valid_branch_name_strict(project_dir: Path, name: str) -> bool: ...
def resolve_base_ref(project_dir: Path, base: str) -> str | None: ...
def resolve_commit(project_dir: Path, ref: str) -> str | None: ...          # full SHA
def is_ancestor(project_dir: Path, ancestor: str, descendant: str) -> bool | None: ...
def operation_in_progress(project_dir: Path) -> Literal["rebase", "merge"] | None: ...
```

## HOW

- All git calls through `run_git_raw(repo, ..., env=GIT_NONINTERACTIVE_ENV)` inside
  `open_repo_for_query(project_dir)` (raises `ValueError` for a non-repository — documented).
- `operation_in_progress` reuses `_rebase_dir_exists(repo)` and checks
  `Path(repo.git_dir) / "MERGE_HEAD"`.

## ALGORITHM

```
is_valid_branch_name_strict:
    if not name or name == "HEAD" or is_option_like(name): False
    rc, out, _ = run_git_raw(repo, "check_ref_format", "--branch", name)
    return rc == 0 and out.decode().strip() == name      # rejects @{-1}, which git expands
resolve_base_ref:
    if not is_valid_branch_name_strict(base): None
    ref = f"refs/remotes/{base}" if base.startswith("origin/") else f"refs/heads/{base}"
    rc = run_git_raw(repo, "show_ref", "--verify", "--quiet", ref); return ref if rc == 0 else None
resolve_commit: if is_option_like(ref): None; rev_parse --verify -q f"{ref}^{{commit}}" -> sha or None
is_ancestor: if either is option-like: None
    rc = merge_base --is-ancestor a d; 0 -> True, 1 -> False, else None (missing object)
operation_in_progress: "rebase" if _rebase_dir_exists else "merge" if MERGE_HEAD exists else None
```

## DATA

Plain values as in the signatures. `is_ancestor` → `None` means "could not decide" (an object
is missing locally), which the delete tool turns into "fetch first".

## Tests (write first)

Integration (`git_integration`, real temp repos):
- strict validator: accepts `feature/x`, `220-foo`; rejects `""`, `HEAD`, `-x`, `a..b`,
  `x.lock`, `a@{b`, `@{-1}` (after switching branches once), `a b`, `x~1`.
- `resolve_base_ref`: `main` → `refs/heads/main`; `origin/main` → `refs/remotes/origin/main`;
  a tag `v1` → None; a local branch literally named `origin/x` with no remote `origin/x` → None;
  unknown → None.
- `resolve_commit("HEAD")` → 40-char SHA; unknown → None.
- `is_ancestor`: parent/child → True; reversed → False; unknown 40-char SHA → None.
- `operation_in_progress`: clean → None; stopped rebase on a conflict → `"rebase"`;
  merge stopped on a conflict → `"merge"`.

Unit: `operation_in_progress` on a non-repository raises `ValueError`.

## Commit

`feat(git_operations): add guardrail queries for git write tools`
