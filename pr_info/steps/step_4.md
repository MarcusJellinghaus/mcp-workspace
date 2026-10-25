# Step 4 — `unstage_paths`

## LLM prompt
Read `pr_info/steps/summary.md` and this file. Implement step 4 only (`unstage_paths`),
tests first. Run the checks from the summary, format, commit as one commit.

## WHERE
- `src/mcp_workspace/git_operations/staging.py` (add `unstage_paths`)
- `src/mcp_workspace/git_operations/__init__.py` (export; count +1)
- `tests/git_operations/test_unstage_paths.py` (new)

## WHAT
```python
def unstage_paths(paths: list[Path], project_dir: Path) -> GitResult:
    """Unstage paths; works on an unborn HEAD. Idempotent, chunked for Windows."""
```

## HOW
- Paths via `to_git_paths`; outside `project_dir` → error result (`returncode=None`).
- Empty `paths` → success, no git call.
- Reuse `_chunk_paths` (same module) for the Windows command-line limit.
- `literal_paths=True`, `--` before paths.

## ALGORITHM
```
open repo (non-repo -> error); rel = to_git_paths(...)
head_rc, _, _ = run_git_raw(repo, "rev_parse", "--verify", "-q", "HEAD")
for chunk in _chunk_paths(rel):
    args = ("reset", "-q", "HEAD", "--", *chunk) if head_rc == 0
           else ("rm", "--cached", "-r", "-q", "--ignore-unmatch", "--", *chunk)
    rc, _, err = run_git_raw(repo, *args, literal_paths=True); rc != 0 -> error result
return success
```

## DATA
`GitResult`.

## Tests
- Staged modification is unstaged; working-tree content kept.
- Unborn HEAD: staged new file becomes untracked; file still on disk.
- Calling twice is a success (idempotent).
- Path `x*.txt` literal: only that file is unstaged, `xa.txt` stays staged.
- Magic pathspec `":(glob)*.txt"` (no such file) → success, staged `a.txt` stays staged.
- Outside path → `success=False`. Non-repo → `success=False`.
- Chunking: patch `_chunk_paths` to force one path per chunk with two paths → both unstaged.
