# Step 2 — `pull`

## LLM prompt
Read `pr_info/steps/summary.md` and this file. Implement step 2 only (`pull`), tests first,
using `run_git_raw` and `GIT_NONINTERACTIVE_ENV` from step 1. Run the checks from the
summary, format, commit as one commit.

## WHERE
- `src/mcp_workspace/git_operations/remotes.py` (add `pull`)
- `src/mcp_workspace/git_operations/__init__.py` (export `pull`; count +1)
- `tests/git_operations/test_pull.py` (new)

## WHAT
```python
def pull(project_dir: Path) -> GitResult:
    """git pull --no-edit (honors pull.rebase). Replaces raw `git pull` in mcp-coder."""
```

## HOW
- Non-repo (`InvalidGitRepositoryError` / `NoSuchPathError` from `safe_repo_context`) →
  error result, `returncode=None`.
- "No upstream" detected up front with `rev-parse --abbrev-ref --symbolic-full-name @{u}`,
  never from pull's stderr. That check also covers detached HEAD.
- Both git calls use `env=GIT_NONINTERACTIVE_ENV`.
- Log at debug only.

## ALGORITHM
```
open repo (non-repo -> error result)
rc, _, err = run_git_raw(repo, "rev_parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", env=ENV)
if rc != 0: return error "No upstream branch configured for the current branch", rc, err
rc, _, err = run_git_raw(repo, "pull", "--no-edit", env=ENV)
return success if rc == 0 else error f"git pull failed (exit {rc})", rc, err
```

## DATA
`GitResult`: success `{"success": True, "error": None, "returncode": 0, "stderr": ...}`.

## Tests (use `git_repo_with_remote`; clone the bare remote for a second working copy)
- Fast-forward pull brings in a commit pushed from a second clone → success, file present.
- Branch with no upstream → `success=False`, error mentions "upstream", stderr from the
  rev-parse call.
- Non-repo directory → `success=False`, `returncode is None`.
- Pull that fails (remote path deleted after setting upstream) → `success=False`,
  `returncode` nonzero.
