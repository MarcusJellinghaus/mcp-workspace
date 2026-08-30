# Step 3 — Fix the `fetch_code_scanning_alerts` tuple unpack

**Depends on:** nothing (independent of steps 1, 2). **Commit:** test + fix + checks green.

## Goal

`requestJsonAndCheck` returns a **2-tuple**. `_pr_feedback_sources.py:170` unpacks it three
ways, so `fetch_code_scanning_alerts` has raised `ValueError` against real GitHub since
#175 — `pr_manager.py:678-685` swallows it as
`[unavailable] alerts: ValueError — not enough values to unpack`.

It survives CI only because `_setup_mocks` feeds a 3-tuple the API cannot produce. Fix the
code **and** the mock that hides it.

This is fixed here, before step 4, because step 4 calls the same method and would otherwise
copy line 170 as its template.

## WHERE

- `src/mcp_workspace/github_operations/_pr_feedback_sources.py:170` (modify — one line)
- `tests/github_operations/test_pr_manager_feedback.py` (modify — mock + one new test)

## WHAT

Verified against installed PyGithub:

```python
def requestJsonAndCheck(self, verb, url, parameters=None, headers=None,
                        input=None, follow_302_redirect=False) -> tuple[dict[str, Any], Any]:
    """:return: ``(headers: dict, JSON Response: Any)``"""
```

Change:

```python
_, _, data = manager._github_client._Github__requester.requestJsonAndCheck(...)   # before
_, data = manager._github_client._Github__requester.requestJsonAndCheck(...)      # after
```

Keep the existing `# type: ignore[attr-defined]` and `# pylint: disable=protected-access`
comments and the surrounding `try` / `except GithubException` block (403 → `None` silent
skip, everything else re-raised) exactly as they are.

## HOW

Test harness, `_setup_mocks` at `test_pr_manager_feedback.py:82-83`:

```python
mock_requester.requestJsonAndCheck = Mock(return_value=(200, {}, alerts_response or []))  # before
mock_requester.requestJsonAndCheck = Mock(return_value=({}, alerts_response or []))       # after
```

No other harness change in this step — step 4 converts this into a verb-dispatching
`side_effect`.

## ALGORITHM

None — a one-line unpack correction. The alert-parsing loop below it is unchanged.

## DATA

Unchanged public behaviour:

- `None` on 403 (silent skip — caller does not flag as unavailable)
- `[]` on success with no alerts, or when the repository is unavailable
- `list[dict]` with keys `rule_description`, `message`, `path`, `line`

## TDD — write the test first

New test in `TestGetPRFeedback`, plus the import:

```python
from mcp_workspace.github_operations._pr_feedback_sources import fetch_code_scanning_alerts
```

1. `test_code_scanning_alerts_unpacks_two_tuple` — call `fetch_code_scanning_alerts(manager, 42)`
   **directly** with `mock_requester.requestJsonAndCheck` returning the real 2-tuple shape
   `({}, [<one alert dict>])`. Assert one parsed alert with the expected
   `rule_description` / `message` / `path` / `line`.

   Against the current code this fails with
   `ValueError: not enough values to unpack (expected 3, got 2)` — that failure is the point
   of the test. Confirm you see it before fixing.

2. Existing `test_happy_path` (alerts assertions at lines 205-209) must stay green after the
   harness returns a 2-tuple. It is the regression net for the parsing loop.

Also re-confirm `test_code_scanning_403_silent_skip` and `test_code_scanning_500_unavailable`
still pass — they use `alerts_raises`, so they never reach the unpack, but they share the
harness being edited.

## Verification

All four MCP checks green — `run_pylint_check`, `run_pytest_check`, `run_mypy_check`, and
`run_ruff_check` (the repo selects `["D", "DOC"]`, so ruff is an exit criterion for every
step even when this one touches no docstring).

**`TestGetPRFeedback` is marked `git_integration`**, so the fast-unit exclusion pattern skips
this entire file. Run both:

```
run_pytest_check  extra_args=["-n","auto","-m","not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"]
run_pytest_check  extra_args=["-n","auto"]  markers=["git_integration"]
```

## Commit message

```
Fix fetch_code_scanning_alerts unpacking requestJsonAndCheck as a 3-tuple

requestJsonAndCheck returns (headers, data). The three-way unpack has raised
ValueError against real GitHub since #175, surfacing as
"[unavailable] alerts: ValueError — not enough values to unpack". CI missed it
because the mock fed a 3-tuple the API cannot produce; correct the mock too and
add a test that exercises the real shape.
```

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`.
>
> Implement step 3 only: correct the tuple unpack at
> `src/mcp_workspace/github_operations/_pr_feedback_sources.py:170` from three values to two,
> fix the mock at `tests/github_operations/test_pr_manager_feedback.py:82-83` to return a
> 2-tuple, and add `test_code_scanning_alerts_unpacks_two_tuple`.
>
> Follow TDD: write the new test first and **confirm it fails with
> `ValueError: not enough values to unpack (expected 3, got 2)`** before touching the source.
> That failure is what proves the test is real.
>
> This step is independent of steps 1, 2 and 4. Do not add the verb-dispatching mock
> `side_effect` — that is step 4. Do not modify `fetch_review_data` or `pr_manager.py`.
>
> `TestGetPRFeedback` is marked `git_integration`, so the fast-unit exclusion pattern skips it.
> Run pytest **twice**: once with the exclusion pattern and once with
> `markers=["git_integration"]`.
>
> Use MCP tools exclusively. Run `run_pylint_check`, `run_pytest_check`, `run_mypy_check`,
> and `run_ruff_check` and fix everything before reporting done.
