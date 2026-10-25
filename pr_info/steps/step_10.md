# Step 10 — `clone_repo` relaxation + credential scrubbing

## LLM prompt
Read `pr_info/steps/summary.md` and this file. Implement step 10 only, tests first. Run the
checks from the summary, format, commit as one commit.

## WHERE
- `src/mcp_workspace/git_operations/remotes.py` (`clone_repo`, add `_scrub_credentials`)
- `tests/git_operations/test_remotes.py` (`TestCloneRepo`, ~line 531)

## WHAT
```python
_USERINFO_RE = re.compile(r"(?<=://)[^/@\s]+@")

def _scrub_credentials(text: str) -> str:
    """Remove userinfo ('user:token@') from every URL in text."""

def clone_repo(url: str, target_path: Path) -> None:  # signature unchanged
```

## HOW
- Allow an existing empty directory; reject a non-empty directory and an existing file
  (`ValueError`).
- On `GitCommandError`: `raise ValueError(f"Failed to clone '{_scrub_credentials(url)}': "
  f"{_scrub_credentials(str(e))}") from None` — no exception chain.
- Update the docstring (`Raises`). `reference_projects.py` is unaffected.

## ALGORITHM
```
validate url / target as today
if target.exists():
    if target.is_file() or any(target.iterdir()): raise ValueError("... exists and is not an empty directory")
try clone_from(url, str(target))
except GitCommandError as e: raise ValueError(scrubbed message) from None
```

## DATA
None (raises `ValueError`).

## Tests
- Replace `test_clone_target_exists`: empty `tmp_path` dir → `clone_from` called (mocked).
- Non-empty directory → `ValueError`; existing file → `ValueError`.
- Mocked `clone_from` raising `GitCommandError` whose message contains
  `https://user:s3cret@host/r.git`, called with that URL → message lacks `s3cret`,
  `__cause__ is None` and `__suppress_context__ is True`.
- `_scrub_credentials` unit cases: `https://u:p@h/x`, `ssh://git@h/x`, no userinfo unchanged.
