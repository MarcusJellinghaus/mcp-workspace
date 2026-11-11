# Step 11 — Tool `git_commit`

## LLM prompt

> Read `pr_info/steps/summary.md` ("KISS decisions") and this file. Implement step 11 only:
> tests first, then the tool and its orchestration (reuse step 9 helpers). Run format, pylint,
> pytest (`-n auto`), mypy, lint-imports and ruff; all must pass. Make exactly one commit.

## WHERE

- `src/mcp_workspace/toolset/git_write.py`: closure `git_commit`.
- `src/mcp_workspace/toolset/_git_write_helpers.py`: `do_git_commit`, `format_commit_result`.
- `tests/toolset/test_git_commit.py`; `tests/toolset/test_toolset.py`;
  `tests/toolset/tool_schemas/git_commit.json`.

## WHAT

```python
async def git_commit(
    message: Annotated[str, Field(description="Commit message")],
    paths: Annotated[list[str] | None, Field(description=...)] = None,
    all: Annotated[bool, Field(description=...)] = False,  # pylint: disable=redefined-builtin
) -> str:
    """Commit the given paths, or all changes (modifies the repository). ..."""

def do_git_commit(ctx: WorkspaceContext, message: str, paths: list[str] | None, commit_all: bool) -> str: ...
_MAX_COMMITTED_FILES = 50
```

## HOW

- Library: `commit_paths` (commits.py), `commit_all_changes` (workflows.py),
  `list_untracked_paths`, `stage_paths`, `unstage_paths` (staging.py), `committed_files`
  (commits.py), `format_dirty_tree` (remotes.py), `get_current_branch_name`, `operation_in_progress`.
- Description: modifies the repository; exactly one of `paths` / `all`; `paths` may include
  directories — new files under them are included; `all` is `git add -A` (respects
  `.gitignore`, but picks up e.g. `.scratch/`); no amend, no hook bypass; check the file list.
- Same closure pattern as step 9.

## ALGORITHM

```
has_paths = bool(paths); has_paths == commit_all -> "Error: pass exactly one of paths or all=True"
guard_operation(); branch = get_current_branch_name(); None -> "Error: HEAD is detached"
if commit_all: r = commit_all_changes(message, dir); staged = []
else: staged = list_untracked_paths([Path(p) for p in paths]); s = stage_paths(staged)
      s fails -> unstage_paths(staged) (a partial chunked failure leaves earlier chunks staged) -> f"Error: {s.error}"
      r = commit_paths(message, [Path(p) for p in paths], dir); if not r.success and staged: unstage_paths(staged)
nothing = (r.success and r.commit_hash is None) or r.error_category == "nothing_to_commit" or r.error == "No staged files to commit"
nothing -> "Nothing to commit" (+ f" for paths: {', '.join(paths)}" when commit_paths returned
           nothing_to_commit, so a mistyped / missing path is visible) + format_dirty_tree
failure -> f"Error: {r.error}"
files = committed_files(dir) -> format_commit_result(r.commit_hash, branch, files) + format_dirty_tree(dir)
```

## DATA

```
Committed abc1234 on feature/x (3 files)
  src/a.py
  src/b.py
  tests/test_a.py
Working tree:
  untracked: .scratch/probe.py
```
File list capped at `_MAX_COMMITTED_FILES` with `... showing 50 of N files`; the
remaining-changes block is `format_dirty_tree` (already capped per bucket).

## Tests (write first)

Unit (patch library functions where `_git_write_helpers.py` imports them, e.g.
`mcp_workspace.toolset._git_write_helpers.commit_paths` — not in `mcp_workspace.git_operations.*`):
- neither / both of `paths` and `all` → error, nothing called; `paths=[]` counts as "not given".
- detached HEAD, rebase/merge in progress → error.
- commit failure after staging untracked files → `unstage_paths` called with exactly those files.
- `stage_paths` fails partway (patched to return `success=False`) → `Error:`, `unstage_paths`
  called with the untracked files, `commit_paths` not called.
- `commit_all_changes` → `success=True, commit_hash=None` → `Nothing to commit`.
- `commit_all_changes` → "No staged files to commit" → `Nothing to commit`.
- `commit_paths` → `nothing_to_commit` → first line `Nothing to commit for paths: <given paths>`
  (e.g. a mistyped path appears in the message).
- committed file list longer than the cap → truncated line.

Integration (`git_integration`, `origin_clone`):
- `paths` with a modified, a deleted and a new file → all committed; another modified file stays
  uncommitted and appears under `Working tree:`.
- `paths=["newdir"]` with nested new files → included.
- a file staged beforehand but not in `paths` stays staged and uncommitted.
- `all=True` commits everything incl. untracked; clean tree → `Nothing to commit`.
- failing `pre-commit` hook → `Error:`; the untracked files are untracked again.

Snapshot + `EXPECTED`/`ASYNC_TOOLS` as in step 9.

## Commit

`feat(toolset): add git_commit tool`
