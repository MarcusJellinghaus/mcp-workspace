# review-implementation review log 2

Issue #268 — check_branch_status: verify the issue's linked branch matches the
current branch.

Run 2 opens after run 1 escalated: a one-line isort revert at
`src/mcp_workspace/server.py:37` was tasked in rounds 3, 4 and 5 and recorded as
applied each time, but no commit ever carried it. Verified before this run: the
parenthesized three-line form is still on the branch, and `origin/main` has
since moved ahead (it added `reference_name` support to `server.py`), so a
`git diff origin/main` on that file no longer isolates the stray edit.

## Round 1 — 2026-08-31

**Findings**

1. `src/mcp_workspace/server.py:37` — critical — out-of-scope parenthesized
   single-name import still on the branch; sole cause of the red isort CI job.
2. `pr_info/steps/` committed — medium — CI's `check-forbidden-folders` job is
   gated on `pull_request`, so it has never run; it forbids `pr_info/steps` and
   will fail once a PR is opened.
3. Branch is 3 commits behind `origin/main` (`82e6b5a`, `308a8e8`, `ad702ca`) —
   medium — rebase needed; no expected conflicts.
4. `pr_info/commit_message.txt` — low — transient artifact committed; the
   undotted name slips past both `.gitignore:48` and `ci.yml:82`.
5. `branch_status_rendering.py`, MISMATCH branch of `_format_linked_branch_line`
   — low — empty-tuple fallback would render `links ''`; unreachable from
   `_collect_linked_branch_status`.
6. `branch_status_rendering.py:219-233`, `:267` — low — the compact
   `Branch Status:` line and the `Summary: … | Action: …` footer omit the
   linked-branch state.
7. `linked_branches_mixin.py:147` — low — `get_linked_branches_or_none` takes a
   bare `self` plus `cast("BaseGitHubManager", self)`, while its siblings
   annotate `self` directly.
8. `checks/branch_status.py` at 688 lines — low — under CI's 750 limit, above
   the local 600 default.

Local checks were clean throughout: pylint, mypy strict, pytest 2158 passed /
2 skipped, lint-imports 9/9, vulture silent.

**Decisions**

- **1 — accept.** Red CI, and the plan lists `server.py` as deliberately
  unchanged.
- **2, 4 — skip.** `pr_info/` is removed later in the workflow by design
  (knowledge base: "*pr_info/ folder — deleted later during the process*"), so
  both resolve themselves before the PR exists.
- **3 — not a code finding.** Reported as branch state; a rebase is the user's
  call, not a review fix.
- **5 — skip.** Unreachable defensive path; speculative under the knowledge
  base's "only matters when someone makes a future mistake" rule.
- **6 — skip.** The plan decided the message lives on the render line and the
  gate header, with recommendations deliberately falling through to `Continue
  with current work` ("No new recommendation string"). Adding it to the summary
  line would reverse an agreed decision, not fix a defect.
- **7 — accept.** Bounded consistency fix inside a module this branch created.
- **8 — skip.** Under the CI limit, and the plan predicted ~660 lines.

**Changes**

- `server.py:37` collapsed back to the single-line
  `from mcp_workspace.server_reference_tools import set_reference_projects`.
- `get_linked_branches_or_none` now annotates `self: "BaseGitHubManager"`; the
  redundant `cast` and the now-unused `cast` import were dropped.
- `pr_info/TASK_TRACKER.md`: corrected the false "local isort conflicts with CI"
  note that had steered three rounds away from the formatter.

**Root cause of the four-round loop.** The tracker's claim that the local isort
rewrites the single-line import back into parentheses is false. `[tool.isort]`
in `pyproject.toml` is `profile = "black"`, `line_length = 88`,
`float_to_top = true` — exactly what CI passes on its command line, so
`run_format_code` and CI's `isort --check` are equivalent. Confirmed
empirically: the fix was applied, `run_format_code` was run, and the line was
not re-broken. The three earlier "applied" reports never wrote the edit at all.
A second trap compounded it: `git diff origin/main -- src/mcp_workspace/server.py`
was being used as the verification check, but the branch is behind `main`, so
that diff is dominated by main's newer `reference_name` work. Both this round's
review and its fix were verified against the merge-base and against the
committed blob (`git show HEAD:…`) rather than the working tree.

**Status**: committed as `216900a` and pushed.

## Round 2 — 2026-08-31

**Findings**

Round 1's two fixes were confirmed present in the committed blob (`216900a`),
and **CI went green** — run `33414599619` on `216900a` succeeded, with the isort
job that had failed on the four preceding pushes now passing. Local checks
clean: pylint, mypy strict, pytest 2158 passed / 2 skipped, lint-imports 9/9,
vulture silent. Two new findings, both low:

1. `github_operations/issues/base.py:47` — low — `validate_issue_number_or_log`
   re-implements the `not isinstance(issue_number, int) or issue_number <= 0`
   predicate that `validate_issue_number` already carries at `:33`, instead of
   delegating to it.
2. `github_operations/issues/linked_branches_mixin.py:116` — low — the parse
   guard catches `(KeyError, TypeError)`, but a GraphQL error response shaped
   `{"data": None, "errors": [...]}` makes the response walk raise
   `AttributeError` and escape it. Outcome was still correct via the broad
   catch, so this was a lost diagnostic rather than a behaviour bug. The
   reviewer flagged the reachability half as reasoning, not measurement.

**Decisions**

- **1 — accept.** DRY, two copies of one rule in a single module, and the
  duplication was introduced when this branch promoted the validator into
  `base.py`.
- **2 — accept.** `pr_info/steps/summary.md` names "parse error" as one of the
  four *in-body* paths that should map to `UNKNOWN`, so it belongs in the
  in-body guard where it is logged as a parse failure. Required the engineer to
  measure the claim with a scratch probe before acting on it, rather than
  inheriting the reviewer's reasoning.

**Changes**

- `validate_issue_number_or_log` now delegates to `validate_issue_number` inside
  `try` / `except ValueError`; return values and log message byte-identical,
  `test_base.py` unchanged and still passing.
- The parse guard in `_query_linked_branches` is now
  `except (AttributeError, KeyError, TypeError)`.
- Added `test_graphql_error_response_returns_none_from_the_in_body_handler`,
  which feeds the full `{"data": None, "errors": [...]}` payload to
  `get_linked_branches_or_none` and pins the result to the in-body branch via
  the log-message pair (`"Error parsing GraphQL response"` present, `"Failed to
  query linked branches"` absent) — so the test fails if the `AttributeError`
  is reverted. No existing assertion weakened; `test_graphql_error_handling`
  (which asserts `[]` through `get_linked_branches`) still holds.

**Probe result.** A `.scratch/` probe drove the walk
`result.get("data", {}).get("repository", {}).get("issue")` against
`{"data": None, "errors": [...]}` and asserted both `isinstance(exc,
AttributeError)` and `not isinstance(exc, (KeyError, TypeError))`. It passed —
the payload measurably raised `AttributeError: 'NoneType' object has no
attribute 'get'` and did escape the old guard. `.scratch/` was deleted.

`delete_linked_branch` carries an identically shaped guard and was deliberately
left alone — pre-existing and outside #268.

**Status**: committed as `6146102` and pushed.

## Round 3 — 2026-08-31

**Findings**: none. Both `6146102` fixes confirmed in the committed blob, and
the new test was shown to fail on revert by measurement rather than reasoning: a
probe loaded a copy of the mixin with `AttributeError` stripped from the guard,
confirmed the exception then escapes `_query_linked_branches` into
`get_linked_branches_or_none`'s broad catch, which logs `"Failed to query linked
branches for #123"` — the exact string the new test asserts is absent.

`server.py` no longer appears in `git diff b9106c4..HEAD --stat` at all, so it is
identical to the merge-base. **CI green** on `6146102` (run `33416265963`): every
job passed; `check-forbidden-folders` is `skipped`, still `pull_request`-gated.

Also verified as sound: the mixin extraction is lossless (all 8
`TestGetLinkedBranches` and all 12 `TestDeleteLinkedBranch` cases survive, the
latter moved intact to `test_branch_manager_unlink.py`); `_collect_linked_branch_status`
is called exactly once per report and is not inside the polling loop, so the two
extra requests are not multiplied; the `@patch` stacks bind in the right order in
all nine test sites; every state that blocks also renders a reason line, pinned
by `test_every_blocking_state_renders_a_reason`; and `branch_status_rendering.py`
has no `__all__`, so mcp_coder can import `LinkedBranchStatus` as the plan's
out-of-scope note assumes.

**Decisions**: nothing to accept — zero code changes, so the review loop ends.

**Status**: no changes needed.

## Final Status

**Review loop closed after 3 rounds** (run 2; run 1 had escalated after 5).
Two commits produced:

| Commit | Content |
|---|---|
| `216900a` | `server.py:37` reverted to the single-line import; `get_linked_branches_or_none` annotates `self`; TASK_TRACKER's false isort note corrected |
| `6146102` | `validate_issue_number_or_log` delegates to `validate_issue_number`; parse guard catches `AttributeError`; new in-body parse-error test |

**Final gates** (run by the supervisor):

- `run_vulture_check` — no output.
- `run_lint_imports_check` — PASSED, 9 contracts kept, 0 broken. No
  architectural violation to escalate.
- `check_branch_status` — `CI=PASSED, Rebase=BEHIND, Tasks=COMPLETE (All 9
  tasks complete), PR=NOT_FOUND`, label `status-07:code-review`.

**What unblocked the five-round stall.** Two compounding measurement errors, not
a hard problem. First, `pr_info/TASK_TRACKER.md` asserted that the local isort
rewrites the single-line import back into parentheses and that `run_format_code`
must therefore not be run — false; `[tool.isort]` is `profile = "black"`,
`line_length = 88`, `float_to_top = true`, exactly what CI passes, and the
formatter was empirically shown to leave the line alone. Second, verification
was being done with `git diff origin/main -- src/mcp_workspace/server.py`, but
the branch is behind `main`, so that diff is dominated by main's newer
`reference_name` work and could not isolate the stray edit. Every fix in run 2
was verified against the merge-base and against the committed blob
(`git show HEAD:…`), never the working tree.

**End-to-end sanity check.** The live `check_branch_status` tool renders no
`Linked Branch:` line on this branch, which would be the exact silent-green
failure #268 exists to prevent. Investigated and cleared: the MCP server runs a
non-editable installed build from a shared venv
(`C:\Jenkins\environments\mcp-coder-dev\.venv`, version
`0.1.13.dev35+g82e6b5a00`) that predates this work, while `.mcp.json` points the
server at the venv and only `--project-dir` at this checkout. The source in this
tree is correctly wired — both formatters append the line's return value, and a
probe on a report with `linked_branch_status=OK` measurably produces
`Linked Branch:` in the output. The feature will surface once the build is
refreshed.

**Open, for the user — not defects:**

1. **Rebase needed.** The branch is 3 commits behind `origin/main` (`82e6b5a`,
   `308a8e8`, `ad702ca`). None touches `checks/` or `github_operations/issues/`,
   so a clean rebase is expected.
2. **`pr_info/` must come off before the PR.** CI's `check-forbidden-folders` job
   is `pull_request`-gated, so it has never run on this branch; `ci.yml:76`
   forbids `pr_info/steps`, and `origin/main` carries no `pr_info/` tree. This is
   the workflow's normal cleanup step, not a review finding.
3. **`tests/test_startup_performance.py::test_server_startup_under_two_seconds`
   is flaky under `-n auto`** (median 2.228s against a 2.0s budget); it passes
   3/3 when run alone and passes in CI. Pre-existing timing sensitivity — this
   branch adds no module-level import to the startup path.
4. **Noted, no action taken.** A digit-prefixed non-issue branch such as
   `2024-05-release` is matched by the pre-existing
   `extract_issue_number_from_branch` regex `^(\d+)-`, so it now resolves to
   `UNKNOWN` and blocks the merge verdict where before it only degraded the
   status label. This follows from the pre-existing extractor rather than from
   #268's code, the repo convention is `<issue>-<slug>`, and the rendered message
   stays neutral.
