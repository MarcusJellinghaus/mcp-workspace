# Step 18 — `list_tree`

## LLM prompt
Read `pr_info/steps/summary.md` and this file. Implement step 18 only, tests first: add
`parse_ls_tree_z` and `list_tree` in `conflicts.py`. Run the checks from the summary, format,
commit as one commit.

## WHERE
- `src/mcp_workspace/git_operations/porcelain_parsers.py` (add parser)
- `src/mcp_workspace/git_operations/core.py` (add `TreeEntry`, `TreeListing`)
- `src/mcp_workspace/git_operations/conflicts.py`
- `src/mcp_workspace/git_operations/__init__.py` (function + 2 types; count +3)
- `tests/git_operations/test_porcelain_parsers.py`, `tests/git_operations/test_list_tree.py` (new)
- `vulture_whitelist.py`

## WHAT
```python
# core.py
class TreeEntry(TypedDict):
    mode: str
    type: str    # "blob" | "tree" | "commit"
    sha: str
    path: str

class TreeListing(GitResult):
    entries: list[TreeEntry]

# porcelain_parsers.py
def parse_ls_tree_z(output: bytes) -> list[TreeEntry]:
    """'<mode> <type> <sha>\\t<path>\\0'... -> entries."""

# conflicts.py
def list_tree(project_dir: Path, ref: str, path: str) -> TreeListing:
    """Contents of directory `path` at `ref` (ls-tree -z <ref> -- <path>/)."""
```

## HOW
- `ref` empty or starting with `-` → error result, no git call. Non-repo → error result.
- `path` normalised to `path.rstrip("/") + "/"`; `literal_paths=True`; `--` before path.
- Missing path → exit 0, empty output → success with `[]`. Bad ref → nonzero → failure.
- `porcelain_parsers.py` imports `TreeEntry` from `.core` (core must not import the parsers).

## ALGORITHM
```
validate ref; open repo
rc, out, err = run_git_raw(repo, "ls_tree", "-z", ref, "--", path.rstrip("/") + "/", literal_paths=True)
rc != 0 -> success=False, entries=[], error=f"git ls-tree failed (exit {rc})", rc, err
return success=True, entries=parse_ls_tree_z(out)
```

## DATA
`TreeListing`; entry paths are repo-relative (e.g. `pr_info/a.md`).

## Tests
- Parser: blob and tree entries; non-ASCII path; empty → `[]`.
- Ref with `pr_info/a.md`, `pr_info/sub/b.md` → two entries (`blob`, `tree`), `pr_info/`
  contents only (no recursion).
- Read at `main` while `feature` is checked out (the mcp-coder use: `ls-tree origin/<base> pr_info`).
- Missing directory → `success=True`, `entries=[]`. Bad ref → `success=False`.
- `ref="-x"` → `success=False`. Non-repo → `success=False`.

## vulture
`_.mode`, `_.type`, `_.sha`, `_.path` (as reported).
