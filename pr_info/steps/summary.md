# Issue #320 — Reject malformed "Base Branch" section when creating/editing issues

## Problem

`parse_base_branch` (`github_operations/issues/base.py`) raises `ValueError` when a
`### Base Branch` section spans more than one line. Today that only surfaces inside
`IssueManager`, which catches the error, logs a WARNING, and silently drops the base
branch — so a malformed section written through `github_issue_create` /
`github_issue_edit` is accepted and the data loss is discovered only later, by a
reader (e.g. `vscodeclaude status`).

## Goal

Reject the malformed section at write time, in `github_issue_create` and
`github_issue_edit`, before any network call — behind a default-on flag.

## Architecture / design changes

- **New exception type**: `MalformedBaseBranchError(ValueError)` in
  `github_operations/issues/base.py`, carrying the raw section `content` on the
  instance. `parse_base_branch` raises this instead of a bare `ValueError` on the
  multi-line case. Because it subclasses `ValueError`, `IssueManager`'s existing
  `except ValueError` is unaffected — no behavior change there. Re-exported from
  `issues/__init__.py` for reuse by #321 (the read-side companion issue, out of
  scope here).
- **One shared validation helper** in `server.py`, `_check_base_branch(body)`,
  placed next to the existing `_check_labels` helper. Both `github_issue_create`
  and `github_issue_edit` call it so the two tools cannot drift apart. The helper:
  - short-circuits to "no error" when the server-wide flag is off, or when
    `parse_base_branch` finds no section / an empty section / a valid one-line
    value (parser behavior for those three outcomes is unchanged by this issue).
  - on `MalformedBaseBranchError`, returns a fixed-text error naming the problem
    and the fix, plus the section's first line (`exc.content.splitlines()[0]`,
    not `split("\n")[0]`, so a CRLF section does not leak a trailing `\r`).
  - is safe to call unconditionally with `body` possibly `None` (as in
    `github_issue_edit` when the caller omits `body`) — `parse_base_branch("")`
    already returns `None` for empty/missing input, so no separate
    `if body is not None` guard is needed at the call sites; both tools call the
    helper identically.
  - imports `parse_base_branch` / `MalformedBaseBranchError` lazily inside the
    function body, matching the rest of `server.py`'s PyGithub-avoidance pattern
    (enforced by `tests/test_startup_performance.py`).
  - runs before `_issue_manager(...)` is constructed in both tools — a rejected
    call makes no network call and leaves the issue unchanged.
- **New server-wide flag**, `--enforce-base-branch-format` /
  `--no-enforce-base-branch-format` (`argparse.BooleanOptionalAction`,
  default `True`), plumbed exactly like the existing `--fail-on-reviews` flag:
  `main.py` argparse → `run_server(..., enforce_base_branch_format=True)` →
  `set_enforce_base_branch_format(value)` → module global
  `_enforce_base_branch_format` in `server.py`. Unlike `fail_on_reviews`, both the
  module global and the `run_server` parameter default to `True`, so the check is
  on whenever `run_server` is called without the kwarg.
- The check applies identically to the workspace repository and to reference
  projects (`reference_name`) — one server-wide flag, no per-repo override.
- Docstrings of both tools gain a line about the new rejection; `README.md`'s
  usage synopsis and flag bullet list gain the new flag (and the already-missing
  `--fail-on-reviews` bullet, fixed in the same edit).

## Out of scope

- #321 (read-side): exposing malformed state on `IssueData` / `check_branch_status`.
  This plan only adds `MalformedBaseBranchError` for #321 to reuse later.
- Validating that a well-formed single-line value is an actual branch name.

## Folders / modules / files touched

| Path | Change |
|---|---|
| `src/mcp_workspace/github_operations/issues/base.py` | add `MalformedBaseBranchError`; `parse_base_branch` raises it |
| `src/mcp_workspace/github_operations/issues/__init__.py` | re-export `MalformedBaseBranchError` |
| `src/mcp_workspace/server.py` | module global + setter + `_check_base_branch` helper + wiring into `github_issue_create` / `github_issue_edit` + `run_server` param |
| `src/mcp_workspace/main.py` | new `--enforce-base-branch-format` / `--no-enforce-base-branch-format` flag, pass-through to `run_server` |
| `tests/github_operations/issues/test_base.py` | tests for `MalformedBaseBranchError` |
| `tests/test_server_enforce_base_branch_format.py` | **new** — flag plumbing tests + `_check_base_branch` helper tests |
| `tests/test_main.py` | **split out of `tests/test_reference_projects.py`** (file-size limit; tests now mirror `main.py` / `server.py` / `server_reference_tools.py`: `test_main.py`, `test_main_validate_reference_projects.py`, `test_server_reference_tools.py`, `run_server` test in `test_server.py`). New `parse_args` tests + `main()` pass-through tests for the new flag |
| `tests/github_operations/test_github_write_tools_issues.py` | new tests for `github_issue_create` rejection/acceptance |
| `tests/github_operations/test_github_write_tools_issue_edit.py` | new tests for `github_issue_edit` rejection/acceptance |
| `README.md` | usage synopsis + flag bullet list |

No other files are expected to change. `tests/github_operations/issues/test_manager.py`
and `tests/test_startup_performance.py` must stay green **unmodified** — they are the
two "nothing else changed" guarantees for this issue.

## Steps (one commit each)

1. `step_1.md` — `MalformedBaseBranchError` in `issues/base.py` + re-export.
2. `step_2.md` — `--enforce-base-branch-format` flag plumbing (unused by any tool yet).
3. `step_3.md` — `_check_base_branch` helper in `server.py` (unit-tested directly, not yet wired into a tool).
4. `step_4.md` — wire the helper into `github_issue_create`.
5. `step_5.md` — wire the helper into `github_issue_edit`.
6. `step_6.md` — README documentation update.

Every step ends with: `mcp__mcp-tools-py__run_format_code`, then
`mcp__mcp-tools-py__run_pylint_check`, `mcp__mcp-tools-py__run_pytest_check`
(`extra_args: ["-n", "auto"]`), `mcp__mcp-tools-py__run_mypy_check` all passing,
then one commit via the approved Bash `git add` / `git commit`.
