# Step 9 — `detect_base_branch_with_source` + `BaseBranchSource`

## LLM prompt
Read `pr_info/steps/summary.md` (section 6) and this file. Implement step 9 only, tests
first. `detect_base_branch` must behave exactly as before when `issue_manager` is not
passed; existing tests in `test_base_branch.py` / `test_base_branch_git.py` must pass
unchanged. Run the checks from the summary plus `mcp__mcp-tools-py__run_tach_check`, format,
commit as one commit.

## WHERE
- `src/mcp_workspace/git_operations/base_branch.py`
- `src/mcp_workspace/git_operations/__init__.py` (export both; count +2)
- `tests/git_operations/test_base_branch_source.py` (new)

## WHAT
```python
class BaseBranchSource(Enum):
    ISSUE = "issue"
    PR = "pr"
    MERGE_BASE = "merge_base"
    DEFAULT = "default"

def detect_base_branch_with_source(
    project_dir: Path,
    current_branch: Optional[str] = None,
    issue_data: Optional["IssueData"] = None,
    pr_manager: Optional["PullRequestManager"] = None,
    issue_manager: Optional["IssueManager"] = None,
) -> Optional[tuple[str, BaseBranchSource]]: ...

def detect_base_branch(project_dir, current_branch=None, issue_data=None,
                       pr_manager=None, issue_manager=None) -> Optional[str]:
    result = detect_base_branch_with_source(...); return result[0] if result else None

def _fetch_issue_data(issue_manager: "IssueManager", branch: str) -> Optional["IssueData"]: ...
```

## HOW
- `IssueManager` imported under `TYPE_CHECKING` only, from
  `mcp_workspace.github_operations.issues` (same pattern as `IssueData`).
- `_fetch_issue_data`: number from `extract_issue_number_from_branch`; none → `None`.
  `issue_manager.get_issue(number)` in `try/except Exception` (log warning, `None`).
  Result with `number <= 0` (the manager's empty value on failure) → `None`. Result with a
  truthy `base_branch_error` → log debug, `None` (not trusted).
- Fetch only when `issue_data is None and issue_manager is not None`. When `issue_data` is
  given but has no `base_branch`, the issue step is skipped with no fetch (as today).
- Existing private helpers `_detect_from_issue`, `_detect_from_pr`, `_detect_from_merge_base`
  stay; the new function tags each hit with its source.
- Update the module docstring and `detect_base_branch` docstring (new parameter).

## ALGORITHM
```
branch = current_branch or get_current_branch_name(); None -> return None
if issue_data is None and issue_manager is not None: issue_data = _fetch_issue_data(...)
if (b := _detect_from_issue(issue_data)): return b, ISSUE
if (b := _detect_from_pr(branch, pr_manager)): return b, PR
if (b := _detect_from_merge_base(project_dir, branch)): return b, MERGE_BASE
default = get_default_branch_name(); return (default, DEFAULT) if default else None
```

## DATA
`Optional[tuple[str, BaseBranchSource]]`.

## Tests (mocks for managers; patch the private helpers / git queries as existing tests do)
- Each source: ISSUE (issue_data with base_branch), PR, MERGE_BASE, DEFAULT; all fail → `None`.
- `issue_manager` given, `issue_data=None`, branch `123-x` → `get_issue(123)` called, ISSUE.
- `issue_manager` skipped cases: issue has `base_branch_error`; branch without number (no
  call); `get_issue` raises; `get_issue` returns `number=0` → falls through to PR/next.
- `issue_data` given without `base_branch` and `issue_manager` given → `get_issue` not called.
- `detect_base_branch` returns the name only and matches previous behaviour.
