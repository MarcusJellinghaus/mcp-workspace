# Step 1 — Log the dirty working tree on the `rebase_onto_branch` fall-through

See [summary.md](./summary.md) for goal, design decisions, and accepted costs.

One commit: test + implementation + checks passing.

## WHERE

| File | Change |
|------|--------|
| `tests/git_operations/test_remotes.py` | One new case in `TestRebaseOntoBranch` (class starts at line 205) |
| `src/mcp_workspace/git_operations/remotes.py` | Import extension, one constant, one helper, one edited log call |

## WHAT

New in `src/mcp_workspace/git_operations/remotes.py`, both private, placed immediately
above `rebase_onto_branch`:

```python
_MAX_DIRTY_PATHS_PER_BUCKET = 20

def _format_dirty_tree(project_dir: Path) -> str: ...
```

New in `tests/git_operations/test_remotes.py`, inside `TestRebaseOntoBranch`:

```python
def test_rebase_onto_branch_dirty_tree_logs_files(
    self,
    git_repo_with_remote: tuple[Repo, Path, Path],
    caplog: pytest.LogCaptureFixture,
) -> None: ...
```

## HOW — integration points

1. Extend the existing import at `remotes.py:13`:

   ```python
   from .repository_status import get_full_status, is_git_repository
   ```

   This is the only import change. `Path` is already imported (line 5), `logger` comes from
   `.core` (line 12).

2. Change the fall-through warning at `remotes.py:351` — the branch reached after the
   up-to-date check and the rebase-in-progress check have both declined — from:

   ```python
   logger.warning(f"Skipping rebase: {e}")
   ```

   to:

   ```python
   logger.warning(f"Skipping rebase: {e}{_format_dirty_tree(project_dir)}")
   ```

   The f-string style matches the surrounding branch. Do **not** touch the conflict branch
   (`remotes.py:338-348`) or the outer handler (`remotes.py:354`) — see the summary's
   decision table for why.

3. The test class already carries `@pytest.mark.git_integration`; the new method inherits
   it. The marker is registered in `pyproject.toml` and is not deselected — `addopts`
   (`pyproject.toml:82`) has no `-m` filter, so the test runs in the default suite.

4. Use `caplog.at_level("WARNING")` with the string form, as `test_verification.py:143`
   does, so `test_remotes.py` needs no new `import logging`.

## ALGORITHM

`_format_dirty_tree`:

```
status = get_full_status(project_dir)          # never raises; always has all 3 keys
for label in ("staged", "modified", "untracked"):
    paths = status[label]; skip if empty
    line = f"  {label}: " + ", ".join(first _MAX_DIRTY_PATHS_PER_BUCKET paths)
    if len(paths) > cap: line += f" ... showing {cap} of {len(paths)} {label}"
return "" if no lines else "\nWorking tree:\n" + "\n".join(lines)
```

Two details that fall out of this:

- No defensive `status.get(label, [])` is needed — every return path in `get_full_status`
  (`git_operations/repository_status.py:51`) constructs all three keys, including its
  not-a-repo early return and its broad `except`.
- `lines` needs an explicit `lines: list[str] = []` annotation; mypy rejects a bare empty
  list assignment.

Test body:

```
repo, project_dir, _ = git_repo_with_remote
push main -u; checkout -b feature-branch
checkout main; add+commit a new file; push main   # advance origin/main
checkout feature-branch
write README.md without committing                # dirty TRACKED file
with caplog.at_level("WARNING"): result = rebase_onto_branch(project_dir, "main")
assert result is False and "README.md" in caplog.text
```

Use `repo.active_branch.name` for the main branch name, as the neighbouring cases do,
rather than hardcoding `"main"`.

## DATA

`_format_dirty_tree` returns `str`:

- `""` when all three buckets are empty. This is what keeps the call site a single line and
  what keeps `test_rebase_onto_branch_invalid_target_branch` logging exactly what it does
  today — that test's tree is clean at the point of failure.
- Otherwise a leading-newline block, one line per non-empty bucket:

  ```
  \nWorking tree:\n  modified: README.md
  ```

`get_full_status` returns `dict[str, list[str]]` with keys `"staged"`, `"modified"`,
`"untracked"`, values root-relative path strings, forward-slashed by git on all platforms.

`rebase_onto_branch`'s signature and return values are unchanged: still
`(Path, str) -> bool`, still `False` on this branch, still never raises.

## TDD order

1. Write the test. Run it and watch it fail on the assertion `"README.md" in caplog.text`,
   not on a setup error — a failure anywhere else means the setup is not reaching the
   fall-through branch.
2. Add the constant and helper, extend the import, edit the call site.
3. Re-run and watch it pass.

## Verification

```
mcp__mcp-tools-py__run_format_code
mcp__mcp-tools-py__run_pylint_check
mcp__mcp-tools-py__run_pytest_check   extra_args: ["-n", "auto"]
mcp__mcp-tools-py__run_mypy_check
```

All must pass before committing. Specifically confirm
`test_rebase_onto_branch_invalid_target_branch` still passes — it is the case that proves
the unconditional `get_full_status` call adds nothing on a clean tree.

The issue records a prior scratch probe confirming that a dirty tracked file lands in the
fall-through branch (no `.git/rebase-merge` or `.git/rebase-apply`) and that
`get_full_status` there returns `{'staged': [], 'modified': ['README.md'], 'untracked':
[]}`. Treat that as the expectation to verify with the new test, not as already-settled
fact. If any `.scratch/` probe is added while working, delete it before committing —
`delete_directory(".scratch", recursive=True)`; CI blocks any PR carrying one.

## Known coverage gap

The truncation clause is not exercised by this test — it needs 21+ dirty files in one
bucket. Left uncovered deliberately: the issue scopes this to one new integration case, and
a fixture that creates 21 files to assert a log substring costs more than the branch is
worth.

## LLM prompt

> Implement Step 1 of issue #295 in the `mcp-workspace` repo. Read `pr_info/steps/summary.md`
> and `pr_info/steps/step_1.md` first; the summary's decision table explains why the check
> goes in the failure handler rather than before the rebase call, and why only one of the
> three `except GitCommandError` branches is touched.
>
> Work test-first. Add `test_rebase_onto_branch_dirty_tree_logs_files` to
> `TestRebaseOntoBranch` in `tests/git_operations/test_remotes.py` following the existing
> `git_repo_with_remote` pattern with no mocking, confirm it fails on its assertion, then
> implement `_MAX_DIRTY_PATHS_PER_BUCKET` and `_format_dirty_tree` in
> `src/mcp_workspace/git_operations/remotes.py` and wire the helper into the fall-through
> `logger.warning`.
>
> Assert the file path appears in `caplog.text`, not the sentence around it — this must not
> become a message-text test. Do not change `rebase_onto_branch`'s signature, return values,
> or control flow, and do not touch the conflict branch or the outer exception handler.
>
> Use the MCP tools per CLAUDE.md. Run `run_format_code`, then `run_pylint_check`,
> `run_pytest_check` with `["-n", "auto"]`, and `run_mypy_check`; all must pass. Commit once,
> with tests and implementation together.
