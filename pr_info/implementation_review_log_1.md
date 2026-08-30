# review-implementation review log 1

## Round 1 — 2026-08-30
**Findings**:
I'll gather context first — loading the tools I need.All checks pass locally (pylint clean, mypy clean, 1765 passed / 1 skipped, lint-imports 9/9 contracts kept). The diff contains real implementation changes across `branch_manager`/`linked_branches_mixin`, `checks/branch_status*`, tests and docs, and covers every element the issue specifies.

src/mcp_workspace/github_operations/issues/linked_branches_mixin.py:57 — low — `validate_issue_number_or_log` lives in the linked-branches mixin, but `issues/base.py` is the documented home for standalone validators shared by "the mixin classes and manager" and already holds a `validate_issue_number` sibling; `branch_manager.py` now imports a general-purpose validator from an unrelated feature module.
src/mcp_workspace/checks/branch_status_rendering.py:333 — low — `_format_linked_branch_line` re-derives the issue number from `report.branch_name` instead of the report carrying it; when that guard returns None for a blocking state the report renders `Review Gate: BLOCKED (linked branch)` with no explanatory line, the disagreeing double verdict the design set out to prevent.
tests/github_operations/issues/test_branch_manager_linked.py:326 — low — `test_malformed_response_returns_none` does not exercise the parse-error path it names: `{"data": None}` raises `AttributeError`, which `_query_linked_branches`' `except (KeyError, TypeError)` does not catch, so the test passes only via the broad catch in `get_linked_branches_or_none` and the in-body parse-error → `None` branch stays uncovered.
src/mcp_workspace/server.py:37 — low — isort-only reformat of a single-name import, unrelated to issue #268.
**Decisions**:
Verdict(decision='tasks', tasks=['Move `validate_issue_number_or_log` out of `src/mcp_workspace/github_operations/issues/linked_branches_mixin.py` into `src/mcp_workspace/github_operations/issues/base.py` alongside the existing `validate_issue_number`, and update `branch_manager.py` and any other importers to reference the new location.', 'In `src/mcp_workspace/checks/branch_status_rendering.py`, stop re-deriving the issue number from `report.branch_name` in `_format_linked_branch_line`: carry the issue number on the report object itself, and ensure a blocking linked-branch state always renders an explanatory line so `Review Gate: BLOCKED (linked branch)` can never appear without a reason.', 'Fix `tests/github_operations/issues/test_branch_manager_linked.py:326` `test_malformed_response_returns_none` so it actually exercises the parse-error branch inside `_query_linked_branches`: use a payload that triggers the `except (KeyError, TypeError)` handler (not `{"data": None}`, which raises `AttributeError` caught only by the broad handler in `get_linked_branches_or_none`), and assert the in-body parse-error → `None` path is taken.'], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-08-30
**Findings**:
I'll start by loading the tools I need and gathering context.All checks pass locally (pylint clean, mypy clean, pytest 1773 passed / 1 skipped). The diff contains real implementation changes and covers every element issue #268 specifies; the three round-1 tasks were applied correctly.

src/mcp_workspace/github_operations/issues/linked_branches_mixin.py:147 — low — `get_linked_branches_or_none` omits the `@log_function_call` decorator that both sibling methods (`get_linked_branches`, `delete_linked_branch`) carry, so the new production lookup path has less observability than the code it sits beside.
src/mcp_workspace/github_operations/issues/linked_branches_mixin.py:39 — low — `_LINKED_BRANCHES_WITH_IDS_QUERY` duplicates `_LINKED_BRANCHES_QUERY` except for one `id` field, and `delete_linked_branch`'s response walk duplicates the parse in `_query_linked_branches`; the extraction commit was the natural point to collapse the pair.
src/mcp_workspace/github_operations/issues/base.py:38 — low — `validate_issue_number_or_log` was promoted into `base.py`'s `__all__` but `tests/github_operations/issues/test_base.py` only tests `validate_issue_number`; the new public validator has no direct test.
src/mcp_workspace/github_operations/issues/linked_branches_mixin.py:1 — low — the mixin extraction (266-line new module plus splitting the test file into `test_branch_manager_unlink.py`) exceeds what #268 asked for; `branch_manager.py` was 576 lines on `main` and the sibling method alone would have kept it well under the 750-line CI limit, so the split was not forced by file size. It is behaviour-preserving and loses no test coverage, but it enlarges the review surface of an otherwise focused change.
src/mcp_workspace/server.py:37 — low — isort-only reformat of a single-name import, unrelated to issue #268 (carried over from round 1, not tasked).
**Decisions**:
Verdict(decision='tasks', tasks=['Add the `@log_function_call` decorator to `get_linked_branches_or_none` in `src/mcp_workspace/github_operations/issues/linked_branches_mixin.py:147` so it matches the observability of its siblings `get_linked_branches` and `delete_linked_branch`.', 'Add direct unit tests for `validate_issue_number_or_log` in `tests/github_operations/issues/test_base.py`, covering both the valid-input and the invalid-input/logging paths, alongside the existing `validate_issue_number` tests.'], escalate_reason=None)
**Changes**:
applied

## Round 3 — 2026-08-30
**Findings**:
I'll start by loading the tools I need and gathering context.`src/mcp_workspace/server.py:37` — critical — Unrelated cosmetic reformat of `from mcp_workspace.server_reference_tools import set_reference_projects` into a parenthesized multi-line import; isort (`--check --profile=black --float-to-top`) rejects it, and it is the sole failing CI job (run 33303570761). Revert to the single-line form — the edit is outside issue #268's scope and has no behavioural effect.
**Decisions**:
Verdict(decision='tasks', tasks=['Revert the import at `src/mcp_workspace/server.py:37` back to the single-line form `from mcp_workspace.server_reference_tools import set_reference_projects`, removing the unrelated parenthesized multi-line reformat, then confirm isort (`--check --profile=black --float-to-top`) passes.'], escalate_reason=None)
**Changes**:
applied
