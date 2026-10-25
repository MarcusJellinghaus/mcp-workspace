# Step 6 — `probe_rebase_conflicts` (+ conflict-repo test builder)

## LLM prompt
Read `pr_info/steps/summary.md` (sections 1–5) and this file. Implement step 6 only, tests
first: the conftest builder, `parse_merge_tree_z`, and `probe_rebase_conflicts` in the new
`rebase.py`. Run the checks from the summary, format, commit as one commit.

## Precondition
Run `git --version` via a scratch probe (or `run_git_raw(repo, "version")`). If it is below
2.38, the real-repo merge-tree tests cannot run: write one line to `pr_info/.blocked.txt`
and stop.

## WHERE
- `tests/git_operations/conftest.py` (add `commit_files`, `make_conflict_repo`)
- `src/mcp_workspace/git_operations/porcelain_parsers.py` (add `parse_merge_tree_z`)
- `src/mcp_workspace/git_operations/core.py` (add `RebaseProbe`)
- `src/mcp_workspace/git_operations/rebase.py` (new)
- `src/mcp_workspace/git_operations/__init__.py` (export function + `RebaseProbe`; count +2)
- `tests/git_operations/test_porcelain_parsers.py`, `tests/git_operations/test_rebase_probe.py` (new)
- `vulture_whitelist.py`

## WHAT
```python
# conftest.py
def commit_files(repo: Repo, files: dict[str, str | bytes | None], message: str) -> str:
    """Write (None = delete) files, `git add -A`, `git commit`; return the full sha."""

@pytest.fixture
def make_conflict_repo(git_repo) -> Callable[[dict, dict, dict], tuple[Repo, Path]]:
    """build(base, main_change, feature_change): commit base on 'main', commit main_change
    on 'main', commit feature_change on 'feature' (from base); leave 'feature' checked out."""

# porcelain_parsers.py
def parse_merge_tree_z(output: bytes) -> tuple[Optional[str], list[str]]:
    """'<tree>\\0<path>\\0...' -> (tree_oid or None if empty, paths)."""

# core.py
class RebaseProbe(GitResult):
    status: Literal["conflict", "clean", "unsupported", "error"]
    files: list[str]

# rebase.py
def _git_version(repo: Repo) -> tuple[int, int]: ...   # from repo.git.version()
def probe_rebase_conflicts(project_dir: Path, base_ref: str) -> RebaseProbe: ...
```

## HOW
- Builder sets `core.autocrlf=false` and uses `repo.git.*` (not `repo.index`); branch names
  `main` / `feature` via `branch -M main`. Later steps reuse it for every conflict scenario.
- `_git_version` parses `"git version 2.43.0.windows.1"` → `(2, 43)`; tests patch
  `mcp_workspace.git_operations.rebase._git_version`.
- `base_ref` starting with `-` → `status="error"` result, no git call.

## ALGORITHM
```
rc, out, err = run_git_raw(repo, "merge_tree", "--write-tree", "--name-only",
                           "--no-messages", "-z", base_ref, "HEAD")
rc == 0 -> clean (success=True, files=[])
rc == 1: tree, files = parse_merge_tree_z(out)
         tree -> conflict (success=False, error=None, files) ; else -> error
other rc: unsupported if _git_version(repo) < (2, 38) else error
```

## DATA
`RebaseProbe`; `success` True only for `clean`; `conflict` has `error=None`.

## Tests
- Parser: tree + two paths; non-ASCII path; tree only; empty bytes → `(None, [])`.
- Real repo: conflict on `dätei.txt` → `conflict`, `files == ["dätei.txt"]`.
- Clean (non-overlapping changes) → `clean`, `success=True`.
- Bad ref (`no-such-ref`) → exit 1 with empty stdout → `error`, not `conflict`.
- Mocked `run_git_raw` → `(129, b"", "usage")` + patched `_git_version` → `(2, 37)` →
  `unsupported`; with `(2, 40)` → `error`.
- `base_ref="-x"` → `error`. Non-repo → `error`.

## vulture
`_.files` (and `_.status` if reported).
