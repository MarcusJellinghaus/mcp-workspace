# Implementation Review Log #1 — Issue #188

Branch: `188-verify-github-probe-per-permission-rest-endpoints-to-surface-fine-grained-pat-grant-gaps`
Scope: per-permission GitHub probes in `verify_github` (6 read probes + `RepoIdentifier.web_host` property)

## Round 1 — 2026-05-04

**Findings:**
1. Misleading test docstring — `TestPermissionProbeOverallOkUnaffected` claimed all 6 probes fail but `perm_administration_read` actually succeeded (`get_protection` returned mock).
2. `# type: ignore[arg-type]` at `verification.py:341` — suspected redundant.
3. Symmetry: unused `web_host` param in `_probe_statuses` two-call branch.
4. `except Exception` swallows non-`GithubException` (pre-existing pattern in `verification.py`).
5. Brittle MagicMock internal assertion in `test_permission_probes.py:362-368`.
6. Untracked log file (this file).

**Decisions:**
- #1 ACCEPT — make the test genuinely fail all 6.
- #2 ACCEPT — Boy Scout cleanup, but verify mypy still passes.
- #3 SKIP — symmetry between two-call probes is more valuable than micro-optimization.
- #4 SKIP — pre-existing pattern, out of scope per software_engineering_principles.md; warning severity can't mask criticals.
- #5 SKIP — already covered by clearer sentinel test in `test_verification.py`. Defense in depth fine.
- #6 SKIP — review log, deleted later.

**Changes:**
- `tests/github_operations/test_verification.py`: `mock_branch.get_protection.side_effect = denial` so all 6 probes genuinely fail; loop assertion tightened to `check["ok"] is False`; comments updated.
- Fix #2 was attempted but the `# type: ignore[arg-type]` turned out to be load-bearing for the `manager` argument (`BaseGitHubManager | None` from try-init pattern), not the `repo` argument. Removing it caused mypy failure. Restored — no change.

**Quality checks:** pylint clean, pytest 1676 passed / 2 skipped / 0 failed, mypy clean, format clean.

**Status:** committing.

## Round 2 — 2026-05-04

**Findings:** None of substance. Fresh-eyes review confirmed round 1 fix is correct, no regressions.

**Decisions:** N/A — zero new findings.

**Changes:** None.

**Status:** No code changes — review loop terminates.

## Final Status — 2026-05-04

**Rounds run:** 2 (round 1: 1 fix accepted + committed; round 2: zero findings).

**Quality gates (all clean):**
- pylint
- pytest (1676 passed, 2 skipped, 0 failed)
- mypy (strict)
- vulture (no output)
- lint-imports (9 contracts kept, 0 broken)

**Compliance:** All issue #188 constraints satisfied — 6 probe keys with exact names and ordering, all `severity="warning"`, `overall_ok` driven only by error-severity checks, skip-when-unreachable produces 6 placeholders with zero PyGithub calls, host-branched 404 hint, two-call attribution for Administration and Statuses probes, `RepoIdentifier.web_host` as single source of host classification, URLs built statically (no PyGithub internals).

**Commits this review:**
- `74c3c77` test(verification): make 6-failed-probes test honest by failing all six

**Outcome:** Ready for PR merge from a code-review perspective.
