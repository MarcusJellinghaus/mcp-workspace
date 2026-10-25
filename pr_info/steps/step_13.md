# Step 13 — `reset_hard`

## LLM prompt
Read `pr_info/steps/summary.md` and this file. Implement step 13 only, tests first, in
`rebase.py`. Run the checks from the summary, format, commit as one commit.

## WHERE
- `src/mcp_workspace/git_operations/rebase.py`
- `src/mcp_workspace/git_operations/__init__.py` (export; count +1)
- `tests/git_operations/test_rebase.py`

## WHAT
```python
def reset_hard(project_dir: Path, sha: str) -> GitResult:
    """git reset --hard <sha> (restore pre-rebase state)."""
```

## HOW
- `sha` empty or starting with `-` → error result, no git call. Non-repo → error result.
- `run_git_raw(repo, "reset", "--hard", sha, "--")` — the trailing `--` forces `sha` to be
  read as a revision.

## ALGORITHM
```
validate sha; open repo
rc, _, err = run_git_raw(repo, "reset", "--hard", sha, "--")
return success iff rc == 0 (error=f"git reset --hard failed (exit {rc})")
```

## DATA
`GitResult`.

## Tests
- Commit twice, `reset_hard(first_sha)` → HEAD is first sha, working tree matches.
- Uncommitted change discarded.
- Unknown sha → `success=False`, `returncode` nonzero. `"-x"` → `success=False`,
  `returncode is None`. Non-repo → `success=False`.
