# Step 6 — `IssueBranchManager` accepts `github_token`

## LLM prompt
Read `pr_info/steps/summary.md`, then implement this step (`pr_info/steps/step_6.md`)
only. Write the tests first, then the implementation. Run pylint, pytest
(`-n auto`) and mypy; all must pass. Run format_code, then make exactly one commit.

## WHERE
- `src/mcp_workspace/github_operations/issues/branch_manager.py` — `IssueBranchManager.__init__`
- `tests/github_operations/issues/test_branch_manager_create.py`

## WHAT
```python
def __init__(
    self,
    project_dir: Optional[Path] = None,
    repo_url: Optional[str] = None,
    github_token: Optional[str] = None,
) -> None
```

## HOW
`super().__init__(project_dir=project_dir, repo_url=repo_url, github_token=github_token)`.
Docstring gains the `github_token` arg, worded like `BaseGitHubManager`
("Optional explicit token — overrides config lookup when provided.").

## ALGORITHM
None (pass-through).

## DATA
`self.github_token` equals the passed token.

## Tests
- `IssueBranchManager(repo_url="https://github.com/owner/repo", github_token="tok")`
  with `get_github_token` patched to return `None` → constructs, `github_token == "tok"`,
  `get_github_token` not called.
- Without `github_token`, existing behaviour (config lookup) unchanged.
