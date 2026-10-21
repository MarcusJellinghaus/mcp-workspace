# Step 2 — `head_sha` on `PullRequestData`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_2.md` exactly.
> TDD: write the test first, see it fail, then change the code. Run pylint, pytest
> (`extra_args: ["-n", "auto"]`) and mypy; all must pass. Run `run_format_code`, then make one commit.

## WHERE

- `src/mcp_workspace/github_operations/pr_types.py` — `PullRequestData`
- `src/mcp_workspace/github_operations/pr_manager.py` — `_pr_to_data`
- `tests/github_operations/test_pr_manager.py` — `get_pull_request` tests

## WHAT

- `PullRequestData` gains `head_sha: Optional[str]`, placed after `head_branch`.
- `_pr_to_data(pr)` adds `"head_sha": pr.head.sha`.

## HOW

This is a plain field addition. `pr.head` is already loaded for `head_branch`, so it costs no extra
request. `_pr_to_data` is the only `PullRequestData` constructor. The dicts in `server.py`,
`test_formatters.py` and `test_base_branch.py` are not `PullRequestData` and need no change.
If mypy reports another place that builds a `PullRequestData` literal, add `head_sha` there too.
Add `- head_sha: Head commit SHA (str)` to the field list in the `create_pull_request` docstring.

## Tests (write first)

In `tests/github_operations/test_pr_manager.py`, add a test next to the existing
`get_pull_request` success test, using the same fixtures and mock style. Set
`mock_pr.head.sha = "abc123"` and assert `result["head_sha"] == "abc123"`. If any existing test
compares the full returned dict with `==`, add `head_sha` to its expected dict.

## DATA

`PullRequestData["head_sha"]` is a `str` (or `None` per the type) and is present in every
non-empty result of `get_pull_request`, `find_pull_request_by_head`, `list_pull_requests`, etc.
