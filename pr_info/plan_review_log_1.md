# Plan Review Log — Issue #187

Branch: 187-git-auto-split-in-args-into-pathspec-for-path-supporting-commands
Base: main
Plan files reviewed: pr_info/steps/summary.md, pr_info/steps/step_1.md, pr_info/steps/step_2.md


## Round 1 — 2026-05-03

**Findings**:
- Tool-name prefix typos (`mcp__tools-py__`, `mcp__workspace__`) in `step_1.md` and `step_2.md` LLM prompts and quality-gate blocks
- `step_2.md` pytest quality gate uses unsupported `markers=["git_integration"]` keyword arg instead of `-m` inside `extra_args`
- Plan deviates from issue body on `_SUPPORTS_PATHSPEC` re-export (issue suggested keeping a shim, plan drops it)
- Step 2 happy-path test only covers `git_diff` (skips `git_log`/`git_status`/`git_show`/`ls_files`/`ls_tree`)
- Other minor observations: set-ordering difference (cosmetic), underscore-prefixed cross-module constant (pre-existing), Step 1 `test_rejects_double_dash` is the sole assertion of the new wording

**Decisions**:
- Tool-prefix typos: **accept** (autonomous fix — clear typo)
- `markers=` keyword: **accept** (autonomous fix — consistency with Step 1 and project convention)
- Re-export deviation: **skip** (plan's clean import is correct per refactoring_principles.md "no shims")
- Step 2 single-handler coverage: **skip** (YAGNI — helper unit tests cover the logic; one wiring test proves the one-liner pattern)
- Other minor observations: **skip** (pre-existing or cosmetic)

**User decisions**: None — no design or requirements questions raised.

**Changes**:
- `pr_info/steps/step_1.md`: replaced `mcp__tools-py__` → `mcp__mcp-tools-py__`; replaced `mcp__workspace__` → `mcp__mcp-workspace__`
- `pr_info/steps/step_2.md`: replaced `mcp__tools-py__` → `mcp__mcp-tools-py__`; replaced `mcp__workspace__` → `mcp__mcp-workspace__`; replaced `markers=["git_integration"]` keyword with `-m git_integration` inside `extra_args`

**Status**: applied — pending commit
