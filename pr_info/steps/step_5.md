# Step 5 — Approximate sub-issue count

## LLM prompt

> Read `pr_info/steps/summary.md` (section 2) and this file, `pr_info/steps/step_5.md`.
> Implement exactly this step with TDD: update the tests first, then the code.
> Run pylint, pytest (`-n auto`) and mypy; all must pass. Run format_code, then make one commit.

## WHERE
- `src/mcp_workspace/server.py` — `_subissue_write`, docstrings of `github_subissue_add` / `github_subissue_remove`
- `tests/github_operations/test_github_write_tools_subissues.py` — two exact-string assertions (≈ lines 99, 243)

## WHAT
No signature changes.

## HOW
- In `_subissue_write`:
  `count = "" if link.total is None else f" (~{link.total} sub-issues, may lag)"`
- Add a short comment: GitHub's `sub_issues_summary` lags after a write even on the refetch; counting via the
  list endpoint was rejected for its API cost.
- Docstrings, `Returns:` of both tools: `"... — <url> (~<N> sub-issues, may lag)"`, count approximate and
  omitted when unreadable; "Call github_subissue_list for the exact set."

## ALGORITHM
None.

## DATA
- Add: `"Linked #7 as a sub-issue of #3 — <url> (~2 sub-issues, may lag)"`
- Remove: `"Unlinked #7 from #3 — <url> (~1 sub-issues, may lag)"`

## Tests
Update the two expected strings to the new format. The existing "count omitted" test (≈ line 110) keeps working;
extend its negative assertion to `"sub-issues" not in result` if it only checks `"(0 sub-issues)"`.
