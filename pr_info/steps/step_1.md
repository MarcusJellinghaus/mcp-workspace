# Step 1 — Foundations: `GitResult`, `CommitResult` extension, env, runner, helpers

## LLM prompt
Read `pr_info/steps/summary.md` (sections 1, 2 and "Every step") and this file. Implement
step 1 only, tests first. Do not add any public git operation yet. Run the checks listed in
the summary, then format and commit as one commit.

## WHERE
- `src/mcp_workspace/git_operations/core.py` (modify)
- `src/mcp_workspace/git_operations/commits.py`, `workflows.py` (modify return sites)
- `src/mcp_workspace/git_operations/base_branch.py` (use the new env constant)
- `src/mcp_workspace/git_operations/__init__.py` (export `GitResult`)
- `tests/git_operations/test_core_runner.py` (new)
- `tests/git_operations/test_init_exports.py` (count +1), `vulture_whitelist.py`

## WHAT
```python
class GitResult(TypedDict):
    success: bool
    error: Optional[str]
    returncode: Optional[int]
    stderr: Optional[str]

class CommitResult(GitResult):
    commit_hash: Optional[str]
    error_category: Optional[Literal["signing_failed", "commit_failed",
                                     "validation_failed", "nothing_to_commit"]]

GIT_NONINTERACTIVE_ENV: dict[str, str] = {"GIT_TERMINAL_PROMPT": "0", "GIT_EDITOR": "true"}

def run_git_raw(repo: Repo, command: str, *args: str,
                env: Optional[dict[str, str]] = None,
                literal_paths: bool = False,
                strip_newline: bool = True) -> tuple[int, bytes, str]: ...
def is_option_like(value: str) -> bool: ...
def to_git_paths(paths: Sequence[Path], project_dir: Path) -> list[str]: ...
@contextmanager
def open_repo_for_query(project_dir: Path) -> Iterator[Repo]: ...
```

## HOW
- `CommitResult` keeps its name and location; `GitResult` is defined just above it.
- Every existing `CommitResult` literal (`commits.py::commit_staged_files`,
  `workflows.py::commit_all_changes`) gains `"returncode"` and `"stderr"`: `None` when no git
  process ran; in the `except GitCommandError` branch of `commit_staged_files` use
  `e.status` and `str(e.stderr or "")`. mypy flags every site you miss.
- `base_branch.py`: delete `_LS_REMOTE_ENV`, import `GIT_NONINTERACTIVE_ENV` from `.core`
  and pass it as `env=` in `origin_has_branch`.
- Before writing `run_git_raw`, write a scratch probe (`.scratch/test_probe.py`, see
  CLAUDE.md "Scratch probes") that calls `repo.git.status(with_extended_output=True,
  with_exceptions=False, stdout_as_string=False)` in a failing situation and asserts the type
  of the returned stderr. Normalise both `bytes` and `str` in the runner either way. Delete
  `.scratch/` afterwards.

## ALGORITHM
```
run_git_raw:
  call_env = dict(env or {}); if literal_paths: call_env["GIT_LITERAL_PATHSPECS"] = "1"
  status, out, err = getattr(repo.git, command)(*args, with_extended_output=True,
      with_exceptions=False, stdout_as_string=False,
      strip_newline_in_stdout=strip_newline, env=call_env or None)
  err_text = err.decode("utf-8", "replace") if isinstance(err, bytes) else str(err)
  return int(status), out (bytes, b"" if None), err_text
to_git_paths: for p: abs = p if p.is_absolute() else project_dir / p
  -> _normalize_git_path(abs.resolve(), project_dir.resolve()); ValueError if outside
open_repo_for_query: with safe_repo_context(...) as repo: yield repo;
  except (InvalidGitRepositoryError, NoSuchPathError) -> raise ValueError(...) from None
```

## DATA
- `run_git_raw` → `(returncode, stdout_bytes, stderr_text)`.
- `is_option_like("-x") is True`, `is_option_like("main") is False`.

## Tests (`test_core_runner.py`, real repos via existing fixtures)
- Nonzero exit returned, not raised (e.g. `rev_parse --verify nope`); stderr is `str`.
- Non-ASCII file name round-trips through `ls_files -z` as UTF-8 bytes.
- `strip_newline=False` keeps the trailing `\n` of a blob read with `cat_file blob <sha>`;
  default strips it.
- `env=GIT_NONINTERACTIVE_ENV`: `run_git_raw(repo, "var", "GIT_EDITOR", env=...)` → `b"true"`.
- `literal_paths=True`: `ls_files -- "*.txt"` with a file literally named `*.txt` and a
  file `a.txt` returns only `*.txt`. Magic pathspec (no real file — Windows forbids `:` in
  file names): with `a.txt` present, `ls_files -- ":(glob)*.txt"` with `literal_paths=True`
  matches nothing.
- `to_git_paths`: relative, absolute, outside (`ValueError`), Windows backslashes → `/`.
- `open_repo_for_query` on a plain dir and on a missing dir → `ValueError`.
- `is_option_like` cases.
- Existing `test_commits.py` assertions still pass; add one asserting
  `result["returncode"] is None` on a validation failure.

## vulture
`_.returncode`, `_.stderr` (if vulture reports them).
