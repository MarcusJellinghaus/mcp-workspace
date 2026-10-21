# Summary — #321 Surface malformed "Base Branch" as data, stop falling back silently

## Goal

A multi-line `### Base Branch` section is **data**, shown where it is acted on, and never
silently replaced by a guessed base (PR / merge-base / default branch).

Today `IssueManager.get_issue`/`list_issues` log a WARNING and set `base_branch=None`, so
every consumer falls through to a guessed base. Additionally the parser matches a heading
inside a fenced code block, the warning is logged repeatedly, the rebase recommendation names
the default branch instead of the detected base, and `github_pr_create` defaults to the repo
default branch.

## Architectural / design changes

| Area | Before | After |
|---|---|---|
| Parser (`issues/base.py`) | Regex over raw text; fenced/quoted headings match | `markdown-it-py` (CommonMark) tokens; only top-level ATX headings (`#`-markup, `level == 0`) start/end a section; section content still read from raw source lines → multi-line check unchanged |
| Error text | Built inline in `server._check_base_branch` | One helper `format_malformed_base_branch(exc)` returns the bare sentence; callers add their own prefix |
| `IssueData` | `base_branch` only | + `base_branch_error: NotRequired[Optional[str]]` (helper sentence when malformed, else `None`) |
| Manager logging | WARNING every parse | One helper `_parse_base_branch_fields` used by `get_issue` and `list_issues`; WARNING once per `(repo, issue, message)` per process, DEBUG afterwards |
| `detect_base_branch` (`git_operations`) | Optional `issue_manager` → may fetch the issue itself (double fetch) | **`issue_manager` parameter and fetch path removed**; it only reads `issue_data`. Callers fetch the issue once and check `base_branch_error` *before* calling it. Layering kept: `git_operations` never sees the malformed state, never imports upward |
| Origin existence check | Private `_origin_still_has_branch -> Optional[bool]` (swallows errors) | Public `origin_has_branch(project_dir, name) -> bool`, raises on network/auth failure; merge-base caller catches inline |
| Server (`server.py`) | `get_base_branch` and `github_pr_create` each pick a base independently (`main` fallback / default branch) | One helper `_resolve_base_branch(project_dir, branch, pr_manager) -> tuple[Optional[str], Optional[str]]` = `(base, error)`; error is the ready `Error: issue #N: <sentence>` string |
| `get_base_branch` | Returns `main` on any failure | Malformed → `Error: issue #N: …`; otherwise as before |
| `github_pr_create` | `base` defaults to repo default branch | `base` resolved for `head` (issue → PR → merge-base → default), then verified on origin via `ls-remote`; four distinct `Error:` results, nothing created on error |
| `BranchStatusReport` | `rebase_needed: bool` | `rebase_needed: Optional[bool]` (`None` = UNKNOWN) + new `base_branch_error: Optional[str]` field |
| `check_branch_status` | Malformed invisible; base guessed | `Base: MALFORMED (issue #N: '<first line>')`, `Rebase=UNKNOWN`, fix recommendation, no `Ready to merge`, Review Gate `BLOCKED (base branch)` (before `BLOCKED (linked branch)`) |
| Rebase recommendation | `Rebase onto origin/<default branch>` | `Rebase onto origin/<detected base>` (`Pull origin/<default>` on the default branch is unchanged) |

### Decisions taken during planning (beyond the issue text)

- **`issue_manager` removed from `detect_base_branch`** instead of every caller passing
  `issue_manager=None`. All three callers fetch the issue themselves; `mcp_coder` has its own
  `detect_base_branch` and does not call this one. Scope 5 ("never re-fetch when `issue_data`
  was passed") then holds by construction.
- **`Pull origin/<default>` stays on the default branch.** Only the `Rebase onto …`
  recommendation switches to the detected base (on the default branch the thing to pull is the
  branch itself).
- `get_base_branch` maps "no base detected" to `"main"` exactly as today.
- `_resolve_base_branch` returns a `(base, error)` tuple — no new result type.

## Files

### Created

- `tests/github_operations/issues/test_parse_base_branch_markdown.py` — new parser cases (step 1)
- `tests/github_operations/issues/test_manager_base_branch.py` — `base_branch_error` + log-once (step 3)
- `tests/test_server_get_base_branch.py` — `_resolve_base_branch` + `get_base_branch` (step 5)
- `tests/github_operations/test_github_pr_create_base.py` — default-base resolution (step 7)
- `tests/checks/test_branch_status_base_branch.py` — tri-state rebase + malformed state (steps 8, 9)

### Modified

- `pyproject.toml` — `markdown-it-py` in `dependencies`
- `src/mcp_workspace/github_operations/issues/base.py` — parser rewrite, message helper
- `src/mcp_workspace/github_operations/issues/types.py` — `IssueData.base_branch_error`
- `src/mcp_workspace/github_operations/issues/manager.py` — `_parse_base_branch_fields`, log-once
- `src/mcp_workspace/git_operations/base_branch.py` — drop `issue_manager`; public `origin_has_branch`
- `src/mcp_workspace/server.py` — `_check_base_branch` via helper, `_resolve_base_branch`, `get_base_branch`, `github_pr_create`
- `src/mcp_workspace/checks/branch_status.py` — tri-state rebase, malformed state, recommendations
- `src/mcp_workspace/checks/branch_status_rendering.py` — UNKNOWN rendering, Review Gate
- `tests/test_startup_performance.py` — assert `markdown_it` not imported at startup
- `tests/test_server_enforce_base_branch_format.py`, `tests/github_operations/test_github_write_tools_issue_edit_base_branch.py` — fenced heading accepted on write
- `tests/github_operations/conftest.py` — autouse reset of the log-once set
- `tests/git_operations/test_base_branch.py`, `tests/git_operations/test_base_branch_git.py`
- `tests/github_operations/test_github_write_tools_labels_pr.py` — patch targets for the default-base path
- `tests/checks/test_branch_status_recommendations.py`, `tests/checks/test_branch_status_review_gate.py`

## Steps

1. Parser on markdown-it-py (+ dependency, startup assertion)
2. Shared message helper; `_check_base_branch` uses it; fenced heading accepted on write
3. `IssueData.base_branch_error` + log-once in the manager
4. Public `origin_has_branch`
5. Server helper `_resolve_base_branch` + `get_base_branch`
6. Remove `issue_manager` from `detect_base_branch` (no double fetch)
7. `github_pr_create` default base
8. Tri-state `rebase_needed`; rebase recommendation names the detected base
9. Malformed state in `check_branch_status` (+ Review Gate)

Every step: tests first, then implementation, then `run_pylint_check`, `run_pytest_check`
(`extra_args: ["-n", "auto"]`), `run_mypy_check` all green, `run_format_code`, one commit.
