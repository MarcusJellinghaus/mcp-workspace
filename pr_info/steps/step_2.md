# Step 2 — Prepare test fixtures for the guard

**Context:** see [summary.md](./summary.md), section "Test fixtures fixed rather
than the guard weakened".

**Goal:** make every mock issue and mock repo in the test suite carry a
consistent identity, so that step 3 can route the call sites without turning the
suite red. **This step changes no production code** and is green on its own —
stamping extra attributes on a `Mock` is inert until the guard reads them.

## Why this is a separate commit

`conftest.mock_issue_manager` sets `manager._repository = Mock()`, so
`repo.full_name` is a `Mock`; `repository_url` is set on no mock issue anywhere,
and `number` only at some sites. Once step 3 lands, the helper parses
`issue.repository_url` — a plain `Mock` does not support the `[-2:]` slice, so
the parse raises `TypeError`, `_handle_github_errors` swallows it, and the call
returns empty `IssueData`. Roughly 30 tests would fail at once, mixed in with
the routing diff. Separating them keeps step 3 readable.

---

## WHERE

| Path | Change |
|---|---|
| `tests/github_operations/_issue_test_helpers.py` | **NEW** — `make_mock_issue()` |
| `tests/github_operations/conftest.py` | `full_name` on the mocked repo |
| `tests/github_operations/issues/test_manager.py` | Convert mock-issue sites |
| `tests/github_operations/issues/test_labels_mixin.py` | Convert mock-issue sites |
| `tests/github_operations/issues/test_comments_mixin.py` | Convert mock-issue sites |
| `tests/github_operations/issues/test_events_mixin.py` | Convert mock-issue sites |
| `tests/github_operations/issues/test_branch_manager_create.py` | Convert sites + `full_name` on local `mock_repo`s |

`test_branch_manager_linked.py`, `test_branch_manager_pr_fallback_a.py` and the
`test_cache_*.py` files need **no change** — they only stub `_get_repository` to
return `None`, or mock `IssueManager` wholesale, and never reach
`repo.get_issue`.

---

## WHAT

New module `tests/github_operations/_issue_test_helpers.py`, mirroring the
existing `_pr_test_helpers.py` convention exactly:

```python
"""Shared helpers for issue-fetching unit tests."""

from unittest.mock import MagicMock


def make_mock_issue(number: int = 1, repo_full_name: str = "test/repo") -> MagicMock:
    """Create a mock issue whose identity satisfies _get_issue_checked."""
    mock_issue = MagicMock()
    mock_issue.number = number
    mock_issue.repository_url = f"https://api.github.com/repos/{repo_full_name}"
    return mock_issue
```

Keep it to these two attributes. Callers set `title`, `body`, `state`, `labels`,
`created_at` etc. themselves, exactly as they do today.

---

## HOW

- Import style follows the established pattern
  (`from ._pr_test_helpers import create_mock_pr`, used in five modules):
  - from `tests/github_operations/`: `from ._issue_test_helpers import make_mock_issue`
  - from `tests/github_operations/issues/`: `from .._issue_test_helpers import make_mock_issue`

  Both directories have `__init__.py`, so relative imports work.

- In `tests/github_operations/conftest.py`, inside `mock_issue_manager`, next to
  `mock_repo_obj = Mock()` (line 153):

  ```python
  mock_repo_obj.full_name = "test/repo"
  ```

  `"test/repo"` matches the fixture's git remote,
  `https://github.com/test/repo.git` (line 143). Keep the two consistent.

- In `test_branch_manager_create.py`, the ~5 locally-built `mock_repo = Mock()`
  objects (e.g. line 39) are **not** the conftest fixture — add
  `mock_repo.full_name = "test/repo"` to each alongside the existing
  `mock_repo.name = "test-repo"` line.

---

## ALGORITHM

The conversion at each site is mechanical and shrinks the tests:

```
find:     mock_issue = MagicMock()
          mock_issue.number = issue_number      # present at some sites only
replace:  mock_issue = make_mock_issue(issue_number)
```

Where the site has no issue number in scope (e.g. `test_labels_mixin.py:40`),
pass the literal the test calls the manager with. Where a mock issue is used for
`create_issue` rather than a fetch (`test_manager.py` lines 71, 91 — these feed
`_repository.create_issue`, not `get_issue`), converting is harmless and
consistent; do it anyway rather than leaving two idioms in one file.

Leave every other line of these tests alone — no assertion changes, no
restructuring. `mock_repo.get_issue.assert_called_once_with(123)`
(`test_branch_manager_create.py:87`) stays valid: the step-3 helper makes exactly
one `get_issue` call.

---

## DATA

`make_mock_issue` returns a `MagicMock` with:

| Attribute | Value |
|---|---|
| `number` | the `number` argument |
| `repository_url` | `https://api.github.com/repos/{repo_full_name}` |

All other attributes remain `MagicMock` auto-attributes, unchanged from today.

---

## CHECKS

The mixin test classes carry a **class-level `@pytest.mark.git_integration`**
(e.g. `test_labels_mixin.py:19`), so the recommended fast command *skips exactly
the tests this step touches*. Both runs are required:

```
mcp__tools-py__run_pylint_check
mcp__tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])
mcp__tools-py__run_pytest_check(extra_args=["-n", "auto"], markers=["git_integration"])
mcp__tools-py__run_mypy_check
```

Every test must still pass. If any test *changes* behaviour in this step,
something was converted that should not have been — revert that site.

---

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`.
>
> Implement step 2 only: create
> `tests/github_operations/_issue_test_helpers.py` with `make_mock_issue()`, set
> `full_name` on the mocked repos, and convert the mock-issue construction sites
> in the five listed test files to use the helper.
>
> This step touches **test files only**. Do not modify anything under `src/`.
> Do not route any `repo.get_issue(` call site — that is step 3.
>
> This is a behaviour-preserving refactor, so there are no new tests: the
> existing suite is the test. It must be green both before and after, including
> the `git_integration` marked tests, which the default fast command skips — run
> `mcp__tools-py__run_pytest_check` twice as shown in the step file.
>
> Use MCP tools for all file operations. Run
> `mcp__tools-py__run_pylint_check` and `mcp__tools-py__run_mypy_check` too.
> Then run `./tools/format_all.sh` and make exactly one commit.
