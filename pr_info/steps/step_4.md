# Step 4 — Visible warning in `check_branch_status`

**Context:** see [summary.md](./summary.md), section "Visible warning placed in
`checks/`, not `git_operations/`".

**Goal:** make the most common encounter with a transferred issue visible in the
log. Without this, `check_branch_status` on a branch named `72-something`
degrades to "no issue data" with nothing but a `debug`-level line.

Depends on steps 1–3.

---

## WHERE

| Path | Change |
|---|---|
| `src/mcp_workspace/checks/branch_status.py` | New import + new `except` clause at line ~510 |
| `tests/checks/test_branch_status.py` | New warning-emitted test |

### Explicitly NOT changed

- `src/mcp_workspace/git_operations/base_branch.py:73` — `git_operations` sits
  *below* `github_operations` in the layer stack and reaches it only through two
  `ignore_imports` waivers. Importing the exception there would need a third
  architectural waiver for a log level. It is also the *inner* of the two
  catches: `branch_status` fetches first, and when that raises, `issue_data`
  stays `None`, so `_detect_from_issue` re-fetches and hits the guard again —
  warning in both places would log the same transfer twice per call.
- `src/mcp_workspace/github_operations/issues/cache.py:334` — unchanged.

---

## WHAT

No new functions. One import and one `except` clause.

---

## HOW

Add a top-level import alongside the existing `github_operations` imports
(`branch_status.py` lines 28–37 — this file imports at module level, not lazily):

```python
from mcp_workspace.github_operations import IssueIdentityMismatchError
```

`checks` sits *above* `github_operations`, so this import needs no waiver.
Place it in the existing alphabetical block, before the
`from mcp_workspace.github_operations.issues import ...` line.

Then, in `collect_branch_status`, insert the new clause **before** the existing
broad catch at line 510:

```python
                try:
                    fetched = issue_manager.get_issue(issue_number)
                    if fetched and fetched.get("number", 0) > 0:
                        issue_data = fetched
                except IssueIdentityMismatchError as e:
                    logger.warning("%s", e)
                except Exception:  # pylint: disable=broad-exception-caught
                    logger.debug("Failed to fetch issue data", exc_info=True)
```

Order matters — `IssueIdentityMismatchError` is a `ValueError`, so the broad
`except Exception` would otherwise swallow it first.

---

## ALGORITHM

```
try to fetch the issue for the branch's issue number
on IssueIdentityMismatchError:  log the exception message at WARNING, continue
on any other Exception:         log at DEBUG as before, continue
issue_data stays None in both cases; the report degrades to "no issue data"
```

The exception is **caught, not re-raised** — `check_branch_status` must keep
producing a report. Log the message as-is: it already reads as user-facing text
and carries the transfer target and URL.

---

## DATA

No data structure changes. `BranchStatusReport` is unchanged; on this path
`issue_data` is `None` and `base_branch` degrades to `"unknown"`, exactly as it
does today for any other fetch failure. The only difference is log level and
message content.

---

## TESTS (write first)

In `tests/checks/test_branch_status.py`, follow the established
`@patch("mcp_workspace.checks.branch_status.IssueManager")` pattern used at
lines 486, 531, 574 etc.:

```python
@patch("mcp_workspace.checks.branch_status.detect_base_branch")
@patch("mcp_workspace.checks.branch_status.PullRequestManager")
@patch("mcp_workspace.checks.branch_status.IssueManager")
@patch("mcp_workspace.checks.branch_status.extract_issue_number_from_branch")
@patch("mcp_workspace.checks.branch_status.get_current_branch_name")
def test_transferred_issue_logs_warning(
    self, mock_branch, mock_extract, mock_issue_mgr_cls, mock_pr_mgr_cls,
    mock_detect, caplog,
) -> None:
    mock_branch.return_value = "72-feature"
    mock_extract.return_value = 72
    mock_issue_mgr = MagicMock()
    mock_issue_mgr.get_issue.side_effect = IssueIdentityMismatchError(
        "Issue #72 was transferred to test/other-repo#220 — https://example/220"
    )
    mock_issue_mgr_cls.return_value = mock_issue_mgr
    mock_detect.return_value = "main"

    with caplog.at_level(logging.WARNING):
        report = collect_branch_status(Path("/tmp"))

    assert "was transferred to test/other-repo#220" in caplog.text
    assert report is not None          # degrades, does not raise
```

Two assertions, both load-bearing: the message is **visible at WARNING**, and
the report is still produced rather than the exception escaping.

Match the exact decorator/parameter ordering and typing style of the
neighbouring tests in that file (they annotate params as `MagicMock`).

---

## CHECKS

```
mcp__tools-py__run_pylint_check
mcp__tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])
mcp__tools-py__run_mypy_check
mcp__tools-py__run_lint_imports_check
```

`run_lint_imports_check` matters here specifically: this step adds a
cross-package import, and the whole point of putting it in `checks/` rather than
`git_operations/` is that it needs no new waiver. If import-linter complains,
the import landed in the wrong module.

---

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_4.md`.
>
> Implement step 4: in `src/mcp_workspace/checks/branch_status.py`, import
> `IssueIdentityMismatchError` from `mcp_workspace.github_operations` and add an
> `except IssueIdentityMismatchError as e: logger.warning("%s", e)` clause
> **before** the existing broad `except Exception` at line ~510. The exception
> is caught, not re-raised — the report must still be produced.
>
> Do **not** touch `git_operations/base_branch.py:73` or
> `github_operations/issues/cache.py:334`; the step file explains why.
>
> Follow TDD: add the warning test to `tests/checks/test_branch_status.py`
> first, watch it fail, then implement.
>
> Use MCP tools for all file operations. Run `mcp__tools-py__run_pylint_check`,
> `mcp__tools-py__run_pytest_check`, `mcp__tools-py__run_mypy_check` and
> `mcp__tools-py__run_lint_imports_check`. Fix everything before finishing.
> Then run `./tools/format_all.sh` and make exactly one commit.
>
> After this step, add the follow-up note from the summary to the PR
> description: file an issue on **mcp_coder** to catch
> `IssueIdentityMismatchError` in `execute_set_status`, print the message and
> exit `3`.
