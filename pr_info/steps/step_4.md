# Step 4 — Public `origin_has_branch`

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_4.md`). Implement
> step 4 only: tests first, then replace the private `_origin_still_has_branch` with a public
> `origin_has_branch` that raises on failure, and catch inline in `_detect_from_merge_base`.
> Run pylint, pytest (`-n auto`) and mypy until green, run `run_format_code`, then make one
> commit.

## WHERE

- `src/mcp_workspace/git_operations/base_branch.py`
- `tests/git_operations/test_base_branch_git.py`

## WHAT

```python
def origin_has_branch(project_dir: Path, branch_name: str) -> bool:
    """Ask origin (git ls-remote, no fetch) whether refs/heads/<branch_name> exists.

    Raises:
        Exception: Whatever GitPython raises when origin cannot be reached or
            authentication fails (callers distinguish "gone" from "unknown").
    """
```

`_origin_still_has_branch` is deleted.

## HOW

- Same body as today minus the `try/except`: `safe_repo_context`,
  `repo.git.ls_remote("--heads", "origin", f"refs/heads/{branch_name}", env=_LS_REMOTE_ENV)`,
  `return bool(output.strip())`. Keep the comment about the full ref.
- `_detect_from_merge_base` replaces `if _origin_still_has_branch(...) is False:` with:

```python
try:
    still_there = origin_has_branch(project_dir, result)
except Exception as e:  # pylint: disable=broad-exception-caught
    logger.debug("Could not ask origin about branch '%s': %s", result, e)
    return result
if not still_there:
    logger.debug("Discarding merge-base winner '%s': deleted on origin", result)
    return None
return result
```

- Not exported from `git_operations/__init__.py` (server imports from the module directly).

## DATA

`True` = listed on origin, `False` = origin answered and the branch is absent, raises = could
not ask.

## Tests (write first)

- `test_base_branch_git.py:89` patches `_origin_still_has_branch` → patch
  `origin_has_branch` instead; existing merge-base behaviour tests stay green
  (`test_unreachable_origin_keeps_the_winner` still passes via the inline catch).
- New: `origin_has_branch` returns `True` for a pushed branch and `False` for an absent one
  (use the existing local-remote fixtures in that file).
- New: `origin_has_branch` raises when `origin` is unreachable (e.g. remote URL pointing to a
  nonexistent path).
