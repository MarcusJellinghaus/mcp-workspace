# Step 5 — `get_working_tree_status`

## LLM prompt
Read `pr_info/steps/summary.md` (sections 1–3) and this file. Implement step 5 only, tests
first: create `porcelain_parsers.py` with `parse_status_z`, then `get_working_tree_status`.
Leave `get_full_status`, `is_working_directory_clean` and the old helpers untouched. Run the
checks from the summary, format, commit as one commit.

## WHERE
- `src/mcp_workspace/git_operations/porcelain_parsers.py` (new)
- `src/mcp_workspace/git_operations/core.py` (add `StatusResult`)
- `src/mcp_workspace/git_operations/repository_status.py` (add function)
- `src/mcp_workspace/git_operations/__init__.py` (export function + `StatusResult`; count +2)
- `tests/git_operations/test_porcelain_parsers.py` (new), `test_working_tree_status.py` (new)
- `vulture_whitelist.py`

## WHAT
```python
# porcelain_parsers.py
class StatusEntry(NamedTuple):
    index: str       # X
    worktree: str    # Y
    path: str
    orig_path: Optional[str]   # rename/copy source

def parse_status_z(output: bytes) -> list[StatusEntry]: ...

# core.py
class StatusResult(GitResult):
    clean: bool
    staged: list[str]
    modified: list[str]
    untracked: list[str]

# repository_status.py
def get_working_tree_status(project_dir: Path) -> StatusResult: ...
```

## HOW
- One call: `status --porcelain=v1 -z -uall`.
- Any failure (non-repo, nonzero exit) → `success=False`, `clean=False`, empty lists. Never
  `clean=True` on failure.

## ALGORITHM
```
parse_status_z: fields = output.split(b"\0"); i = 0
  while i < len(fields): f = fields[i]; if not f: i += 1; continue
    x, y, path = chr(f[0]), chr(f[1]), f[3:].decode("utf-8", "replace")
    orig = None; if x in "RC": orig = fields[i+1].decode(...); i += 1
    append StatusEntry(x, y, path, orig); i += 1
get_working_tree_status: "??" -> untracked; else x not in " ?!" -> staged; y not in " ?!" -> modified
  clean = not (staged or modified or untracked)
```

## DATA
`StatusResult`, paths repo-relative with `/`.

## Tests
- Parsers (bytes only): modified, added, deleted, untracked, rename with orig path, non-ASCII
  path, empty output → `[]`.
- Real repo: clean repo → `clean=True`; staged + modified + untracked buckets; non-ASCII file
  name; untracked file inside a new directory listed individually (`-uall`).
- Corrupt index (overwrite `.git/index` with garbage bytes) → `success=False`, `clean=False`.
- Non-repo → `success=False`, `clean=False`.

## vulture
`_.clean`, `_.staged`, `_.modified`, `_.untracked`, `_.orig_path` (as reported).
