# Summary — Issue #342: fence and label untrusted issue text; ignore untrusted Base Branch

## Goal

Issue tools print issue text verbatim, and the issue's `### Base Branch` section
picks the rebase target / PR base, whoever wrote it. After this change:

- `github_issue_view` fences untrusted title/body/comments with a per-call random
  delimiter and adds a summary line under the State line.
- `github_issue_list`, `github_search`, `github_subissue_list` prefix untrusted rows
  with `[untrusted @login]`.
- `IssueManager.get_issue` / `list_issues` return `base_branch = base_branch_error = None`
  when the body is untrusted, so every consumer (check_branch_status, get_base_branch,
  mcp_coder) falls through to PR base / merge-base / default branch.
- `### Base Branch` values must be valid git ref names, for every author, at read and
  write time.

Trust rule: unchanged from #336 (`is_trusted_author`, `get_trusted_commenters`,
`normalize_author_association`).

## Architectural / design changes

1. **`IssueData.author_association: Optional[str]` — required key.** Same pattern as
   `CommentData` (#336); mypy finds every construction site. The PyGithub → `IssueData`
   conversion moves into `issues/types.py` as `issue_to_data()` so `manager.py` and
   `labels_mixin.py` share one converter (no circular import: both already import
   `types.py`).
2. **Base Branch gate lives in the library, not the tools.** New module
   `issues/base_branch_trust.py` decides whether a body may choose the base branch:
   author trusted (role, then allowlist) **or** last body editor trusted (token user or
   allowlist). The editor comes from one GraphQL query, run only when the author is
   untrusted **and** the body has a Base Branch section. The trust check never raises:
   any lookup failure means "untrusted".
   `manager.py` calls it from one shared `_parse_base_branch_fields` used by `get_issue`
   and `_list_issues_no_error_handling`. The allowlist is read lazily, at most once per
   manager call (`functools.cache(config.get_trusted_commenters)`).
3. **Ref-name validation inside `parse_base_branch`.** New
   `InvalidBaseBranchRefError(MalformedBaseBranchError)`; `format_malformed_base_branch`
   picks the message by type. Every existing `except MalformedBaseBranchError` site
   (IssueManager, `_malformed_first_line`, write-time `_check_base_branch`) inherits it
   with no code change.
4. **Display labelling stays in pure formatters.** `format_issue_view`,
   `format_issue_list`, `format_search_results` take a required keyword
   `trusted: frozenset[str]`; `format_issue_view` also takes `fence_id: str`. One shared
   `untrusted_prefix()` helper serves all three list tools. Server tools read the
   allowlist only when some author's role is untrusted (`_allowlist_for`), and generate
   the fence id with `secrets.token_hex(8)` once per call.
5. **Withholding vs. labelling.** PR feedback stays withheld (#336); issue text is shown
   but fenced, because an untrusted issue *is* the request being analysed.

## Files

Created:
- `src/mcp_workspace/github_operations/issues/base_branch_trust.py`
- `tests/github_operations/issues/test_base_branch_trust.py`

Modified (source):
- `src/mcp_workspace/github_operations/issues/base.py` — ref validator, new error, message
- `src/mcp_workspace/github_operations/issues/types.py` — `author_association`, `issue_to_data`
- `src/mcp_workspace/github_operations/issues/manager.py` — use `issue_to_data`, gate
- `src/mcp_workspace/github_operations/issues/labels_mixin.py` — use `issue_to_data`
- `src/mcp_workspace/github_operations/formatters.py` — fence, summary line, prefix
- `src/mcp_workspace/server.py` — trusted/fence_id wiring, search item fields, sub-issue prefix
- `README.md` — `--enforce-base-branch-format`, trust section

Modified (tests):
- `tests/github_operations/_issue_test_helpers.py` — `author_association="OWNER"` default
- `tests/github_operations/issues/test_base.py`
- `tests/github_operations/issues/test_types.py`
- `tests/test_server_enforce_base_branch_format.py`
- `tests/github_operations/test_github_write_tools_issues.py`
- `tests/github_operations/test_github_write_tools_issue_edit_base_branch.py`
- `tests/checks/test_branch_status_base_branch.py`
- `tests/test_server_get_base_branch.py`
- `tests/github_operations/issues/test_manager_base_branch.py`
- `tests/github_operations/test_formatters.py`
- `tests/github_operations/test_github_read_tools_issues.py`
- `tests/github_operations/test_github_search_tool.py`
- `tests/github_operations/test_github_write_tools_subissues.py`
- every test `IssueData(...)` construction site mypy reports (`_github_read_tools_helpers.py`,
  `test_github_write_tools_*.py`, `issues/test_cache_additional.py`,
  `git_operations/test_base_branch.py`, …)

## Steps

1. [step_1.md](./step_1.md) — Ref-name check for `### Base Branch` (read and write time) + README flag line
2. [step_2.md](./step_2.md) — `IssueData.author_association` + shared `issue_to_data`
3. [step_3.md](./step_3.md) — `base_branch_trust.py`: editor lookup + body trust decision
4. [step_4.md](./step_4.md) — Base Branch gate in `IssueManager`
5. [step_5.md](./step_5.md) — Fenced `format_issue_view` + summary line
6. [step_6.md](./step_6.md) — `[untrusted @login]` prefix in list/search/sub-issue tools + README trust section

Each step = one commit: tests first, then implementation, then pylint / pytest
(`-n auto`) / mypy all green, then `run_format_code` before committing.

## Out of scope

- mcp_coder mypy fixes for the new required key (MarcusJellinghaus/mcp_coder#1275).
- Forcing a cache refresh: stale entries lack `author_association` and self-heal at the
  next full refresh; readers use `.get("author_association")`.
