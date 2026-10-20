# Step 1 — `on_error` parameter on `_handle_github_errors`

Reference: `pr_info/steps/summary.md` for full context and architecture. This step
implements summary point 1 only.

## Precondition

Read `src/mcp_workspace/github_operations/base_manager.py`. If `_handle_github_errors`
already has an `on_error` parameter, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/github_operations/base_manager.py` — function `_handle_github_errors`
- `tests/github_operations/test_base_manager.py` — class `TestHandleGitHubErrorsDecorator`

## WHAT

```python
def _handle_github_errors(
    default_return: Any,
    on_error: Optional[Callable[[BaseException, T], None]] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
```

`on_error`, when provided, is called with the caught exception and the resolved
value right after `resolved` is computed from `default_return`, in both the
non-auth `GithubException` branch and the generic `Exception` branch. Never called
from the `ValueError` or 401/403 branches. Its return value is discarded — it
mutates the resolved value in place.

## HOW

- Add `on_error` as the function's second parameter, default `None`.
- No call site passes `on_error` yet in this step (that's step 3) — this step only
  changes the decorator itself and its docstring's Args section.

## ALGORITHM

```
resolved = default_return() if callable(default_return) else default_return
if on_error is not None:
    on_error(e, resolved)
return cast(T, resolved)
```

Applied identically in the `GithubException` (status not in 401/403) branch and the
generic `Exception` branch.

## DATA

No change to `_handle_github_errors`'s own return type.
`on_error: Optional[Callable[[BaseException, T], None]]`.

## Tests (write first)

Add to `TestHandleGitHubErrorsDecorator` in `tests/github_operations/test_base_manager.py`:

- `test_on_error_called_with_exception_and_resolved_on_github_error` — non-auth
  `GithubException`; assert `on_error` mock received `(exception, resolved)` where
  `resolved == default_return`.
- `test_on_error_called_with_exception_and_resolved_on_generic_error` — `RuntimeError`;
  same assertion.
- `test_on_error_not_called_on_auth_error` — 401 and 403 `GithubException`; assert the
  `on_error` mock was never called (exception still raised).
- `test_on_error_not_called_on_success` — successful call; assert `on_error` mock not
  called.
- `test_on_error_can_mutate_resolved_dict_in_place` — `on_error` sets a key on the
  `resolved` dict; assert the decorator's returned value reflects the mutation.
- `test_on_error_optional_omitted_default_none` — call the decorator without
  `on_error`; confirm behavior is unchanged from before this step.

## Commit

One commit: the test additions plus the `base_manager.py` change. Run
`mcp__mcp-tools-py__run_pytest_check` (`extra_args: ["-n", "auto"]`),
`run_pylint_check`, `run_mypy_check` — all must pass. Then `run_format_code`, stage,
commit.

## LLM Prompt

Read `pr_info/steps/summary.md` for the overall design, then implement
`pr_info/steps/step_1.md` exactly as specified: add the optional `on_error` parameter
to `_handle_github_errors` in `src/mcp_workspace/github_operations/base_manager.py`.
Write the tests listed under "Tests (write first)" in
`tests/github_operations/test_base_manager.py` before the implementation. Run
pytest/pylint/mypy, then format and commit as one commit. Do not touch
`ci_results_manager.py` in this step — that is step 3.
