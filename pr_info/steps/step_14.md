# Step 14 — `list_unmerged_paths`

## LLM prompt
Read `pr_info/steps/summary.md` and this file. Implement step 14 only, tests first: add
`parse_ls_files_u_z` and create `conflicts.py` with `list_unmerged_paths`. Run the checks
from the summary, format, commit as one commit.

## WHERE
- `src/mcp_workspace/git_operations/porcelain_parsers.py` (add parser)
- `src/mcp_workspace/git_operations/conflicts.py` (new)
- `src/mcp_workspace/git_operations/__init__.py` (export; count +1)
- `tests/git_operations/test_porcelain_parsers.py`, `tests/git_operations/test_conflicts.py` (new)

## WHAT
```python
# porcelain_parsers.py
class UnmergedEntry(NamedTuple):
    mode: str
    sha: str
    stage: int
    path: str

def parse_ls_files_u_z(output: bytes) -> list[UnmergedEntry]:
    """'<mode> <sha> <stage>\\t<path>\\0'... -> entries."""

# conflicts.py
def list_unmerged_paths(project_dir: Path) -> list[str]: ...
```

## HOW
- Plain-value query: `open_repo_for_query` (non-repo → `ValueError`); nonzero exit →
  `raise GitCommandError(["git", "ls-files", "-u", "-z"], rc, err)`.
- No truncation; deduplicated in order of first appearance.

## ALGORITHM
```
parse: for field in output.split(b"\0") if field:
  meta, path = field.split(b"\t", 1); mode, sha, stage = meta.split(b" ")
  -> UnmergedEntry(mode, sha, int(stage), path.decode("utf-8", "replace"))
list_unmerged_paths: rc, out, err = run_git_raw(repo, "ls_files", "-u", "-z")
  rc != 0 -> raise; return list(dict.fromkeys(e.path for e in parse(out)))
```

## DATA
`list[str]`, repo-relative with `/`.

## Tests
- Parser: three stages of one path; two paths; non-ASCII path; empty → `[]`.
- No conflict → `[]`.
- Text conflict on two files (one non-ASCII name) → both, once each, in git's order.
- Non-repo → `ValueError`. Mocked `run_git_raw` returning `(128, b"", "fatal")` →
  `GitCommandError`.
