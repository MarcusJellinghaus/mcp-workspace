# Implementation Review Log 1 — Issue #235

Docstring salience: surface Args-only capabilities in 7 tool summary lines.

Supervised code review of branch
`235-docstring-salience-surface-args-only-capabilities-in-7-tool-summary-lines`.

## Round 1 — 2026-07-31

**Findings**

1. Out-of-scope commits on branch — `.github/workflows/ci.yml` (git-only pre-install of
   `mcp-coder-utils` in 3 jobs) and `pyproject.toml` (`mcp>=1.3.0` → `mcp>=1.3.0,<2.0`)
   rode in on a docstring-only branch (commits `2e72bed`, `0bdf21a`).
2. README sync covers 4 bullets, not the 2 authorized by the issue's Decisions table
   (`edit_file` and `read_reference_file` added).
3. Trailing-period inconsistency — the 4 rewritten README bullets end with a period; the
   other 8 in the Features list do not.
4. README half-synced — `delete_directory` and `move_file` docstrings changed but their
   README bullets were left on the old wording.
5. Information loss — README `save_file` bullet dropped "atomically"; the write genuinely
   is atomic (`file_tools/file_operations.py:252`) and nothing user-facing says so now.
6. Summary/body redundancy — new summaries restate the first body line in `save_file`,
   `delete_directory`, `move_file`.
7. Wrapper/impl docstring divergence — the underlying functions in `file_tools/` still
   carry the old summaries.
8. `pytest -n auto` failure in `tests/test_startup_performance.py::test_server_startup_under_two_seconds`
   (6.6s vs 2.0s threshold); passes 3/3 standalone.

**Decisions**

- **1 — Skip (note only).** Both commits are legitimate CI-green fixes; reverting them
  would break CI. Flagged to the user rather than fixed. Not a code defect.
- **2 — Accept as implemented.** `step_2.md` already flagged and justified the expansion:
  the issue's claim that the other tools are not summarized in the README is factually
  wrong. Rolling back would leave the docs knowingly stale. No change.
- **3 — Skip.** Cosmetic; byte-identity with the docstrings is the stated plan constraint,
  and adding periods to 8 untouched bullets is scope creep.
- **4 — Skip.** `step_2.md` records a reasoned decision that those two bullets already
  surface the key capability. Re-opening it is churn.
- **5 — Skip.** Wording approved verbatim in the issue; atomicity is not a
  tool-selection driver, and the fix would require touching a docstring body, which the
  issue forbids.
- **6, 7 — Skip.** Issue mandates bodies stay intact; `file_tools/` functions are not
  `@mcp.tool()` wrappers and never reach the generated schema. Out of scope.
- **8 — Skip (pre-existing).** Timing-sensitive benchmark flaking under parallel
  execution; a docstring edit cannot affect startup time. Worth a separate issue to mark
  the test serial.

**Verifications (all PASS)**

- All 7 docstring summary lines match the issue's approved table character-for-character,
  at the predicted line numbers.
- `src/` diff is exactly 7 single-line hunks — no Args / Returns / Raises / body /
  signature / decorator / logic line touched.
- The 4 synced README bullets are byte-identical to their docstring first lines.
- No test pins any of the old summary strings (zero hits under `tests/`).

**Changes**: none — no finding was accepted for code change.

**Status**: no changes needed.

## Final Status

- **Rounds run**: 1 (zero code changes → loop terminated after round 1).
- **pylint**: PASS. **mypy** (strict): PASS. **pytest**: pass except the pre-existing
  `test_startup_performance` parallel-execution flake (passes standalone).
- **vulture**: clean, no output.
- **lint-imports**: PASSED — 9 contracts kept, 0 broken (231 files, 1008 dependencies).
- **Implementation verdict**: the change matches the approved specification exactly and is
  ready to merge. The two open items are procedural, not technical: the unrelated
  CI/`pyproject` commits sharing this branch, and confirmation of the 2-extra-README-bullet
  expansion that the plan itself flagged.
