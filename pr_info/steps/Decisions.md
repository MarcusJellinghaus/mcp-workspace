# Decisions

## Merge Step 2 and Step 3

Original plan had Step 2 (`formatters.py`) and Step 3 (`server.py`) as
separate commits. A prior implementation attempt got blocked partway
through Step 2: the full pytest suite requires `server.py` and
`formatters.py` to agree on the conversation-comment dict shape, but
`server.py` (Step 3's scope) wasn't touched yet, so
`test_github_pr_view_with_comments` failed with `KeyError: 'author'`.

Since each step is required to land with the full test suite green before
committing, and `server.py` is the only caller that builds the argument
`format_pr_view()` consumes, Steps 2 and 3 cannot be completed
independently — reordering them doesn't help either (it just flips which
side is incomplete).

Decision: merge Step 2 and Step 3 into a single step/commit covering both
files. Discussed and confirmed by Marcus on 2026-10-13.
