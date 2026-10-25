# Step 16 — `resolve_take_theirs_or_remove`

## LLM prompt
Read `pr_info/steps/summary.md` and this file. Implement step 16 only, tests first, in
`conflicts.py`. Run the checks from the summary, format, commit as one commit.

## WHERE
- `src/mcp_workspace/git_operations/conflicts.py`
- `src/mcp_workspace/git_operations/__init__.py` (export; count +1)
- `tests/git_operations/test_conflicts.py` (or a new `test_conflict_resolve.py` if near 750 lines)

## WHAT
```python
def resolve_take_theirs_or_remove(project_dir: Path, path: str) -> GitResult:
    """Take the feature side (stage 3) and stage it; remove the path if stage 3 is absent."""
```

## HOW
- Decision from the `ls-files -u -z -- <path>` listing, never by catching a failed checkout.
- All calls `literal_paths=True`, `--` before the path. Not `stage_specific_files`
  (`repo.index.add`, requires the file to exist).
- No unmerged entries for `path` → error result ("path is not unmerged").
- Docstring: during a rebase "theirs" (stage 3) is the commit being replayed, i.e. the
  feature branch.

## ALGORITHM
```
open repo (non-repo -> error); rc, out, err = ls-files -u -z -- path; rc != 0 -> error
stages = {e.stage for e in parse_ls_files_u_z(out) if e.path == path}; empty -> error
if 3 in stages: run checkout --theirs -- path; then add -- path
else: run rm -q -- path
first nonzero rc -> error result with rc/err; else success
```

## DATA
`GitResult`.

## Tests (real repos via `make_conflict_repo`)
- Text conflict → file content equals the feature version, path no longer unmerged, staged.
- Delete/modify (feature deleted the file) → file removed from index and disk.
- Path with `[` in the name, conflicted alongside a matching non-literal name → only the
  literal path resolved.
- Non-conflicted path → `success=False`. Non-repo → `success=False`.
