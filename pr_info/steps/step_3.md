# Step 3 — Rebuild `get_full_status` on `get_working_tree_status`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_3.md` exactly.
> Tests first (watch the new parity cases fail on the old code), then code. Run format,
> pylint, pytest (`-n auto`), mypy; all must pass. Make one commit:
> `refactor(repository_status): build get_full_status on the -z status parser (#355)`.

## WHERE

- `src/mcp_workspace/git_operations/repository_status.py` — `get_full_status`
- `tests/git_operations/test_repository_status.py` — new class `TestGetFullStatusParity`
- `docs/release-notes.md` — Compatibility section

## WHAT

`get_full_status(project_dir: Path) -> dict[str, list[str]]`: signature, return shape and
the "never raises, failure → empty lists" contract are unchanged. It stays in
`repository_status.py` (mcp-coder imports it from that submodule).

## HOW

- Body calls `get_working_tree_status(project_dir)` (same module).
- Drop the `is_git_repository` precheck: a non-repo is already a failed `StatusResult` with
  empty lists.
- Keep the broad `except Exception` (with its pylint disable): `get_working_tree_status` can
  still raise, e.g. `GitCommandNotFound`.
- `get_staged_changes` / `get_unstaged_changes` are **not** deleted here (step 8). Other
  modules still use them.
- Docstring: replace "Returns empty dict if not a git repository" with "All lists are empty
  if the status could not be read". Keep the existing Note. Paths are repo-relative, forward
  slashes, raw UTF-8.

## ALGORITHM

```
try:
    status = get_working_tree_status(project_dir)
except Exception as e:                       # broad, as today
    logger.warning(...); return {"staged": [], "modified": [], "untracked": []}
return {"staged": status["staged"], "modified": status["modified"], "untracked": status["untracked"]}
```

## DATA

Returns exactly `{"staged": [...], "modified": [...], "untracked": [...]}`, not a
`StatusResult` (mcp-coder iterates `.items()`).

## Tests (write first)

Add `TestGetFullStatusParity` (`@pytest.mark.git_integration`) in
`test_repository_status.py`. Use real repos (`git_repo_with_commit`; `git_repo` for unborn
HEAD). Each test asserts the **full** dict with `==`, plus `set(result) == {"staged",
"modified", "untracked"}` once:

| Case | Setup | Expected |
|---|---|---|
| staged | new file, `git add` | staged=[f] |
| modified | edit `README.md` | modified=["README.md"] |
| untracked | new file in a new dir `d/x.py` | untracked=["d/x.py"] |
| staged-then-modified | add `f`, stage, edit again | staged=[f], modified=[f] |
| rename | `git mv README.md docs.md` | staged=["docs.md"] |
| rename-then-modify | `git mv`, then edit the new file | staged=["docs.md"], modified=["docs.md"] |
| non-ASCII | untracked `ä.txt` | untracked=["ä.txt"] (raw, not C-quoted) |
| unborn HEAD | `git_repo`, stage `f` | staged=[f] |
| unmerged `UU` | two branches edit the same line, `git merge` (expect failure) | staged=[f], modified=[f] |
| intent-to-add | `git add -N f` | staged=[], modified=[f] |
| not a repo | plain `tmp_path` dir | all empty |
| raises | patch `...repository_status.get_working_tree_status` with `side_effect=RuntimeError("boom")` | all empty, no exception |

The `UU` and intent-to-add expectations come from porcelain v1 XY codes (`UU`, ` A`).
They are analytical, not yet run. If, after the rebuild, either case yields something other
than the table, write one line to `pr_info/.blocked.txt` and stop.

Keep the existing `test_get_full_status`. Leave `test_get_staged_changes` /
`test_get_unstaged_changes` for step 8.

## Release notes

In `docs/release-notes.md` → `### Compatibility`, add after the `detect_base_branch` bullet:

```
- `get_full_status` reads the `-z` status: paths are raw UTF-8 (no C-quoting), a
  staged-renamed-then-modified file is reported by its new path (not `old -> new`), and a
  status failure gives all-empty lists (never partial).
```
