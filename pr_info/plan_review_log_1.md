# Plan Review Log — Issue #180

**Issue:** [#180 — commit_staged_files silently produces unsigned commits even with commit.gpgsign=true](https://github.com/MarcusJellinghaus/mcp-workspace/issues/180)
**Branch:** `180-commit-staged-files-silently-produces-unsigned-commits-even-with-commit-gpgsign-true`
**Plan files:** `pr_info/steps/summary.md`, `pr_info/steps/step_1.md`, `pr_info/steps/step_2.md`, `pr_info/steps/step_3.md`
**TASK_TRACKER:** empty (no steps complete yet — full review)
**Branch state at start:** CI=PASSED, Rebase=UP_TO_DATE

## Round 1 — 2026-04-30

**Findings**:
- summary.md / step_2.md: dict-literal counts wrong (claimed 7 / 4+3; actual 10 / 6+4) — near-critical, mypy `total=True` is the safety net but the LLM following counts literally would miss two exception-handler returns in commits.py.
- step_2.md: minor wording — `Literal` is a *new* symbol on the existing `from typing import ...` line in core.py, not already imported.
- step_3.md: `test_validation_failures_set_validation_failed` enumerated four cases under "Three cases — pick three" hedge.
- step_3.md: stderr truncation length unspecified in debug-log plan.
- step_3.md: mock patch targets for `is_git_repository` / `get_staged_changes` not explicit (common patch-where-defined mistake).
- step_1/2/3.md: fast-mode pytest marker exclusion list contained four markers not registered in `pyproject.toml`.
- summary.md: optional fixture-hermeticity prose expansion (skipped — overengineering).
- step_1.md: optional manual `git config --global commit.gpgsign true` verification recipe (skipped — speculative).
- step_3.md: hash-length test confirmation (no action — already correct in step 3 algorithm).

**Decisions**:
- Apply: dict-literal counts, Literal import wording, test #3 cases (3→4), stderr truncation (500 chars), explicit patch targets, marker list cleanup (4 fakes removed, 2 real kept).
- Skip: prose-padding suggestions, speculative manual verification, no-action items.
- No design/scope/requirements questions to escalate to user.

**User decisions**: none — all findings autonomously triaged as straightforward improvements.

**Changes**:
- `pr_info/steps/step_1.md`, `step_2.md`, `step_3.md`: pytest marker exclusion replaced with `-m "not git_integration and not github_integration"` (the two markers actually defined in `pyproject.toml`).
- `pr_info/steps/step_2.md`: `commits.py` count 4→6 with all six sites enumerated; `workflows.py` count 3→4 with all four sites enumerated and the "if present" hedge dropped; `Literal` import note tightened.
- `pr_info/steps/step_3.md`: test #3 reframed as "four cases — parametrize over all four"; stderr truncated to first 500 chars; explicit patch targets `mcp_workspace.git_operations.commits.{is_git_repository,get_staged_changes}` added.
- `pr_info/steps/summary.md`: implementation-steps count corrected (6 + 4 = 10); 500-char truncation noted in Debug logging row.

**Verified return-literal counts** (via grep against actual source):
- `commits.py`: 6 sites — lines 39, 44, 52, 67, 72, 78.
- `workflows.py`: 4 sites — lines 65, 71, 81, 106.

**Status**: committed in `4d824c7` — `docs(plan): correct dict-literal counts and pytest markers in #180 plan` (4 files, +34/−27).

## Round 2 — 2026-04-30

**Findings**:
- step_2.md: `Iterator` is also on the existing `from typing import ...` line in core.py; the wording omits it. Instruction is unambiguous regardless — `improvement`, cosmetic only.
- step_3.md test #1: plan says mock `get_staged_changes` to "bypass validation" without spelling out the truthy return value (e.g. `["test.py"]`). Implementer will figure it out via test failure — `improvement`, non-blocking.
- step_3.md test #1: strict equality on `call_args.args == ("-m", "hello")` — speculative concern about future positional args, current spec acceptable. No action.
- step_3.md test #3: mixed mock/real hedging is fine — already addressed in round 1, no further action.
- summary.md "Out of Scope" / "real-gpg end-to-end test" minor redundancy with goal section — no defect.
- `commit_all_changes` broad `except Exception` keeps `error_category=None` — explicitly out of scope per summary; reviewer suggested noting in PR description, but plan already documents the boundary.

**Decisions**:
- Skip all — reviewer recommendation was `approve as-is`. All improvements are cosmetic or non-load-bearing; mypy `total=True` and test-failure feedback will catch any miss.
- No design/scope/requirements questions to escalate to user.

**User decisions**: none.

**Changes**: none — plan files unchanged this round.

**Status**: no changes; review loop terminates.

## Final Status

- **Rounds run**: 2 (round 1 produced changes, round 2 stable).
- **Commits produced**: 1 — `4d824c7` (round-1 plan corrections). Plus one upcoming for this log file.
- **Plan readiness**: ready for approval. The 3-step plan (fixture hardening → typed `error_category` field → porcelain swap with tests) is internally consistent, has accurate dict-literal counts, valid pytest markers, explicit mock patch targets, and a clear hooks-run-by-default behavior change call-out. mypy `total=True` enforces field-threading completeness in step 2; the porcelain swap in step 3 has a mock-based test that asserts no `--no-gpg-sign` is passed.
- **No user escalations** were needed — all findings were straightforward improvements.
