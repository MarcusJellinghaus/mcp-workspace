# review-implementation review log 1

## Round 1 — 2026-08-28
**Findings**:
I'll start by loading the tools I need and gathering context.I'll gather context in parallel: knowledge base files, the issue, plan files, and the branch diff.The issue is detailed. Now reading knowledge base, plan files, and computing the diff.There are real implementation changes. Reading the full diff of source and test files.Checks on the branch: pytest 1577 passed / 1 skipped, mypy clean, pylint clean.

`src/mcp_workspace/server.py:637` — medium — decision 4's diagnostic reaches only `github_pr_view` and `github_search`; a misconfigured reference project (e.g. a GitLab or unreachable URL) surfaces from `github_issue_view` as `"Error: Issue #N not found"` and from `github_issue_list` as an empty list, with no API base URL. This is the likeliest cross-repo misconfiguration and is fixable in `server.py` alone (check `_get_repository()` / include `_repo_identifier.api_base_url` on the empty-issue path) without touching `github_operations/`.
`src/mcp_workspace/server.py:718` — low — the three-line "could not access repository" block is duplicated verbatim at `server.py:806`; a small module-level helper would keep the two messages from drifting.
`src/mcp_workspace/server.py:592` — low — `_issue_manager` docstring has no `Raises:` section although its `ValueError` propagation is the load-bearing mechanism of the error-string contract (decision 3); `get_reference_repo_url` documents it, this one does not.
**Decisions**:
Verdict(decision='tasks', tasks=["In src/mcp_workspace/server.py, extend the decision-4 misconfiguration diagnostic to the issue tools: in github_issue_view, when the issue is not found, and in github_issue_list, when the result set is empty, include the resolved repository identity (e.g. _repo_identifier.api_base_url from _get_repository()) in the returned message so a GitLab or unreachable reference-project URL is distinguishable from a genuinely absent issue, instead of the bare 'Error: Issue #N not found' / empty list. Keep the change confined to server.py; do not modify github_operations/.", "Extract the three-line 'could not access repository' error block duplicated verbatim at src/mcp_workspace/server.py:718 and src/mcp_workspace/server.py:806 into a single module-level helper in server.py and call it from both sites so the two messages cannot drift.", "Add a 'Raises:' section to the _issue_manager docstring at src/mcp_workspace/server.py:592 documenting the ValueError it propagates, matching how get_reference_repo_url documents the same contract."], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-08-28
**Findings**:
I'll gather context first — loading the tools I need.All checks re-run on the branch: pytest 1579 passed / 1 skipped, mypy clean, pylint clean, ruff `D`/`DOC` clean (only pre-existing D104 on `__init__.py` packages).

`src/mcp_workspace/github_operations/formatters.py:93` — medium — `format_issue_list`'s `if not issues: return "No issues found."` branch is now unreachable from its only production caller: `server.py:719` short-circuits the empty case before calling it. Dead code created by this change; either drop the branch or keep the empty-case message in the formatter and pass the repo name to it.
`pyproject.toml:121` — medium — the new whole-file `DOC502` per-file-ignore for `server.py` was needed only for `_issue_manager` (the sole docstring in the module that documents a propagated rather than in-body `ValueError`); it now also permanently exempts the 14 pre-existing `Raises:` docstrings in that module from the check. A targeted `# noqa: DOC502` on `_issue_manager` gives the same result without disabling the rule module-wide. The accompanying comment ("tool wrappers document ValueError propagated from helpers") also misdescribes the cause — no tool wrapper in `server.py` documents `Raises`.
`src/mcp_workspace/server.py:721` — low — `github_issue_list()` with `reference_name` omitted now returns `"No issues found in owner/repo."` instead of `"No issues found."`, so the workspace path is not byte-for-byte unchanged as `pr_info/steps/summary.md` states; the deviation is deliberate (round-1 task) but is recorded nowhere in the design docs or README.
`.claude/CLAUDE.md:69` — low — the new "**Docstrings:** ... run `mcp__mcp-tools-py__run_ruff_check`" paragraph is unrelated to issue #255; `summary.md` scopes this file to the sibling-repo line only.
**Decisions**:
Verdict(decision='tasks', tasks=['In src/mcp_workspace/github_operations/formatters.py:93, resolve the dead `if not issues: return "No issues found."` branch created by this change: either remove the branch (since server.py:719 now short-circuits the empty case) or move the empty-case message back into the formatter by passing the repo name to it, so there is exactly one place that produces the empty-list message.', 'Replace the whole-file DOC502 per-file-ignore for server.py in pyproject.toml:121 with a targeted `# noqa: DOC502` on the `_issue_manager` docstring, so the 14 pre-existing `Raises:` docstrings in server.py stay covered by the rule; drop the inaccurate accompanying comment about tool wrappers documenting propagated ValueError.', 'Correct pr_info/steps/summary.md: the workspace (no `reference_name`) path of github_issue_list is no longer byte-for-byte unchanged — it now returns "No issues found in owner/repo." — so state the deliberate message change and its rationale instead of claiming the output is unchanged.', 'Revert the docstring/ruff-check paragraph added at .claude/CLAUDE.md:69; it is unrelated to issue #255 and outside the scope summary.md declares for this file.'], escalate_reason=None)
**Changes**:
applied

## Round 3 — 2026-08-28
**Findings**:
I'll gather context first — loading the tools I need.`src/mcp_workspace/server_reference_tools.py:44` — medium — `get_reference_projects()` docstring still describes the return as "projects: List of project names", but the tool returns `{"name": ..., "url": ...}` dicts; this diff corrected the adjacent usage line and README's equivalent bullet, leaving the MCP-visible discovery description as the only stale copy — and `url` is exactly what tells a caller whether `reference_name` is usable for that project.

`src/mcp_workspace/github_operations/formatters.py:96` — low — the `if repo_full_name else ""` fallback is unreachable from the only production caller: `server.py:718-722` returns `_repo_access_error()` when the name is `None` and otherwise passes a non-`None` value, so the bare `"No issues found."` string now exists only for `tests/github_operations/test_formatters.py:170`.
**Decisions**:
Verdict(decision='dismiss', tasks=[], escalate_reason=None)
**Changes**:
rebase-needed
**Escalate reason**: rebase
