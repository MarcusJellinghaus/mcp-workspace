# Step 3 — `commit_paths`

## LLM prompt
Read `pr_info/steps/summary.md` (especially section 7) and this file. Implement step 3 only
(`commit_paths`), tests first. Run the checks from the summary, format, commit as one commit.

## WHERE
- `src/mcp_workspace/git_operations/commits.py` (add `commit_paths`, extract classifier)
- `src/mcp_workspace/git_operations/__init__.py` (export; count +1)
- `tests/git_operations/test_commit_paths.py` (new)

## WHAT
```python
def _classify_commit_failure(stderr: str) -> Literal["signing_failed", "commit_failed"]:
    """Shared with commit_staged_files (uses the existing _SIGNING_KEYWORDS)."""

def commit_paths(message: str, paths: list[Path], project_dir: Path) -> CommitResult:
    """Path-limited (--only) commit of the working-tree content of `paths`."""
```

## HOW
- Refactor `commit_staged_files` to call `_classify_commit_failure(str(e.stderr or ""))`;
  behaviour unchanged.
- `commit_paths` does not use `get_staged_changes` or the "no staged files" precheck.
- Paths via `to_git_paths` (absolute or relative to `project_dir`); `--` before paths;
  `literal_paths=True`; no chunking.
- The precheck only needs the two-character status codes, so it splits the `-z` output
  inline (the full `parse_status_z` arrives in step 5 and need not replace this): split on
  `b"\0"`, ignore empty fields, skip the extra source field after an `R`/`C` entry, collect
  the `XY` codes.
- Commit hash via `run_git_raw(repo, "rev_parse", "HEAD")`, first `GIT_SHORT_HASH_LENGTH`
  chars. No `repo.head.commit`.
- Docstring states: an empty precheck means `nothing_to_commit`, which includes a path that
  is neither tracked nor on disk.

## ALGORITHM
```
empty/whitespace message or empty paths -> validation_failed
open repo (non-repo -> validation_failed); rel = to_git_paths(...) (ValueError -> validation_failed)
rc, out, err = run_git_raw(repo, "status", "--porcelain", "-z", "--", *rel, literal_paths=True)
rc != 0 -> commit_failed; codes = XY codes split from out
"??" in codes -> validation_failed (untracked path); no codes -> nothing_to_commit
rc, _, err = run_git_raw(repo, "commit", "--only", "-m", msg.strip(), "--", *rel, literal_paths=True)
rc != 0 -> _classify_commit_failure(err); else success with short hash
```

## DATA
`CommitResult`; `nothing_to_commit` → `success=False`,
`error="Nothing to commit for the given paths"`, `error_category="nothing_to_commit"`.

## Tests
- Modified tracked file committed; other modified and staged files stay uncommitted.
- Unmodified tracked path → `nothing_to_commit`.
- Untracked path → `validation_failed`. Path outside `project_dir` → `validation_failed`.
- Non-ASCII file name and non-ASCII commit message round-trip (`log -1 --format=%s`).
- File named `a[1].txt` committed while `a1.txt` is also modified and stays uncommitted.
- Magic pathspec `":(glob)*.txt"` (no such file) with `a.txt` modified → `nothing_to_commit`,
  `a.txt` stays uncommitted.
- Unborn HEAD: staged new file (`git add`) committed via `commit_paths` → success.
  If git refuses a partial commit on an unborn HEAD, write one line to
  `pr_info/.blocked.txt` and stop.
- Signing failure classification via mocked `run_git_raw` returning stderr with "gpg".
