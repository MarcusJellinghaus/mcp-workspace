# Step 2 — Issue manager fixtures without a real repo (task 1, issue part)

## LLM prompt

Read `pr_info/steps/summary.md`, then implement this step (`pr_info/steps/step_2.md`) only. Replace the repo-creating issue manager fixture and helper with one repo_url-mode builder. Then fix the `git_integration` markers in the files that used them, following the marker scope rule in the summary. Run only the test files listed below, then ruff, vulture, pylint and mypy, and produce exactly one commit.

## WHERE

- `tests/github_operations/_issue_test_helpers.py`: add the builder, remove `real_issue_manager`
- `tests/github_operations/conftest.py`: `mock_issue_manager` fixture
- `tests/test_server_get_base_branch.py`: former `real_issue_manager` caller (~line 223)
- `tests/checks/test_branch_status_base_branch.py`: former `real_issue_manager` caller (~line 299)
- Marker edits:
  - `tests/github_operations/issues/test_comments_mixin.py`
  - `test_events_mixin.py`
  - `test_labels_mixin.py`
  - `test_manager.py`
  - `test_manager_edit_issue.py`
  - `test_sub_issues_mixin.py`
  - `tests/github_operations/test_github_write_tools_subissues.py` (~line 278)

## WHAT

```python
# tests/github_operations/_issue_test_helpers.py
def make_issue_manager() -> IssueManager:
    """Return an IssueManager for test/repo whose ``_repository`` is a mock."""

# tests/github_operations/conftest.py
@pytest.fixture
def mock_issue_manager() -> IssueManager:
    """Real IssueManager with a mocked GitHub repository (no git repo needed)."""
    return make_issue_manager()
```

## HOW

- `make_issue_manager` builds `IssueManager(repo_url="https://github.com/test/repo.git", github_token="test-token")`. Keep the owner/repo `test/repo`: `make_mock_issue`'s `repository_url` identity check depends on it.
- Sets `manager._repository = Mock()` with `full_name = "test/repo"`, as today.
- No `get_github_token` patch, no `base_manager.Github` patch (no-op; see issue Constraints), no `tmp_path`, no `git.Repo.init`.
- `mock_issue_manager` becomes a plain `return` fixture, with no `Generator`/`yield` and no `tmp_path`.
- Callers that used `with (real_issue_manager(tmp_path) as manager, patch(...), ...)` now do `manager = make_issue_manager()` before the `with`, and drop that item from the `with`. Remove `tmp_path` from the test signature only if nothing else in that test uses it.
- Imports: `from tests.github_operations._issue_test_helpers import make_issue_manager` (match each file's existing import style). Remove now-unused imports (`import git`, `patch`, `contextmanager`, `Iterator`, `Generator`, `Path`) wherever ruff/vulture flag them.
- **Project-dir fallback** (only if a test fails because it needs project-dir mode): patch `mcp_workspace.git_operations.is_git_repository` (return `True`) and construct with `project_dir=Mock(spec=Path)` (precedent: `tests/github_operations/issues/conftest.py::mock_manager`).

### Markers (decision 1, marker scope rule in summary)

After the fixture change, these scopes start no git unless a test inside creates its own repo. Remove their `@pytest.mark.git_integration`:
- `test_comments_mixin.py::TestIssueManagerComments`
- `test_events_mixin.py::TestIssueManagerEvents`
- `test_labels_mixin.py::TestIssueManagerLabels`, `TestGetIssueForStatus`, `TestTransitionIssueLabel`
- `test_manager.py::TestListIssuesExtendedParams`
- `test_manager_edit_issue.py::TestIssueManagerEditIssue`
- `test_sub_issues_mixin.py::TestIssueManagerSubIssues`
- `test_github_write_tools_subissues.py::test_failed_refetch_after_write_reports_success`
- `test_manager.py::TestIssueManagerCore`: move the class marker to the test(s) that start git. That includes at least `test_initialization_requires_github_token`, which has an inline `git.Repo.init`. Read each test in the class. A test that only calls `IssueManager(regular_dir)` on a non-repo directory: judge by reading whether `is_git_repository` spawns git. If unsure, keep the marker on it; task 5's counter run verifies.

Before removing a marker, read the scope for inline `Repo.init`, repo fixtures or `subprocess` git calls. Keep the marker on any test that has one.

## ALGORITHM

```
def make_issue_manager():
    manager = IssueManager(repo_url="https://github.com/test/repo.git", github_token="test-token")
    repo = Mock(); repo.full_name = "test/repo"
    manager._repository = repo
    return manager
```

## DATA

- `make_issue_manager() -> IssueManager`, with `_repository` being a `Mock` (`full_name == "test/repo"`), `project_dir is None`, and `repo_identifier` = `test/repo` on github.com.

## Tests / checks

Existing tests are the spec; assertions stay unchanged.

- `run_pytest_check(extra_args=["-n", "auto", "tests/github_operations/issues", "tests/github_operations/test_github_write_tools_subissues.py", "tests/test_server_get_base_branch.py", "tests/checks/test_branch_status_base_branch.py"])`
- `run_ruff_check`, `run_vulture_check`, `run_pylint_check`, `run_mypy_check`, `run_format_code`.
- If tests still fail after the project-dir fallback, write one line to `pr_info/.blocked.txt` naming the failing test and stop.

## Commit

`test(github_operations): build issue manager fixtures in repo_url mode`
