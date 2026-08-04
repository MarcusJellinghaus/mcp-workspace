# Step 1 — Make `_handle_github_errors` call callable defaults

**Read first:** `pr_info/steps/summary.md` (esp. "Why this needs care" #5 and the
KISS decisions). This step is a self-contained prerequisite for Step 2.

## Goal

Fix the `_handle_github_errors` decorator so a **callable** `default_return` is
*invoked* on failure (returning a fresh value), instead of being returned as the
function object. Non-callable defaults (dict / list / `False` / `None`) keep
working unchanged. This lets Step 2 use a `_failed_merge_result()` factory and
also repairs two latent sites (`list_pull_requests`, `get_pr_feedback`).

One commit: test + implementation + all three checks passing.

## WHERE

- Implementation: `src/mcp_workspace/github_operations/base_manager.py`
  — function `_handle_github_errors` (the two `return cast(T, default_return)`
  lines inside `wrapper`).
- Test: `tests/github_operations/test_base_manager.py`
  — class `TestHandleGitHubErrorsDecorator`.

## WHAT

No signature change. Behaviour change only, in the `wrapper` closure:

```python
def _handle_github_errors(
    default_return: Any,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    ...
    # helper (module-level or inline): resolve the default once, per failure
    # value = default_return() if callable(default_return) else default_return
```

## HOW

- Keep the existing control flow: `ValueError` re-raises; `GithubException` with
  status in `(401, 403)` re-raises; all other `GithubException` and all other
  `Exception` log and return the default.
- At **both** return sites, replace `return cast(T, default_return)` with a
  resolved value:
  `resolved = default_return() if callable(default_return) else default_return`
  then `return cast(T, resolved)`.
- Update the decorator docstring to note that a callable `default_return` is
  called (factory) to produce a fresh value per failure.
- Do **not** touch the ~34 existing call sites — they pass non-callables and are
  unaffected. Do not remove the inner `try/except` in `list_pull_requests` /
  `get_pr_feedback` in this step (out of scope; they simply stop being load-bearing).

## ALGORITHM (both except branches)

```
log the error
resolved = default_return() if callable(default_return) else default_return
return cast(T, resolved)
```

## DATA

- Input: `default_return: Any` — either a value or a zero-arg callable.
- Output: the wrapped function's return type `T`. For a callable default, the
  call's result; otherwise the value itself.

## TESTS (add to TestHandleGitHubErrorsDecorator)

- `test_decorator_callable_default_is_invoked`: a function decorated with
  `@_handle_github_errors(default_return=lambda: {"outcome": "error"})` that
  raises `GithubException(500, ...)` returns `{"outcome": "error"}` (a dict,
  **not** a function object). Assert `callable(result) is False` and equality.
- `test_decorator_callable_default_fresh_instance_each_call`: default is
  `lambda: []`; call the failing function twice; assert the two results are
  equal but **not the same object** (`result_a is not result_b`) — proves a fresh
  instance per failure (no shared-mutable-dict hazard).
- `test_decorator_noncallable_default_unchanged`: `default_return={}` on a 500
  still returns `{}` (regression guard for the ~34 unaffected sites).

Existing tests (401/403 raise, success returns value, other-error returns
default) must remain green.

## CHECKS

Run after the edit and before committing:
- `mcp__tools-py__run_pylint_check`
- `mcp__tools-py__run_pytest_check(extra_args=["-n","auto","-m","not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])`
- `mcp__tools-py__run_mypy_check`

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`. Implement Step 1
> only: in `src/mcp_workspace/github_operations/base_manager.py`, change
> `_handle_github_errors` so that when `default_return` is callable it is called
> to produce the return value (fresh per failure), otherwise returned as-is —
> apply this at **both** `return cast(T, default_return)` sites, keeping the
> existing `ValueError` / 401 / 403 re-raise behaviour. Update the decorator
> docstring. First add the three tests described in Step 1 to
> `TestHandleGitHubErrorsDecorator` in `tests/github_operations/test_base_manager.py`
> (TDD), then implement. Use MCP tools only (`mcp__workspace__*` for files,
> `mcp__tools-py__*` for checks). Do not modify the existing call sites or the
> inner try/except blocks in `list_pull_requests` / `get_pr_feedback`. Run
> pylint, pytest (fast-unit exclusions), and mypy; fix everything until all pass.
> This is one commit.
