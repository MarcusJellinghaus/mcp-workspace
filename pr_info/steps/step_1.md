# Step 1 — Relocate the six healthy test files into `issues/`

> Read `pr_info/steps/summary.md` first. This is Step 1 of 6. One commit.

## Kind
Pure rename / relocation. **No content changes.** These files already import from
`mcp_workspace.github_operations.issues` and rely on fixtures that cascade from the parent
`tests/github_operations/conftest.py`, so moving them one directory down is sufficient.

## WHERE — moves (source → destination)

| Source (flat) | Destination (`issues/`) |
|---|---|
| `tests/github_operations/test_branch_naming.py` | `tests/github_operations/issues/test_branch_naming.py` |
| `tests/github_operations/test_issue_manager_comments.py` | `tests/github_operations/issues/test_comments_mixin.py` |
| `tests/github_operations/test_issue_manager_labels.py` | `tests/github_operations/issues/test_labels_mixin.py` |
| `tests/github_operations/test_issue_manager_events.py` | `tests/github_operations/issues/test_events_mixin.py` |
| `tests/github_operations/test_issue_manager_integration.py` | `tests/github_operations/issues/test_manager_integration.py` |
| `tests/github_operations/test_issue_branch_manager_integration.py` | `tests/github_operations/issues/test_branch_manager_integration.py` |

## WHAT
Relocate six files verbatim. Do **not** move fixtures (they stay in the parent conftest).
Do **not** touch the helper `validate_*` imports inside the comments/labels/events files —
they import from `issues.base` and keep working.

## HOW
Use `mcp__mcp-workspace__move_file(source_path=..., destination_path=...)` for each move
so git records a rename. The `issues/` package and its `__init__.py`/`conftest.py` already
exist — no new package scaffolding needed.

## ALGORITHM
```
for (src, dst) in the six pairs:
    move_file(src, dst)          # git-mv semantics, byte-for-byte identical content
run pytest on tests/github_operations/issues (incl. git markers) -> all pass
run pytest --collect-only repo-wide -> no collection errors, no duplicate basenames
```

## DATA
No code data structures. Deliverable = six relocated files, identical bytes, new paths.

## Verify (MCP tools only)
- `mcp__tools-py__run_pytest_check(extra_args=["-n","auto","tests/github_operations/issues"])`
  — confirms the moved tests still collect and pass (these are `git_integration`-marked, so
  do **not** exclude that marker here).
- `mcp__tools-py__run_pytest_check(extra_args=["-n","auto","--collect-only"])` — repo-wide
  collection succeeds (catches leftover imports of the old paths).
- `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_mypy_check`.

## Done when
Six files live under `issues/` with their new names, old paths gone, pytest collects and
passes, checks green. One commit.

## LLM prompt
> Implement Step 1 from `pr_info/steps/step_1.md` (context in `pr_info/steps/summary.md`).
> Using `mcp__mcp-workspace__move_file`, relocate the six healthy test files into
> `tests/github_operations/issues/` with the exact renames in the table — **no content
> changes**. Verify with `mcp__tools-py__run_pytest_check` on
> `tests/github_operations/issues` (keep git markers) and a repo-wide `--collect-only`,
> then run pylint and mypy. Follow all `CLAUDE.md` rules (MCP tools only; run
> `./tools/format_all.sh` before committing). Produce exactly one commit.
