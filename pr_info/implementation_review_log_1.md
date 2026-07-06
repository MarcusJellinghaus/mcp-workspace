# Implementation Review Log — Issue #221

Make `check_file_size` default limit configurable via a server CLI flag.

Branch: `221-make-check-file-size-default-limit-configurable-via-a-server-cli-flag`

---

## Round 1 — 2026-07-06

**Findings** (from `/implementation_review`, reviewing `main...HEAD`):
- Core implementation correct: resolution order (explicit arg → flag → 600 fallback), `<= 0` validation, argparse non-int rejection, end-to-end threading. 33 targeted tests pass.
- Critical: none.
- Should-fix: `README.md` — new `--file-size-limit` flag not added to the CLI synopsis / arguments list (all sibling flags are documented).
- Nice-to-have: explicit `max_lines <= 0` in `check_file_size` bypasses validation (resolves to `effective = 0`).
- Nice-to-have: `tests/test_server_file_size.py` `TestRunServerFileSizeLimit` calls real `run_server`, mutating module-global `_project_dir` to a non-existent path without restoring — can leak across xdist workers.

**Decisions**:
- ACCEPT — README documentation gap: user-facing flag must be documented like its siblings.
- SKIP — explicit `max_lines <= 0` guard: pre-existing behavior (old `int = 600` default had the same gap), out of the issue's scope (resolution order concerns the *omitted* case only), and speculative (only matters on future caller misuse).
- ACCEPT — test `_project_dir` pollution: real test-isolation bug, bounded fix.

**Changes**:
- `README.md`: added `[--file-size-limit N]` to the usage synopsis and an arguments bullet.
- `tests/test_server_file_size.py`: `TestRunServerFileSizeLimit` tests now also patch `set_project_dir`, so `run_server` no longer mutates the real global. Assertions unchanged.
- Checks: format, pylint, pytest (1785 passed / 2 skipped), mypy — all green.

**Status**: committed (see below).

## Round 2 — 2026-07-06

**Findings** (re-review of full diff through `a53b73d`):
- Production code (`server.py`, `main.py`) correct; resolution order uses proper `is not None` sentinel; `<= 0` fail-fast guard correctly placed; all 7 acceptance criteria mapped to tests. Round-1 fixes introduced no regressions.
- Should-fix: autouse fixture `_reset_globals` (`tests/test_server_file_size.py:33`) flagged by vulture as unused; project convention is to whitelist autouse fixtures in `vulture_whitelist.py`. Acceptance criterion #7 requires the vulture gate to pass.
- Skip (confirmed, not new): `setup_server`/`_project_dir` reset convention mirrors `tests/test_server.py`; explicit `max_lines <= 0` guard (out of scope, pre-existing).

**Decisions**:
- ACCEPT — add `_._reset_globals` to `vulture_whitelist.py`.

**Changes**:
- `vulture_whitelist.py`: added `_._reset_globals` under the test-fixtures section.
- Checks: format, vulture (no output), pylint, pytest (1785 passed / 2 skipped), mypy — all green.

**Status**: committed (see below).

## Round 3 — 2026-07-06

**Findings**: Re-review of full `main...HEAD` diff. Production code and both prior-round fixes confirmed sound; patch targets correct (`main.py` lazily imports `run_server`, so patching `mcp_workspace.server.run_server` works). Checks green (pytest 33/33 targeted, mypy, pylint, vulture all clean). **NO NEW FINDINGS.**

**Decisions**: None — nothing to change.

**Changes**: None.

**Status**: no changes needed. Review loop terminates.

---

## Final Status

- **Rounds run**: 3 (round 1 & 2 produced fixes; round 3 clean → loop terminated).
- **Commits produced** (fixes): `a53b73d` (README doc + test global-leak fix), `a03898c` (vulture whitelist for `_reset_globals`).
- **Supervisor-run gates**: `run_vulture_check` → no output (clean); `run_lint_imports_check` → 9 contracts kept, 0 broken.
- **Acceptance criteria**: all met — resolution order (explicit → flag → 600), `<= 0` fail-fast, non-int rejection via argparse, docstring updated, README documented, unit tests covering all branches, full check suite green.
- **Outstanding issues**: none. Deliberately skipped (out of scope / pre-existing): explicit `max_lines <= 0` guard in `check_file_size`.
