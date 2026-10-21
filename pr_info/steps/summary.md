# Summary — Issue #338: clearer Linked Branch wording; re-check and explain "unstable" when CI passed

## Goal

Two misleading lines in the `check_branch_status` report:

1. **Linked Branch `LINKED_VIA_PR`**: the line shows a raw enum name, doesn't say the check passed,
   and gives no reason for the fallback. New wording:
   `Linked Branch: OK via PR #335 — PR branch matches current branch '<full name>' (closes issue #329; no branch linked in the Development panel)`
2. **Stale `unstable`**: GitHub computes `mergeable_state` lazily, so right after CI finishes the PR
   can still read `unstable`. When CI is PASSED or NOT_CONFIGURED and the state is `unstable`, the
   tool now re-reads the PR once (after about 5 s). If it is still `unstable`, it lists the non-green
   checks and commit statuses on the head SHA and explains the result:
   - non-green checks found → names them;
   - none found → "likely stale, re-check";
   - lookup failed → "could not list checks: <reason>".

`unstable` still never produces `Ready to merge`. CI=FAILED + `unstable` (#207), `blocked` and
`dirty` behave exactly as before. Normal calls make no extra GitHub requests.

## Architectural / design changes

| Area | Change |
|---|---|
| `github_operations` — data | `PullRequestData` gains `head_sha` (`pr.head.sha`), set in `_pr_to_data`. No extra request. |
| `github_operations` — new capability | New mixin `PRChecksMixin` with `get_non_green_checks(pr_number, head_sha=None)`. It is the first `src/` code that reads check runs and commit statuses, apart from the permission probe. It is **not** wrapped in `_handle_github_errors`: it catches every error itself and sorts it into rate limit / permission / other, so it never raises. It returns a plain tuple `(names, error)`. |
| `checks.branch_status` — collection | New private helper `_recheck_unstable(...)`, called as step 9b of `collect_branch_status` (after `_collect_pr_info`, before `_apply_pr_merge_override`). It runs only on the CI=PASSED/NOT_CONFIGURED + `unstable` path. Inside: sleep `_UNSTABLE_REREAD_DELAY_SECONDS` (5.0), re-read via `get_pull_request`, accept the result only if it is a definite state, then run the lookup if the state is still `unstable`. The re-read is wrapped in a broad `except`, so it never breaks the report. |
| `checks.branch_status` — report | `BranchStatusReport` gains `non_green_checks: Optional[tuple[str, ...]] = None` and `non_green_checks_error: Optional[str] = None`. `None`/`None` means the lookup didn't run, and today's recommendation wording is used. `()` means the lookup ran and found nothing. |
| `checks.branch_status` — recommendations | `_generate_recommendations` builds the `unstable` text through a small helper `_merge_state_recommendation`. The new wording is used only when the lookup ran. `merge_state_blocked` is unchanged, so `Ready to merge` stays blocked. |
| `checks.branch_status_rendering` | New `format_check_names(names)` caps the list at 10 names plus `… and N more`; the recommendation and the line both use it. New `_format_non_green_checks_line(report)`, rendered in the human format after `Mergeable State:` and in the LLM format before `GitHub Label:`. New `LINKED_VIA_PR` wording in `_format_linked_branch_line`. The `LinkedBranchStatus.LINKED_VIA_PR` enum value is unchanged. |
| Skill docs | `.claude/skills/check_branch_status/SKILL.md`: the row key changes to `OK via PR`, and three rows are added for the new `unstable` outcomes. |

Design decisions kept deliberately simple (KISS):

- One re-read, no polling loop.
- `_collect_pr_info` is unchanged (its 5-tuple is patched by many tests). The head SHA comes from
  the re-read; if the re-read failed, the lookup resolves it from `pr_number`.
- The re-read helper lives in `branch_status.py` (it ends up at about 720 lines, under the
  750-line CI limit) instead of a new module.
- The "lookup ran" signal is the two report fields, so there is no extra flag.

## Files created / modified

### Created
- `src/mcp_workspace/github_operations/pr_checks_mixin.py` — `PRChecksMixin.get_non_green_checks`
- `tests/github_operations/test_pr_checks_mixin.py`
- `tests/checks/test_branch_status_unstable_recheck.py`
- `tests/checks/test_branch_status_non_green_checks.py`

### Modified
- `src/mcp_workspace/checks/branch_status_rendering.py` — Linked Branch wording, `format_check_names`, `Non-green checks:` line
- `src/mcp_workspace/checks/branch_status.py` — report fields, `_merge_state_recommendation`, `_recheck_unstable`, wiring
- `src/mcp_workspace/github_operations/pr_types.py` — `head_sha`
- `src/mcp_workspace/github_operations/pr_manager.py` — `head_sha` in `_pr_to_data`; `PRChecksMixin` added to bases
- `tests/checks/test_branch_status_linked_branch.py` — per-state prefix, new wording
- `tests/checks/test_branch_status_recommendations.py` — new `unstable` recommendation texts
- `tests/github_operations/test_pr_manager.py` — `head_sha`
- `.claude/skills/check_branch_status/SKILL.md`

## Steps

1. Linked Branch wording + SKILL.md `OK via PR` row
2. `head_sha` on `PullRequestData`
3. `PRChecksMixin.get_non_green_checks`
4. Report fields, recommendation wording, `Non-green checks:` line, SKILL.md unstable rows
5. `_recheck_unstable` wired into `collect_branch_status`

Every step is one commit: tests + implementation. Before committing, run pylint, pytest
(`extra_args: ["-n", "auto"]`), mypy and `run_format_code`; all must pass.
