# Step 3 — `is_staged_diff_cr_only`

## LLM prompt

> Read `pr_info/steps/summary.md` and issue #373 (section "`is_staged_diff_cr_only`"), then
> implement `pr_info/steps/step_3.md`. Write the tests first, then the function. Run format,
> pylint, pytest (`-n auto`), mypy and lint-imports. All must pass. Then make one commit.

## WHERE

- `tests/git_operations/test_is_staged_diff_cr_only.py` (new)
- `src/mcp_workspace/git_operations/repository_status.py`: new function directly after
  `has_staged_changes`
- `src/mcp_workspace/git_operations/__init__.py`: export
- `tests/git_operations/test_init_exports.py`: count 69 → 70
- `docs/release-notes.md`: add a line to the #373 section from step 2

## WHAT

```python
def is_staged_diff_cr_only(paths: list[Path], project_dir: Path) -> bool: ...
```

## HOW

- `repository_status.py`: add `_chunk_paths` and `to_git_paths` to the existing
  `from .core import (...)` list. Do not import from `staging` (that would be circular).
- `__init__.py`: add `is_staged_diff_cr_only` to the `repository_status` import and to `__all__`
  in alphabetical order (after `"is_rebase_in_progress"`).

## ALGORITHM

```
try: with safe_repo_context(project_dir) as repo:
    if not paths: return True
    for chunk in _chunk_paths(to_git_paths(paths, project_dir)):
        rc, _, err = run_git_raw(repo, "diff", "--cached", "--ignore-cr-at-eol", "--quiet", "--", *chunk, literal_paths=True)
        if rc != 0: log (rc, err); return False
    return True
except Exception as e:  # pylint: disable=broad-exception-caught  # fail closed
    log; return False
```

The docstring states (from the issue):

- Only `paths` are inspected, and other staged entries are not checked. Nothing staged → `True`.
  Callers use `has_staged_changes` to decide whether to commit.
- Paths are not validated: a deleted or never-existed path gives an empty staged diff → `True`,
  so the caller relies on `renormalize_paths` failing first.
- Any failure (exit 1, another exit code, non-repo, path outside the project, an exception) →
  `False`. Empty `paths` → `True` without running git (after the repo is opened).

## DATA

`bool`.

## Tests — `test_is_staged_diff_cr_only.py`

Mark the class `@pytest.mark.git_integration`. Use the `crlf_repo` fixture from step 2 and
import `renormalize_paths` from `staging` for the setup.

| Test | Setup | Assert |
|---|---|---|
| CRLF-only | renormalize `doc.md` | `True` |
| content change | write `b"line one\r\n    indented\r\nnew line\r\n"`, renormalize | `False` |
| indentation-only | write `b"line one\r\n  indented\r\n"`, renormalize | `False` (guards against `-w`) |
| empty in repo | `repo.git.add(".gitattributes")` (a real staged change) | `is_staged_diff_cr_only([], dir)` is `True` (a call without a pathspec would see it → `False`) |
| non-repo (parametrized `[]`, `[Path("a.md")]`) | plain `tmp_path / "plain"` dir | `False` |
| path outside project | `crlf_repo`; `tmp_path / "outside.md"` | `False` |

If the CRLF-only test returns `False` because git's `--quiet` ignores `--ignore-cr-at-eol` (check
by hand that `doc.md` is staged and differs only in CR), write one line to
`pr_info/.blocked.txt` and stop.

## Release notes

Add to `### New functions` in the #373 section:

- `is_staged_diff_cr_only(paths: list[Path], project_dir) -> bool` — staged diff of `paths` is CR-at-EOL only; any error → `False`.

## Commit

`feat(git_operations): add is_staged_diff_cr_only`
