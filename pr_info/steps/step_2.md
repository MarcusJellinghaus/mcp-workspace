# Step 2 — `github_issue_comment` gains `reference_name`, plus the `_ref_suffix` helper

Read [summary.md](./summary.md) first. Depends on step 1 (test module exists).

The first *write* tool, and the first message that must name the target repository. The helper
introduced here is used again in step 3, so it arrives with its first user rather than ahead of
one.

## WHERE

- `src/mcp_workspace/server.py` — new `_ref_suffix` helper next to `_check_labels` (`~:70`);
  `github_issue_comment` (`:1326-1352`)
- `tests/github_operations/test_github_write_tools_reference.py` — extend

## WHAT

```python
def _ref_suffix(reference_name: Optional[str]) -> str:
    """Return the clause naming a reference project, or "" for the workspace."""


@mcp.tool()
@log_function_call
def github_issue_comment(
    number: int,
    body: str,
    reference_name: Optional[str] = None,
) -> str:
```

## HOW

- `_ref_suffix` is a plain module-level function placed above `_check_labels` so step 3 can use
  it too. No class, no state, no lazy import.
- `github_issue_comment`: delete the local `IssueManager` import (`:1341-1342`, comment
  included), swap `:1345` to `manager = _issue_manager(reference_name)`, and append
  `_ref_suffix(reference_name)` to the failure sentinel at `:1349`.
- Docstring (`:1329-1339`) names no repository today, so it needs **only** the new `Args` entry:

  ```
  reference_name: Optional reference project name. When set, the comment is
      posted to that project's GitHub repository instead of the workspace
      repository.
  ```

- Tool stays `def`. The existing `except Exception` wrapper already renders
  `_issue_manager`'s `ValueError` as an error string.

## ALGORITHM

```
_ref_suffix(name):
    return "" if name is None else f" in reference project '{name}'"

github_issue_comment(number, body, reference_name):
    try:
        manager = _issue_manager(reference_name)
        comment = manager.add_comment(number, body)
        if not comment["id"]:                       # empty CommentData sentinel
            return f"Error: failed to add comment to issue #{number}{_ref_suffix(reference_name)}"
        return f"Added comment to issue #{number} — {comment['url']}"
    except Exception as e: return f"Error: {e}"
```

## DATA

- `_ref_suffix` → `""` or `" in reference project 'sibling'"`. The empty string on the workspace
  path is what keeps every existing message byte-identical.
- Success line unchanged (`"Added comment to issue #42 — <url>"`); it already carries a URL, so
  it needs no suffix.
- Failure sentinel cross-repo:
  `"Error: failed to add comment to issue #42 in reference project 'sibling'"`.

## Tests (write first)

In `test_github_write_tools_reference.py`:

1. Add `(github_issue_comment, {"number": 42, "body": "hi"})` to `_TOOL_CASES` and
   `"issue_comment"` to `_TOOL_IDS` — the three parametrized tests from step 1 then cover it.
2. Extend `_make_manager()` so `add_comment` returns a real `CommentData` with a non-zero `id`
   (a `MagicMock` return value would make `comment["id"]` opaquely truthy).
3. `test_comment_failure_names_reference_project` — `add_comment` returns an empty-ish
   `CommentData` (`id=0`); assert the result is exactly
   `"Error: failed to add comment to issue #42 in reference project 'sibling'"`.
4. `test_comment_failure_without_reference_is_unchanged` — same, no `reference_name`; assert
   exactly `"Error: failed to add comment to issue #42"`.

Existing `github_issue_comment` coverage in `test_github_write_tools_issues.py` must stay green
unchanged.

## LLM prompt

> Implement step 2 of `pr_info/steps/step_2.md`, using `pr_info/steps/summary.md` for context.
> Work test-first: extend `tests/github_operations/test_github_write_tools_reference.py` with
> the `github_issue_comment` case and the two failure-message tests described in the step, then
> add the `_ref_suffix(reference_name)` helper to `src/mcp_workspace/server.py`, add
> `reference_name: Optional[str] = None` to `github_issue_comment`, swap its manager
> construction to `_issue_manager(reference_name)`, delete the now-unused local `IssueManager`
> import, append the suffix to the failure sentinel, and add the `reference_name` entry to the
> docstring's `Args`. The workspace path (`reference_name=None`) must produce byte-identical
> output to today. Do not modify any other tool. Use the MCP file tools, then run
> `mcp__mcp-tools-py__run_pylint_check`, `mcp__mcp-tools-py__run_pytest_check` (with
> `extra_args: ["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not
> claude_api_integration and not formatter_integration and not github_integration and not
> langchain_integration"]`) and `mcp__mcp-tools-py__run_mypy_check`, and fix everything they
> report. One commit.
