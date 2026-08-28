# Step 2 — Name the API base URL in "Could not access repository"

One commit: tests + implementation + checks passing.
Read [summary.md](./summary.md) first, in particular design decision 4.

Independent of step 1 — this improves the message on the workspace path too — but it is what
makes a misconfigured reference project (e.g. a GitLab remote) diagnosable, so it ships with
the feature.

## WHERE

| File | Change |
|---|---|
| `tests/github_operations/test_github_read_tools.py` | Extend two existing tests |
| `src/mcp_workspace/server.py` | Two error strings in `github_pr_view` and `github_search` |

No other file. In particular **no denylist of non-GitHub hosts** is added: GHES and GHE Cloud
are legitimately supported (`hostname_to_api_base_url` has explicit branches for both), so
"not github.com" is not a valid rejection rule, and telling a real GHES host from GitLab would
need hardcoded guesswork that goes stale.

## WHAT

Both tools currently do:

```python
repo = manager._get_repository()  # pylint: disable=protected-access
if not repo:
    return "Error: Could not access repository"
```

Replace the bare message with one that names the API base URL that was tried:

```python
if not repo:
    api_base_url = manager._repo_identifier.api_base_url  # pylint: disable=protected-access
    return f"Error: Could not access repository (tried {api_base_url})"
```

Use the local variable rather than inlining the attribute chain in the f-string — it keeps the
line inside black's width and keeps the `pylint: disable` comment attached to the access, in
the same inline style the file already uses for `_get_repository()` and `_github_client`.

## HOW / ALGORITHM

No new control flow. The access sits inside each tool's existing `try:`, so if
`_repo_identifier` itself raises (project_dir mode with no detectable remote) the tool still
degrades to `"Error: ..."` via the existing `except Exception` — no new failure mode.

## DATA

Error string shape, exactly:

```
Error: Could not access repository (tried https://api.github.com)
Error: Could not access repository (tried https://ghe.corp.com/api/v3)
Error: Could not access repository (tried https://gitlab.com/api/v3)
```

`api_base_url` comes from `RepoIdentifier.api_base_url`, which keeps its three existing
branches (`github.com` / `*.ghe.com` / GHES fallback). Nothing on that path is modified, so
GHE/GHES support cannot regress.

## TESTS (write first)

Extend the two existing tests rather than adding new ones — they already construct exactly the
`_get_repository() -> None` situation:

- `test_github_pr_view_no_repo`
- `test_github_search_no_repo`

In each, set the mock's identifier before calling:

```python
mock_mgr._repo_identifier.api_base_url = "https://gitlab.com/api/v3"
```

and add to the existing assertions:

```python
assert "https://gitlab.com/api/v3" in result
```

Keep the existing `assert "Error" in result` / `assert "repository" in result.lower()` lines —
they still hold and document the contract.

## LLM PROMPT

```
Implement step 2 of pr_info/steps/summary.md, specified in pr_info/steps/step_2.md.

Read pr_info/steps/summary.md (especially design decision 4) and pr_info/steps/step_2.md
before starting.

Work test-first:
1. In tests/github_operations/test_github_read_tools.py, extend test_github_pr_view_no_repo
   and test_github_search_no_repo as described under TESTS. Run pytest and confirm both fail.
2. In src/mcp_workspace/server.py, change the two "Error: Could not access repository"
   returns in github_pr_view and github_search to include the resolved API base URL.
3. Run pytest, pylint and mypy until all pass.

Do not add any host allowlist or denylist, and do not modify anything under
github_operations/ or utils/repo_identifier.py.

Then run mcp__mcp-tools-py__run_format_code and make exactly one commit.
```

## DONE WHEN

- Both extended tests pass; the rest of the file is untouched.
- pylint, pytest and mypy are green.
- The diff is two files and roughly four lines of production code.
