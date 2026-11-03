# Step 2 — `renormalize_paths`

## LLM prompt

> Read `pr_info/steps/summary.md` and issue #373 (section "`renormalize_paths`"), then implement
> `pr_info/steps/step_2.md`. Write the tests first, then the function. Run format, pylint,
> pytest (`-n auto`), mypy and lint-imports. All must pass. Then make one commit.

## WHERE

- `tests/git_operations/conftest.py`: new fixture `crlf_repo`
- `tests/git_operations/test_renormalize_paths.py` (new)
- `src/mcp_workspace/git_operations/staging.py`: new function after `unstage_paths`
- `src/mcp_workspace/git_operations/__init__.py`: export
- `tests/git_operations/test_init_exports.py`: count 68 → 69
- `docs/release-notes.md`: new top section

## WHAT

```python
# conftest.py
@pytest.fixture
def crlf_repo(git_repo: tuple[Repo, Path]) -> tuple[Repo, Path]: ...

# staging.py
def renormalize_paths(paths: list[Path], project_dir: Path) -> GitResult: ...
```

## HOW

- `crlf_repo` steps:
  1. Call `repo.git.config("core.autocrlf", "false")` (as `make_conflict_repo` does).
  2. Run `commit_files(repo, {"doc.md": b"line one\r\n    indented\r\n"}, "crlf")`. This must
     happen before `.gitattributes` exists.
  3. Write `.gitattributes` = `"*.md text\n"` and leave it untracked.
  4. Rewrite `doc.md` with the same bytes. Return `(repo, project_dir)`.
- `staging.py`: no new imports needed (`_chunk_paths`, `to_git_paths`, `run_git_raw`,
  `safe_repo_context` and `GitResult` are imported already).
- `__init__.py`: change the import to
  `from mcp_workspace.git_operations.staging import (renormalize_paths, stage_all_changes, unstage_paths)`
  and add `"renormalize_paths"` to `__all__` in alphabetical order (after `"reset_hard"`).

## ALGORITHM

```
try: with safe_repo_context(project_dir) as repo:
    if not paths: return success (returncode/stderr None)
    try rel = to_git_paths(paths, project_dir) except ValueError -> error result, rc/stderr None
    for chunk in _chunk_paths(rel):
        rc, _, err = run_git_raw(repo, "add", "--renormalize", "--", *chunk, literal_paths=True)
        if rc != 0: log; return {success False, error "git add --renormalize failed (exit rc)", rc, err}
except (InvalidGitRepositoryError, NoSuchPathError): return "Not a git repository" result
return {success True, error None, returncode rc, stderr err}
```

The docstring states (from the issue):

- `--renormalize` implies `-u`, so files with real edits are staged too. That is what lets the
  check detect them. Undo with `unstage_paths`.
- There is no existence pre-check:
  - A deleted tracked path or a never-existed path → exit 128, and nothing in that chunk is staged.
  - An untracked path or stat-only dirt → exit 0, nothing staged.
- Empty `paths` is a success without running git. A non-repo or a path outside `project_dir` →
  `success=False` with `returncode`/`stderr` None. A failing chunk leaves earlier chunks staged.

## DATA

A `GitResult` dict with `success`, `error`, `returncode` and `stderr`.

## Tests — `test_renormalize_paths.py`

Mark the class `@pytest.mark.git_integration`. Read status via `get_working_tree_status`.

| Test | Setup | Assert |
|---|---|---|
| CRLF-only | `crlf_repo`; renormalize `[Path("doc.md")]` | `success`; `"doc.md"` in `staged`, not in `modified` |
| deleted tracked path | `crlf_repo`; unlink `doc.md` | `success False`, `returncode == 128`, `stderr` non-empty |
| untracked path | `crlf_repo`; create `new.md` | `success`; `staged == []`; `"new.md"` in `untracked` |
| empty in repo | `crlf_repo`; renormalize `[]` | `success`; `staged == []` (a call without a pathspec would have staged `doc.md`) |
| non-repo (parametrized `[]`, `[Path("a.md")]`) | plain `tmp_path / "plain"` dir | `success False`, `returncode is None`, `stderr is None` |
| path outside project | `crlf_repo`; `tmp_path / "outside.md"` | `success False`, `returncode is None` |

If the deleted-path test shows git exiting with a code other than 128, write one line to
`pr_info/.blocked.txt` and stop.

## Release notes

Add a top section `## Next minor release — git_operations: line-ending-only dirt helpers (#373)`
to `docs/release-notes.md`. Give it a one-sentence summary and a `### New functions` list with:

- `renormalize_paths(paths: list[Path], project_dir) -> GitResult` — `git add --renormalize`; deleted or missing path → `success=False` (exit 128).

## Commit

`feat(git_operations): add renormalize_paths`
