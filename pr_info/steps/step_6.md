# Step 6 — Staging: `list_untracked_paths`, `stage_paths`

## LLM prompt

> Read `pr_info/steps/summary.md` ("KISS decisions", `git_commit(paths)` bullet) and this file.
> Implement step 6 only: tests first, then the two functions in `staging.py`. Run format,
> pylint, pytest (`-n auto`), mypy, lint-imports and ruff; all must pass. Make exactly one commit.

## WHERE

- `src/mcp_workspace/git_operations/staging.py`
- New tests: `tests/git_operations/test_stage_paths.py`

Not exported from `__init__.py`; `stage_specific_files` stays unchanged.

## WHAT

```python
def list_untracked_paths(paths: list[Path], project_dir: Path) -> list[str]: ...
def stage_paths(paths: list[Path], project_dir: Path) -> GitResult: ...
```

## HOW

- `list_untracked_paths`: `to_git_paths(paths, project_dir)` then
  `run_git_raw(repo, "ls_files", "--others", "--exclude-standard", "-z", "--", *rel, literal_paths=True)`.
  Recurses into directories, excludes ignored files. Returns repo-relative forward-slash paths.
  On any failure (non-repo, path outside, git error) returns `[]` — `commit_paths` then reports
  the untracked path itself, so nothing is lost.
- `stage_paths`: `_run_chunked(paths, project_dir, "stage_paths", "add", ("add", "--"))`,
  same contract as `unstage_paths` / `renormalize_paths` (empty list → success, no git call).

## ALGORITHM

```
list_untracked_paths:
    if not paths: []
    rel = to_git_paths(...)              # ValueError -> []
    rc, out, _ = run_git_raw(... ls_files ...); rc != 0 -> []
    return [p for p in out.decode("utf-8", "replace").split("\0") if p]
stage_paths: return _run_chunked(...)
```

## DATA

`list[str]` of untracked files; `GitResult` for staging.

## Tests (write first)

Integration (`git_integration`, temp repo):
- untracked file listed; tracked-modified file not listed.
- directory argument → its untracked files listed (nested ones too), tracked ones not.
- gitignored file under the directory → not listed.
- path with `*` in its name is matched literally.
- path outside the repo → `[]`.
- `stage_paths` stages a new file (shows as `A` in `git status --porcelain`); empty list → success
  with `returncode is None`.

## Commit

`feat(git_operations): add list_untracked_paths and stage_paths`
