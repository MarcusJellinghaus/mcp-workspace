# Step 2 — `_last_repository_error` on `BaseGitHubManager`

Reference: `pr_info/steps/summary.md` for full context and architecture. This step
implements summary point 2 only.

## Precondition

Read `src/mcp_workspace/github_operations/base_manager.py`. If `BaseGitHubManager`
already defines `_last_repository_error`, write one line to `pr_info/.blocked.txt`
and stop.

## WHERE

- `src/mcp_workspace/github_operations/base_manager.py` — `BaseGitHubManager.__init__`,
  `BaseGitHubManager._get_repository`, new module-level function
  `_format_error_message`
- `tests/github_operations/test_base_manager.py` — new test class
  `TestLastRepositoryError` (check first whether a `_get_repository` test class
  already exists and extend that instead, to avoid duplicate fixtures)

## WHAT

- A new module-level private helper in `base_manager.py`:
  `def _format_error_message(e: BaseException) -> str`. This is the single place
  that derives the `"GitHub API error {status}: {message}"` /
  `"network error: {type}"` text — `_get_repository()` (this step) and
  `ci_results_manager.py`'s `_set_lookup_error` (step 3) both call it instead of
  each re-deriving the format independently.
- `self._last_repository_error: Optional[str] = None` — added in `__init__`,
  alongside the existing `self._repository: Optional[Repository] = None`.
- `_get_repository()` keeps its `Optional[Repository]` signature unchanged. On
  failure it additionally writes the cause to `self._last_repository_error` before
  its existing `return None`.

## HOW

`_get_repository()` is not wrapped by `_handle_github_errors` — it has its own
`try/except GithubException/except Exception` block. Each except branch gets one
extra line, before the existing `return None`, with no other logic changed.

```python
def _format_error_message(e: BaseException) -> str:
    if isinstance(e, GithubException):
        message = e.data.get("message", "") if isinstance(e.data, dict) else ""
        return f"GitHub API error {e.status}: {message}"
    return f"network error: {type(e).__name__}"
```

## ALGORITHM

```
except GithubException as e:
    ... existing debug/error logging, unchanged ...
    self._last_repository_error = _format_error_message(e)
    return None
except Exception as e:
    ... existing logging, unchanged ...
    self._last_repository_error = _format_error_message(e)
    return None
```

## DATA

New instance attribute `_last_repository_error: Optional[str]`. Not reset on
success — single consumer (`get_latest_ci_status`) reads it immediately after a
`None` return within the same call, so no reset-on-success logic is needed.

## Tests (write first)

- `test_last_repository_error_none_before_any_failure` — fresh manager, attribute is
  `None`.
- `test_last_repository_error_set_on_github_exception` — mock the GitHub client to
  raise `GithubException(500, {"message": "boom"}, {...headers...})` from
  `get_repo`; assert `_get_repository()` returns `None` and
  `manager._last_repository_error == "GitHub API error 500: boom"`.
- `test_last_repository_error_set_on_generic_exception` — mock the client to raise
  `RuntimeError("x")`; assert `manager._last_repository_error == "network error: RuntimeError"`.
- `test_last_repository_error_excludes_headers_and_token` — assert the stored string
  contains neither a header value nor the configured token.

No separate direct test for `_format_error_message` — its two branches are already
exercised by the two tests above through `_get_repository()`; a standalone test
would be redundant.

## Commit

One commit: tests plus the `base_manager.py` change. Run pytest (`-n auto`), pylint,
mypy — all must pass. Format, stage, commit.

## LLM Prompt

Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_2.md` exactly:
add the `_format_error_message` module-level helper, add `_last_repository_error`
to `BaseGitHubManager`, and populate it on both failure branches of
`_get_repository()` by calling `_format_error_message`, in
`src/mcp_workspace/github_operations/base_manager.py`. `_get_repository()`'s return
type/signature must not change. Write the tests listed under "Tests (write first)"
in `tests/github_operations/test_base_manager.py` first, then the implementation.
Run pytest/pylint/mypy, format, and commit as one commit. This step does not touch
`_handle_github_errors` or `ci_results_manager.py`.
