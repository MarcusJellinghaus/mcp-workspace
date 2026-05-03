# Plan Review Log — Issue #184

Supervisor-run automated plan review. Each round corresponds to a `/plan_review` → triage → `/plan_update` cycle.

## Round 1 — 2026-05-03

**Findings** (from `/plan_review` engineer):
- F1 [STRAIGHTFORWARD] Step 1 misses Boy Scout docstring update at `src/mcp_workspace/config.py:10`.
- F2 [SKIP] Duplicated path literal in helper — intentional, mirrors `mcp_coder`.
- F3 [SKIP] Optional cross-platform `_read_config_value` test — borderline, deferred to keep plan simple.
- F4 [STRAIGHTFORWARD] Step 2 acceptance grep is too narrow — false-positives on docstrings owned by Step 3.
- F5 [SKIP] Behavioral test for `ValueError` message — borderline, deferred.
- F6 [SKIP] Mechanical replacement strings verified — confirmation only.
- F7 [STRAIGHTFORWARD] Tool-name typo: `mcp__tools-py__*` → `mcp__mcp-tools-py__*` per CLAUDE.md.
- F8 [STRAIGHTFORWARD] `./tools/format_all.sh` → `mcp__mcp-tools-py__run_format_code` per CLAUDE.md.
- F9 [SKIP] Step granularity — confirmation only.
- F10 [SKIP] Empty TASK_TRACKER.md — expected per planning principles.
- D1 [DESIGN] Duplicate path resolver locally vs. import from `mcp_coder` / `mcp-coder-utils` — needs user input.

**Decisions**:
- Auto-accepted: F1, F4, F7, F8.
- Skipped (deferred or confirmation-only): F2, F3, F5, F6, F9, F10.
- Escalated to user: D1.

**User decisions**:
- D1 → "Add to `mcp-coder-utils` first" (option C). The platform-aware path helper must first be added to `mcp-coder-utils`; `mcp_workspace` then imports it. This PR is now blocked on an upstream PR.

**Changes** (from `/plan_update` engineer):
- `summary.md`: added "Upstream Prerequisite" blocking section; removed local-helper design; reworked steps table for "import from upstream"; added `pyproject.toml` to modified-files list; tool-name + formatter fixes.
- `step_1.md`: replaced local helper with `from mcp_coder_utils.user_config import get_user_config_path`; reworked tests to mock the imported helper instead of `sys.platform`/`Path.home`; added F1 docstring fix; added `pyproject.toml` version bump line.
- `step_2.md`: runtime sites call the imported helper directly; F4 reworded acceptance grep; tool-name fixes.
- `step_3.md`: promoted comprehensive grep gate to Step 3 acceptance with explicit rule; tool-name fixes.
- `pr_info/steps/Decisions.md`: new file logging D1, F1, F4, F7, F8, and explicit skip list.

**Upstream prerequisite findings**:
- `mcp-coder-utils` does not currently expose any config-path helper. Recommended addition: new module `src/mcp_coder_utils/user_config.py` exposing `get_user_config_path() -> Path`, mirroring `mcp_coder.utils.user_config.get_config_file_path()` (with rename for downstream clarity).
- File issue/PR at https://github.com/MarcusJellinghaus/mcp-coder-utils.

**Open risks**:
- Upstream naming/location not yet locked — Step 1 hardcodes a tentative import path with a note to adjust once upstream lands.
- `pyproject.toml` minimum-version pin left as a placeholder — concrete version filled in after upstream release is cut.
- This PR is blocked on the upstream PR. The user accepted this trade-off.

**Status**: changes applied, pending commit.


## Round 2 — 2026-05-03

**Findings** (from `/plan_review` engineer):
- F11 [STRAIGHTFORWARD] Step 1 implementer must install upstream `mcp-coder-utils` release in venv before running tests, else pytest collection fails with `ModuleNotFoundError`.
- F12 [DESIGN] Mocking `get_user_config_path` in every test means zero `mcp_workspace`-side proof that the bug is fixed on Linux/macOS — borderline; one un-mocked smoke test would catch import-path drift.
- F13 [STRAIGHTFORWARD] `pyproject.toml` change is *introducing* a `>=X.Y.Z` lower bound (current entry has no pin), not bumping one. Pin scheme also unspecified.
- F14 [STRAIGHTFORWARD] Step 1 said "apply this pattern uniformly across the existing test classes" — too vague. Actual scope: ~15 tests across 4 classes.
- F15 [SKIP] Verified no leftover `_config_path()` references — confirmation only.
- F16 [SKIP] Verified import paths consistent across step files — confirmation only.
- F17 [SKIP] Verified F4 grep gate rewording is internally consistent between Steps 2 and 3 — confirmation only.
- F18 [SKIP] Verified step boundaries still right-sized after pivot — confirmation only.

**Decisions**:
- Auto-accepted: F11, F13, F14.
- Skipped: F12 (defaulting to simpler plan per supervisor playbook — YAGNI), F15/F16/F17/F18 (confirmations).
- Escalated to user: none.

**User decisions**: none this round.

**Changes** (from `/plan_update` engineer):
- `step_1.md`: added "Before starting" venv prerequisite note (F11); reworded `pyproject.toml` row to clarify lower-bound is being *introduced*, specified pin scheme = match sibling deps (loose `>=X.Y.Z`, no upper cap), added `[tool.mcp-coder.install-from-github]` ref-tag guidance (F13); replaced vague "apply uniformly" line with explicit per-class table and verified call-site count of **13** patch-`Path.home` sites across 4 classes (F14).
- `Decisions.md`: appended D2 entry summarizing F11/F13/F14; F12 logged under "Skipped".

**Verified facts**:
- Test count: 13 `patch.object(Path, "home", ...)` call sites across `TestReadConfigValue` (5), `TestGetGithubToken` (3), `TestGetGithubTokenWithSource` (3), `TestGetTestRepoUrl` (2). 3 env-var-only sibling tests do not use `Path.home` and don't need migration.
- pyproject convention: all pinned siblings use loose `>=X.Y.Z` with no upper cap; no existing `@vX.Y.Z` ref on the install-from-github block.

**Open risks** (carried forward, unchanged):
- Upstream `mcp-coder-utils` release does not yet exist; concrete version pin (`X.Y.Z`) remains a placeholder until upstream lands.

**Status**: changes applied, pending commit.


## Round 3 — 2026-05-03

**Findings**: none. Engineer reports READY — no plan changes needed.

**Confirmations**:
- Issue requirements fully covered: all 12 sites from issue #184 are mapped (3 runtime + 5 class docstrings + 4 test docstrings), plus the F1 boy-scout docstring and upstream-prerequisite / `pyproject.toml` work.
- 3-step split is right-sized; each is one logical commit.
- Tests adequately specified (13 `patch.object(Path, "home", ...)` sites across 4 classes enumerated; Steps 2/3 correctly require no new tests).
- Upstream prerequisite unambiguous in both `summary.md` and `step_1.md`.
- No leftover `_config_path()` references or stale path literals.
- Acceptance criteria are concrete and checkable per step.
- F4 grep-gate scoping consistent across Steps 2 and 3.
- F13 pin-scheme guidance internally coherent across step_1.md and Decisions.md.

**Decisions**: none.
**User decisions**: none.
**Changes**: none.
**Status**: convergence — loop terminates.

## Final Status

- **Rounds run**: 3
- **Commits produced** (excluding this final log commit): 2
  - Round 1 (`3ccf029`): architectural pivot — import platform-aware path resolver from upstream `mcp-coder-utils` instead of duplicating; F1/F4/F7/F8 polish.
  - Round 2 (`a3724cc`): venv prereq, pyproject pin scheme clarified, test rework scope made explicit.
- **User design decisions**: 1 (D1 — use upstream helper from `mcp-coder-utils`, not local duplication).
- **Open work outside this PR**: file an issue / PR at `mcp-coder-utils` to add `user_config.get_user_config_path()`. This PR is **blocked** on the upstream release.
- **Plan status**: **READY for approval and implementation** (subject to the upstream prerequisite landing).
