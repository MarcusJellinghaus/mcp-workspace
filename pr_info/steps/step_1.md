# Step 1 — `IssueIdentityMismatchError` + `_get_issue_checked` + export

**Context:** see [summary.md](./summary.md), sections "Architectural / design
changes" 1, 2 and 4.

**Goal:** add the validated-fetch helper and its exception, and make the
exception part of the `github_operations` public API. **No call site is routed
in this step** — the helper is defined and tested but not yet used, so the
existing suite stays green.

---

## WHERE

| Path | Change |
|---|---|
| `src/mcp_workspace/github_operations/base_manager.py` | Add exception class + method on `BaseGitHubManager` |
| `src/mcp_workspace/github_operations/__init__.py` | Export + `__all__` entry |
| `tests/github_operations/test_base_manager.py` | New `TestGetIssueChecked` class |
| `tests/github_operations/test_package_exports.py` | New export assertion |

---

## WHAT

In `base_manager.py`, at module level, after the `T = TypeVar("T")` line and
before `_handle_github_errors`:

```python
class IssueIdentityMismatchError(ValueError):
    """Raised when a fetched issue is not the issue that was requested."""
```

That is the entire class body — no `__init__`, no attributes. See summary
section 4: all consumers use `str(e)` only, and `vulture` is a configured dev
tool that flags unused fields.

As a method on `BaseGitHubManager` (place it directly after `_get_repository`):

```python
def _get_issue_checked(self, repo: Repository, issue_number: int) -> Issue:
    """Fetch an issue and verify it is the one that was requested.

    GitHub answers the old URL of a transferred issue with a 301 that
    PyGithub follows silently, so the response can be an issue from a
    different repository. Validates identity against the request.

    Raises:
        IssueIdentityMismatchError: If the returned issue belongs to another
            repository, or its number differs from ``issue_number``.
    """
```

---

## HOW

Integration points in `base_manager.py`:

- New import: `from github.Issue import Issue` (next to the existing
  `from github.Repository import Repository` on line 14).
- `Repository` is already imported — no change needed.
- The method takes `repo` as a parameter rather than calling
  `self._get_repository()` internally. Every call site already holds `repo` and
  has its own site-specific `if repo is None` branch, and
  `_pr_feedback_sources.py` supplies its own repo object.

In `github_operations/__init__.py`:

- Extend line 9 to
  `from .base_manager import BaseGitHubManager, IssueIdentityMismatchError, get_authenticated_username`
- Add `"IssueIdentityMismatchError",` to `__all__`, keeping the existing
  alphabetical order (after `"CIStatusData"`, before `"LabelData"`).
- Leave the `# Issue-related imports REMOVED per Decision #1` comment in place
  and do **not** move the class into `issues/` — see summary section 2.

---

## ALGORITHM

```
issue = repo.get_issue(issue_number)
actual = last two "/"-separated segments of issue.repository_url, rejoined
if actual.lower() != repo.full_name.lower():
    raise IssueIdentityMismatchError(transfer message)   # names the target
if issue.number != issue_number:
    raise IssueIdentityMismatchError(number message)
return issue
```

Repository check **first**: only that branch can name a transfer target. Strip a
trailing `/` from `repository_url` before splitting.

Exact message texts (client-facing, **no `Error: ` prefix** — the caller adds
it; note the em dash `—` in the first):

```
Issue #72 was transferred to MarcusJellinghaus/mcp-workspace#220 — https://github.com/MarcusJellinghaus/mcp-workspace/issues/220
```
```
Requested issue #72 but GitHub returned #220 from MarcusJellinghaus/mcp-workspace
```

i.e. `f"Issue #{issue_number} was transferred to {actual}#{issue.number} — {issue.html_url}"`
and `f"Requested issue #{issue_number} but GitHub returned #{issue.number} from {actual}"`.

---

## DATA

- **Returns:** the PyGithub `Issue` object, unmodified, on success.
- **Raises:** `IssueIdentityMismatchError`, a `ValueError` subclass. Subclassing
  `ValueError` is load-bearing — `_handle_github_errors` (`base_manager.py:63`)
  re-raises only `ValueError`; anything else becomes an empty `IssueData` and
  the transfer target is lost.
- **No extra API call.** Both `repository_url` and `number` are already in the
  fetched payload. Do **not** use `issue.repository` — the payload has no
  `repository` key, so PyGithub builds an incomplete `Repository` and
  `.full_name` triggers a second HTTP request.

---

## TESTS (write first)

In `tests/github_operations/test_base_manager.py`, a new `TestGetIssueChecked`
class. Test the helper **directly** against `Mock` objects — no `IssueManager`,
no temp git repo, no `git_integration` marker needed.

Build the fixture inline:

```python
manager = BaseGitHubManager.__new__(BaseGitHubManager)   # no __init__ needed
repo = Mock()
repo.full_name = "test/repo"
issue = Mock()
issue.number = 72
issue.repository_url = "https://api.github.com/repos/test/repo"
repo.get_issue.return_value = issue
```

Four cases:

1. **Match returns the issue** — `_get_issue_checked(repo, 72) is issue`, and
   `repo.get_issue` called once with `72`.
2. **Repository mismatch raises** — `repository_url` points at
   `test/other-repo`, `issue.number = 220`, `issue.html_url` set. Assert
   `IssueIdentityMismatchError`, and that the message contains
   `"was transferred to test/other-repo#220"` and the html_url, and does **not**
   start with `"Error: "`.
3. **Number mismatch raises** — same repository, `issue.number = 220`. Assert
   the message matches `"Requested issue #72 but GitHub returned #220"`.
4. **Rename case must NOT fire** — `repo.full_name = "test/NewName"` and
   `repository_url = ".../repos/test/newname"`. Comparison is case-insensitive,
   so this must return normally. This is the regression guard for the
   false-positive risk described in summary section 5.

Also assert `isinstance(exc, ValueError)` in one case — the decorator contract
depends on it.

In `tests/github_operations/test_package_exports.py`, mirror the existing
`test_merge_result_and_pr_data_exported` style:

```python
def test_issue_identity_mismatch_error_exported() -> None:
    assert IssueIdentityMismatchError is not None
    assert issubclass(IssueIdentityMismatchError, ValueError)
    assert "IssueIdentityMismatchError" in github_operations.__all__
```

---

## CHECKS

```
mcp__tools-py__run_pylint_check
mcp__tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])
mcp__tools-py__run_mypy_check
```

The full suite must be green — the helper is unused, so nothing existing
changes behaviour.

---

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`.
>
> Implement step 1 only: add `IssueIdentityMismatchError` and
> `BaseGitHubManager._get_issue_checked()` to
> `src/mcp_workspace/github_operations/base_manager.py`, and export the
> exception from `src/mcp_workspace/github_operations/__init__.py`.
>
> Do **not** route any `repo.get_issue(` call site in this step — that is step 3.
>
> Follow TDD: write the tests in `tests/github_operations/test_base_manager.py`
> and `tests/github_operations/test_package_exports.py` first, watch them fail,
> then implement.
>
> Use the exact message texts from the step file, including the em dash and with
> no `Error: ` prefix. The exception class body is a docstring only — no
> attributes.
>
> Use MCP tools for all file operations. Run
> `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_pytest_check`
> (with `-n auto` and the integration-marker exclusions) and
> `mcp__tools-py__run_mypy_check` and fix everything before finishing.
> Then run `./tools/format_all.sh` and make exactly one commit.
