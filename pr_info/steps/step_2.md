# Step 2 — Add `MergeResult`, `_failed_merge_result()`, `merge_pull_request()`

**Read first:** `pr_info/steps/summary.md` — the constraints in "Why this needs
care", the KISS decisions, and the authoritative `outcome` mapping table.
**Depends on Step 1** (the decorator must call callable defaults).

## Goal

Add the merge capability to `PullRequestManager`, driven by tests that cover
every acceptance case. One commit: new test file + implementation + checks.

## WHERE

- Implementation: `src/mcp_workspace/github_operations/pr_manager.py`
  — new `MergeResult(TypedDict)`, new `_failed_merge_result()`, new method
  `merge_pull_request()` inside class `PullRequestManager` (place it near the
  other write methods, e.g. after `add_assignees`).
- Test (new): `tests/github_operations/test_pr_manager_merge.py`
  — class `TestMergePullRequest`, marked `@pytest.mark.git_integration`, using
  `create_mock_pr` from `._pr_test_helpers`.
- New imports in `pr_manager.py`: add `Literal` to the `typing` import line.

## WHAT

```python
class MergeResult(TypedDict):
    """Outcome of a merge attempt."""
    merged: bool
    outcome: Literal["merged", "refused", "error"]
    sha: Optional[str]        # merge commit SHA when merged
    message: str              # GitHub's message, or the local failure reason
    status: Optional[int]     # HTTP status when GitHub answered (405, 409, 5xx...)


def _failed_merge_result() -> MergeResult:
    """Fresh MergeResult for the decorator default (outcome='error')."""
    return {"merged": False, "outcome": "error", "sha": None,
            "message": "", "status": None}


@log_function_call
@_handle_github_errors(default_return=_failed_merge_result)
def merge_pull_request(
    self,
    pr_number: int,
    merge_method: str = "squash",       # "squash" | "merge" | "rebase"
    sha: Optional[str] = None,
    commit_title: Optional[str] = None,
    commit_message: Optional[str] = None,
) -> MergeResult:
    ...
```

## HOW (integration points)

- Decorate exactly like the siblings: `@log_function_call` then
  `@_handle_github_errors(default_return=_failed_merge_result)` (a **callable** —
  this is why Step 1 is a prerequisite).
- Use `self._validate_pr_number(...)` and `self._get_repository()` (inherited),
  then `repo.get_pull(pr_number)`.
- The decorator owns everything that is **not** a `GithubException` (network,
  `AssertionError`) → falls through to `_failed_merge_result()` → `error`. Do
  **not** add a bare `except Exception` in the method.
- Populated 405/409/422/404/5xx results come from **one** `except GithubException`
  wrapping only the `pr.merge(...)` call (Constraint 1).

## ALGORITHM (core logic)

```
if merge_method not in {"squash","merge","rebase"}: raise ValueError(...)   # first — caller contract
if not self._validate_pr_number(pr_number): return _failed_merge_result()   # get_pull NOT called
repo = self._get_repository(); if repo is None: return _failed_merge_result()
pr = repo.get_pull(pr_number)
kwargs = {"merge_method": merge_method}
for name, val in (("sha", sha), ("commit_title", commit_title),
                  ("commit_message", commit_message)):
    if val is not None: kwargs[name] = val          # omit None (Constraint 4)
try:
    status = pr.merge(**kwargs)                       # PullRequestMergeStatus on 200
    return {"merged": True, "outcome": "merged", "sha": status.sha,
            "message": status.message, "status": 200}
except GithubException as e:
    if e.status in (401, 403): raise                 # decorator contract
    if e.status == 405:                              # already-merged race
        try:
            pr = repo.get_pull(pr_number)            # re-fetch once
        except GithubException:
            return {..."refused"..., "status": 405}
        if pr.merged:
            return {"merged": True, "outcome": "merged",
                    "sha": pr.merge_commit_sha, "message": ..., "status": 405}
        return {..."refused"..., "status": 405}
    if e.status in (409, 422): return {..."refused"..., "status": e.status}
    return {..."error"..., "status": e.status}       # 404, 5xx
```

Message field: on refused/error use a short local reason incorporating
`e.data`/`str(e)`; on merged use `status.message` (or GitHub's on the 405 path).

## DATA

Returns `MergeResult`. `outcome` is the only cross-process contract. `status` is
diagnostic-only for 405 (GitHub returns 405 for several distinct causes) but
**actionable for 409** (head SHA moved — consumer re-verifies CI on new HEAD).

## DOCSTRING (must document)

- The `sha` race guard: forwarding an expected head SHA makes GitHub return 409
  if the branch moved, preventing an unverified merge.
- The full `outcome` mapping (the table in the summary).
- The 405 re-fetch wording, **no causation claim**: *"merged=True reports that
  the PR is merged as of that read — not that this call performed the merge."*
- `status` is diagnostic-only for 405 but actionable for 409.
- A `Raises:` block: `ValueError` for an invalid `merge_method`.
- No branch deletion (out of scope).

## TESTS (`tests/github_operations/test_pr_manager_merge.py`)

Use a local `manager` fixture / helper to build the git repo + patch the token
(remove the boilerplate repeated in sibling tests). Cover:

- `test_merge_success_squash` → `outcome="merged"`, `sha` set, `merged is True`;
  assert `pr.merge` called with `merge_method="squash"` and **no** `sha`/
  `commit_title`/`commit_message` kwargs.
- `test_merge_refused_405_not_merged` (405, re-fetched `pr.merged is False`) →
  `outcome="refused"`, `status=405`.
- `test_merge_405_refetch_merged_true` (405, re-fetched `pr.merged is True`) →
  `outcome="merged"`, `sha=pr.merge_commit_sha`.
- `test_merge_405_refetch_fails` (405, second `get_pull` raises
  `GithubException`) → `outcome="refused"`.
- `test_merge_sha_mismatch_409` (409) → `outcome="refused"`, `status=409`.
- `test_merge_server_error_500` (500) → `outcome="error"` (**not** refused).
- `test_merge_invalid_pr_number` (`pr_number=0`) → `outcome="error"`,
  `mock_repo.get_pull.assert_not_called()`.
- `test_merge_invalid_merge_method` (`merge_method="fast-forward"`) →
  `pytest.raises(ValueError)`; `get_pull` not called.
- `test_merge_auth_401_reraised` / `test_merge_auth_403_reraised` →
  `pytest.raises(GithubException)`.
- `test_merge_passes_optional_kwargs` (sha/title/message provided) → assert those
  kwargs **are** forwarded when non-None.

For 405 with re-fetch, configure `mock_repo.get_pull.side_effect` as a two-item
list (first call returns the PR whose `.merge` raises 405; second returns the
re-fetched PR) — or set `pr.merge.side_effect` and a second `get_pull` return.

## CHECKS

- `mcp__tools-py__run_pylint_check`
- Fast unit run:
  `mcp__tools-py__run_pytest_check(extra_args=["-n","auto","-m","not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])`
- Merge tests (marked git_integration):
  `mcp__tools-py__run_pytest_check(extra_args=["-n","auto"], markers=["git_integration"])`
- `mcp__tools-py__run_mypy_check`

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`. Implement Step 2
> only (Step 1 is already merged). First create
> `tests/github_operations/test_pr_manager_merge.py` with class
> `TestMergePullRequest` marked `@pytest.mark.git_integration`, using
> `create_mock_pr` from `._pr_test_helpers` and a local fixture that builds the
> git repo and patches `get_github_token`; cover every case listed in Step 2
> (TDD). Then in `src/mcp_workspace/github_operations/pr_manager.py` add
> `MergeResult(TypedDict)`, `_failed_merge_result()`, and `merge_pull_request()`
> exactly per the algorithm and docstring requirements — validate `merge_method`
> first (raise `ValueError`), then `pr_number`, `_get_repository`, `get_pull`,
> build conditional kwargs (omit `None`), wrap only `pr.merge(...)` in one
> `except GithubException` with the flat classifier (`401/403 → raise`,
> `405 → re-fetch once`, `(409,422) → refused`, else `error`), and let
> non-Github errors fall through to the decorator. Add `Literal` to the typing
> import. Use MCP tools only. Run pylint, pytest (both the fast-unit exclusions
> and the git_integration marker), and mypy; fix until all pass. This is one commit.
