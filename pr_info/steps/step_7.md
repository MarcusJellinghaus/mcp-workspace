# Step 7 — `commit_all_changes` precheck uses `get_working_tree_status`, fails closed

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_7.md` exactly.
> Tests first, then code. Run format, pylint, pytest (`-n auto`), mypy; all must pass.
> Make one commit: `fix(workflows): commit_all_changes fails when git status fails (#355)`.

## WHERE

- `src/mcp_workspace/git_operations/workflows.py` — import line 23, `commit_all_changes` (~line 76–87)
- `tests/git_operations/test_commits.py` — next to `test_commit_all_changes_no_changes_returns_success`
- `docs/release-notes.md` — Compatibility section

## WHAT

`commit_all_changes(message: str, project_dir: Path) -> CommitResult`: signature unchanged.
New outcome: status failure → `success=False`, `error_category="commit_failed"`.

## HOW

- Import: `from .repository_status import get_working_tree_status, is_git_repository`
  (drop `get_full_status`).
- Move the "no changes" check inside the existing `try` (first statements), reading
  `get_working_tree_status`.
- Docstring Note: add "- Returns error_category 'commit_failed' if the status can't be read".

## ALGORITHM

```
try:
    status = get_working_tree_status(project_dir)
    if not status["success"]:
        error_msg = f"Failed to read working tree status: {status['error']}"; logger.error(error_msg)
        return {success False, commit_hash None, error error_msg, error_category "commit_failed",
                returncode status["returncode"], stderr status["stderr"]}
    if status["clean"]: logger.info("No changes to commit"); return <unchanged success no-op>
    ... unchanged stage + commit ...
```

## DATA

`StatusResult` in → `CommitResult` out.

## Tests (write first)

New `test_commit_all_changes_status_failure_is_commit_failed` (in `test_commits.py`; a plain
class or the existing one, without needing a real repo beyond `git_repo`). Patch
`"mcp_workspace.git_operations.workflows.get_working_tree_status"` to return a failed
`StatusResult` (`success=False, error="git status failed (exit 128)", returncode=128,
stderr="fatal: boom", clean=False`, empty lists). Assert `success is False`,
`error_category == "commit_failed"`, `returncode == 128`, `stderr == "fatal: boom"`, and no
commit created (`len(list(repo.iter_commits()))` unchanged, or `stage_all_changes` not
called). `test_commit_all_changes` and `test_commit_all_changes_no_changes_returns_success`
must still pass.

## Release notes

In `docs/release-notes.md` → `### Compatibility`, add:

```
- `commit_all_changes` returns `success=False` (`error_category="commit_failed"`) when
  `git status` fails, instead of reporting "nothing to commit".
```
