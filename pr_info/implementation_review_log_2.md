# review-implementation review log 2

Issue: #272 — `reference_name` for the GitHub issue write tools and `github_label_list`
Started: 2026-08-30

Follow-up run to `implementation_review_log_1.md`, whose round 3 produced no findings but
flagged a rebase need.

## Round 1 — 2026-08-30

**Findings**:
- `src/mcp_workspace/server.py:37-39` — **critical** — the `set_reference_projects` import was
  reformatted into a parenthesized multi-line form. Functionally inert and unrelated to #272,
  but it fails the CI isort job (`isort --check --profile=black --float-to-top src tests`):
  the single-line form fits in 88 chars, while the magic trailing comma stops black from
  unwrapping it. The only red CI job. Raised as a low-severity nit in rounds 1 and 2 of
  `implementation_review_log_1.md` but never added to either round's task list, so it survived.
- `.claude/skills/issue_approve/SKILL.md:5-11` — low — the Cross-Repo Issues section instructs
  the agent to call `get_reference_projects()`, but `mcp__mcp-workspace__get_reference_projects`
  is absent from the frontmatter `allowed-tools`. Pre-existing from #255.
- `.claude/skills/issue_approve/SKILL.md:27` — low — the opening clause "If a `--repo owner/repo`
  flag was given, append it to every `gh` command below" now sits directly above the new
  MCP-first guidance, so it reads as though `gh` were still the default path.

**Decisions**:
- Finding 1: **accept** — merge blocker, and pure diff noise the issue never asked for.
- Finding 2: **accept** — pre-existing, but step 5 makes that lookup load-bearing for the new
  cross-repo write path, and it is a one-line Boy Scout fix in a file this PR already touches.
- Finding 3: **accept** — step 5 reworded the prose immediately beneath it; leaving the clause
  contradictory is exactly the stale-guidance failure #272 was filed against.

Nothing skipped this round.

**Changes**:
- `src/mcp_workspace/server.py` — import restored to its single-line form; `run_format_code`
  confirms it survives isort and black.
- `.claude/skills/issue_approve/SKILL.md` — `get_reference_projects` added to `allowed-tools`;
  Cross-Repo Issues opening reworded so the MCP `reference_name` route is the default and the
  `gh --repo owner/repo` form the fallback. The `gh` fallback commands themselves are unchanged.

Checks: pylint pass, mypy pass, pytest 1744 passed / 1 skipped. `test_startup_performance.py::
test_server_startup_under_two_seconds` fails on this host under load; verified environmental —
it fails identically with the change reverted.

**Status**: committed as `2f0c824`, pushed.

## Round 2 — 2026-08-31

**Findings**: NO FINDINGS.

Round-1 fixes verified as landed in `2f0c824`: the single-line import no longer appears in the
branch diff at all, `get_reference_projects` is in `allowed-tools`, and the Cross-Repo Issues
section leads with the MCP `reference_name` route with `gh` explicitly the fallback. The
`implementation_review_log_1.md` fixes were re-verified as correct rather than merely present
(`_ref_suffix` on the second edit-failure sentinel, `_login_cache` keyed on `api_base_url` with
a per-host test, `github_label_list`'s empty result naming the project).

Two items examined and deliberately not raised:
- `server.py:1357` (`failed_before_write`) carries no `_ref_suffix`, but the following line
  appends the issue URL — covered by the plan's "success paths already return a URL" rule.
- `README.md:460` "these eight tools" is scoped to the GitHub tools by its section heading;
  `git()` and the reference file tools also take a reference name. Same phrasing pattern as
  the line it replaces. Nit only.

**Decisions**: nothing to accept or skip.

**Changes**: none.

**Status**: no changes needed — review loop complete.

## Final Status

Two rounds. Round 1 found one merge blocker (the isort-breaking import, twice raised and never
tasked in the previous run) plus two `issue_approve/SKILL.md` fixes, all applied and committed
as `2f0c824`. Round 2 found nothing.

- pylint: pass (needs `-j 4` on this host; a single-job run hits the tool's 120s cap)
- mypy: pass
- pytest: 1744 passed, 1 skipped
- vulture: no output
- lint-imports: 9 contracts kept, 0 broken
- CI: PASSED · Rebase: UP_TO_DATE · Tasks: 15/15 complete

`tests/test_startup_performance.py::test_server_startup_under_two_seconds` fails on this host
under load. Verified environmental — it fails identically on unmodified code.

The implementation is four constructor swaps to `_issue_manager(reference_name)` plus a
`_ref_suffix()` helper, with no new module and no manager-layer change, matching the plan.
