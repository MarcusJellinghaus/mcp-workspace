# Step 15 — `get_conflict_blob_info` + `read_conflict_stage`

## LLM prompt
Read `pr_info/steps/summary.md` (sections 1, 2, 7) and this file. Implement step 15 only,
tests first, in `conflicts.py`. Both functions share the binary check and blob reading, so
they are one step. Run the checks from the summary, format, commit as one commit.

## WHERE
- `src/mcp_workspace/git_operations/core.py` (add 3 types)
- `src/mcp_workspace/git_operations/conflicts.py`
- `src/mcp_workspace/git_operations/__init__.py` (2 functions + `ConflictBlobEntry`,
  `ConflictBlobInfoResult`, `ConflictStageResult`; count +5)
- `tests/git_operations/test_conflicts.py` (split into `test_conflict_blobs.py` if near 750 lines)
- `vulture_whitelist.py`

## WHAT
```python
class ConflictBlobEntry(TypedDict):
    path: str
    stages: list[int]      # subset of 1, 2, 3, ascending
    is_binary: bool

class ConflictBlobInfoResult(GitResult):
    entries: list[ConflictBlobEntry]

class ConflictStageResult(GitResult):
    content: Optional[str]
    is_binary: bool

def _is_binary(data: bytes) -> bool:            # b"\0" in data[:8000]
def _read_blob(repo: Repo, sha: str) -> tuple[int, bytes, str]:
    """run_git_raw(repo, "cat_file", "blob", sha, strip_newline=False)"""
def get_conflict_blob_info(project_dir: Path) -> ConflictBlobInfoResult: ...
def read_conflict_stage(project_dir: Path, stage: int, path: str) -> ConflictStageResult: ...
```

## HOW
- Both are `GitResult` functions: non-repo or any git failure → `success=False`.
- `read_conflict_stage` validates `stage in {1, 2, 3}` (else error result, no git call);
  finds the sha via `ls-files -u -z -- <path>` (`literal_paths=True`), never `show :n:path`
  and never `git_show` (truncation / "No output.").
- One `cat-file blob <sha>` per blob; content keeps its trailing newline
  (`strip_newline=False`); decoded with `errors="replace"`.

## ALGORITHM
```
get_conflict_blob_info: entries = parse_ls_files_u_z(ls-files -u -z); group by path
  for path in sorted(groups): binary = any(_is_binary(_read_blob(sha)) for each stage)
  -> ConflictBlobEntry(path, sorted stages, binary); any failing git call -> success=False
read_conflict_stage: match = entry with entry.path == path and entry.stage == stage
  no match -> success=True, content=None, is_binary=False   (absent side)
  rc, data, err = _read_blob(match.sha); rc != 0 -> success=False
  _is_binary(data) -> success=True, content=None, is_binary=True
  else -> success=True, content=data.decode("utf-8", "replace"), is_binary=False
```

## DATA
See WHAT. The three `read_conflict_stage` outcomes are distinguishable:
absent `(True, None, False)`, binary `(True, None, True)`, failure `success=False`.

## Tests (real repos via `make_conflict_repo`)
- Text conflict: entry `stages=[1, 2, 3]`, `is_binary=False`; stage 2 and 3 contents equal the
  `main` and `feature` versions respectively (rebase: 2 = upstream, 3 = replayed commit).
- File with 150 lines and trailing newline → content returned byte-for-byte.
- Non-ASCII file name and non-ASCII content round-trip.
- Delete/modify conflict (feature deletes, main modifies): stage 3 absent → `content=None`,
  `success=True`, `is_binary=False`; entry `stages=[1, 2]`.
- Binary conflict (content containing `b"\0"`): entry `is_binary=True`;
  `read_conflict_stage` → `is_binary=True`, `content=None`.
- `stage=4` → `success=False`. Mocked `cat_file` failure (`run_git_raw` patched for that
  call) → `success=False`. Non-repo → `success=False` for both functions.
- Entries sorted by path.

## vulture
`_.entries`, `_.stages`, `_.is_binary`, `_.content`.
