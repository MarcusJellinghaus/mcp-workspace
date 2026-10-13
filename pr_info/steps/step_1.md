# Step 1 — `PullRequestManager`: add `repo_url` construction support

Read `pr_info/steps/summary.md` first for overall context.

## Goal

`PullRequestManager` currently only accepts `project_dir`. Steps 2 and 3 need it to
also accept `repo_url`, mirroring `IssueManager`/`CIResultsManager`, so the new tools
can target a reference project. This step only changes the constructor — no new
public behavior yet.

## WHERE

- `src/mcp_workspace/github_operations/pr_manager.py` — `PullRequestManager.__init__`
- `tests/github_operations/test_pr_manager.py` — constructor tests (existing
  `TestPullRequestManagerUnit` class, "Initialization Tests" section)

## WHAT

```python
def __init__(
    self,
    project_dir: Optional[Path] = None,
    repo_url: Optional[str] = None,
    github_token: Optional[str] = None,
) -> None:
```

Signature matches `CIResultsManager.__init__` and `IssueManager.__init__` exactly.

## HOW

- Pass all three params through to `super().__init__(project_dir=project_dir,
  repo_url=repo_url, github_token=github_token)` — `BaseGitHubManager` already handles
  "exactly one of project_dir/repo_url", token resolution, etc.
- The existing eager fail-fast block (resolving `self._repo_identifier` right away so a
  missing GitHub remote raises immediately instead of lazily) is **project_dir-specific**
  wording ("git remote") and must not run for `repo_url` mode — gate it behind
  `if project_dir is not None:`.

## ALGORITHM

```
super().__init__(project_dir=project_dir, repo_url=repo_url, github_token=github_token)
if project_dir is not None:
    assert self.project_dir is not None
    try:
        _ = self._repo_identifier
    except ValueError as e:
        raise ValueError(f"Could not detect GitHub repository URL from git remote in: "
                          f"{self.project_dir}. Make sure the repository has a GitHub "
                          f"remote origin configured.") from e
```

## DATA

No new data structures. `self.project_dir` is `None` in `repo_url` mode (same as
every other manager built that way).

## Tests (write first)

Add to `TestPullRequestManagerUnit` in `tests/github_operations/test_pr_manager.py`,
next to the existing `test_initialization_requires_*` tests:

- `test_initialization_accepts_repo_url` — `PullRequestManager(repo_url="https://github.com/test/repo.git")`
  (with `get_github_token` patched to return a dummy token, no `project_dir`/git repo
  needed) succeeds; `manager.project_dir is None`; `manager.repository_name == "test/repo"`.
- Confirm the four existing `test_initialization_requires_*` tests still pass unchanged
  (they cover `project_dir` mode and must keep working identically).

## Commit

One commit: the test additions above plus the constructor change. Run
`mcp__mcp-tools-py__run_pylint_check`, `run_pytest_check` (`extra_args: ["-n", "auto"]`),
`run_mypy_check` — all must pass.

Commit message: `feat(pr_manager): accept repo_url in PullRequestManager constructor`

## LLM prompt for this step

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`. Implement step 1 only:
> add `repo_url` construction support to `PullRequestManager` in
> `src/mcp_workspace/github_operations/pr_manager.py`, following the WHERE/WHAT/HOW/
> ALGORITHM in step_1.md exactly. Write the test first in
> `tests/github_operations/test_pr_manager.py`, then the implementation. Run pylint,
> pytest (`-n auto`), and mypy via the MCP checks; all must pass. Make exactly one
> commit for this step. Do not touch anything from step 2 or later.
