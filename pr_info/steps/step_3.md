# Step 3 — PR manager fixtures without a real repo (task 1, PR part)

## LLM prompt

Read `pr_info/steps/summary.md`, then implement this step (`pr_info/steps/step_3.md`) only. Rewrite the six listed PullRequestManager fixtures to repo_url mode in place (no shared helper). Then fix the `git_integration` markers of the classes that use them. Run only the six test files, then ruff, vulture, pylint and mypy, and produce exactly one commit.

## WHERE

| File | Fixture | owner/repo |
|---|---|---|
| `tests/github_operations/test_pr_manager_merged_by_sha.py` | `fixture_manager` (registered as `manager`) | `testowner/testrepo` |
| `tests/github_operations/test_pr_merge_mixin.py` | `TestMergePullRequest.merge_env` | `testowner/testrepo` |
| `tests/github_operations/test_pr_manager_update_pull_request.py` | `manager_and_repo` | `testowner/testrepo` |
| `tests/github_operations/test_pr_checks_mixin.py` | `TestGetNonGreenChecks.checks_env` | `testowner/testrepo` |
| `tests/github_operations/test_pr_feedback_mixin.py` | `TestGetPRFeedback.mock_manager` | `test/repo` |
| `tests/github_operations/test_pr_feedback_mixin_closing_issues.py` | `TestGetClosingIssueNumbers.mock_manager` | `test/repo` |

## WHAT

Signatures and return types stay the same, except that `fixture_manager` drops its `tmp_path` parameter, and so does every other fixture that no longer uses it.

```python
def fixture_manager() -> Iterator[PullRequestManager]            # or -> PullRequestManager with return
def merge_env(self) -> Iterator[tuple[PullRequestManager, MagicMock]]
def manager_and_repo() -> Iterator[tuple[PullRequestManager, MagicMock]]
def checks_env(self) -> Iterator[tuple[PullRequestManager, MagicMock]]
def mock_manager(self) -> PullRequestManager                      # TestGetPRFeedback, TestGetClosingIssueNumbers
```

## HOW

- Replace `git_dir` creation, `git.Repo.init`, `create_remote` and `PullRequestManager(git_dir)` with `PullRequestManager(repo_url="https://github.com/<owner>/<repo>.git", github_token="dummy-token")`, using the owner/repo from the table.
- Remove the `base_manager.get_github_token` patch.
- **Keep** the `mcp_workspace.github_operations._client.Github` patches (they work). Don't preset `_repository` instead.
- Where removing the token patch leaves a fixture with no patch at all (`fixture_manager`, both `mock_manager`), turn it into a plain `return`, dropping the `with` and the `yield`.
- Do not copy `base_manager.Github` / `github.Github` patches into new code.
- `test_pr_feedback_mixin.py` still uses `git` in `TestMergeableStateField` / `TestAuthorAssociationField` (inline `Repo.init`, out of scope per decision 3), so keep `import git` there. In the other five files, remove `import git` and any `Path` import that becomes unused.
- **Project-dir fallback** (only if a test needs it, e.g. `default_branch` or `create_pull_request(base_branch=None)`): patch `mcp_workspace.git_operations.is_git_repository` and `mcp_workspace.git_operations.get_repository_identifier`, with `project_dir=Mock(spec=Path)` or `tmp_path`.

### Markers

After the change, these scopes create no repo (their only `Repo.init` was in the fixture). Remove `@pytest.mark.git_integration` from:
- `TestFindMergedPrByHeadSha`
- `TestMergePullRequest`
- `TestUpdatePullRequest`
- `TestGetNonGreenChecks`
- `TestGetPRFeedback`
- `TestGetClosingIssueNumbers`

Re-read each class for inline `Repo.init`, repo fixtures or git subprocesses before removing the marker. If one exists, mark only that test. **Keep** the markers on `TestMergeableStateField` and `TestAuthorAssociationField`.

## ALGORITHM

```
merge_env / checks_env / manager_and_repo:
    mock_repo = MagicMock(); client = MagicMock(); client.get_repo.return_value = mock_repo
    with patch("mcp_workspace.github_operations._client.Github", return_value=client):
        manager = PullRequestManager(repo_url="https://github.com/testowner/testrepo.git", github_token="dummy-token")
        yield manager, mock_repo
```

## DATA

Unchanged fixture return values: `PullRequestManager`, or `(PullRequestManager, MagicMock)`. `manager.project_dir is None`.

## Tests / checks

Existing tests are the spec; assertions stay unchanged.

- `run_pytest_check(extra_args=["-n", "auto", "tests/github_operations/test_pr_manager_merged_by_sha.py", "tests/github_operations/test_pr_merge_mixin.py", "tests/github_operations/test_pr_manager_update_pull_request.py", "tests/github_operations/test_pr_checks_mixin.py", "tests/github_operations/test_pr_feedback_mixin.py", "tests/github_operations/test_pr_feedback_mixin_closing_issues.py"])`
- `run_ruff_check`, `run_vulture_check`, `run_pylint_check`, `run_mypy_check`, `run_format_code`.
- If tests still fail after the project-dir fallback, write one line to `pr_info/.blocked.txt` naming the failing test and stop.

## Commit

`test(github_operations): build PR manager fixtures in repo_url mode`
