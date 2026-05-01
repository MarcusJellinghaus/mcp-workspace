# Implementation Review Log — Issue #181 (`verify_git`)

Branch: `181-add-verify-git-for-local-git-environment-signing-health-checks`
Started: 2026-05-01

This log records each round of automated review for the `verify_git`
implementation. Each round captures findings from the review subagent,
the supervisor's accept/skip decisions, what was implemented, and the
commit status. The final round is followed by a `## Final Status`
section with vulture / lint-imports results and overall readiness.


## Round 1 — 2026-05-01

**Findings (from `/implementation_review`):**

Critical
- C1 — `src/mcp_workspace/git_operations/verification.py` 604 lines (>600 project limit)
- C2 — `tests/git_operations/test_verification.py` 620 lines (>600 project limit)

Nice-to-have
- N1 — `signing_consistency` value="unknown" when `git_repo` fails (minor inconsistency vs Decision #3 spirit)
- N2 — SSH inline-key form (`key::ssh-ed25519 …`) not detected by `signing_key_accessible`
- N3 — `verify_head` outer exception path lacks `logger.debug` per Decision #11
- N4 — Sentinel-based control flow in openpgp `signing_binary` branch (fragile readability)
- N5 — `signing_binary` gpg/ssh-keygen/gpgsm `--version` does not catch `subprocess.TimeoutExpired`
- N6 — `agent_reachable` gpg-connect-agent does not catch `subprocess.TimeoutExpired`
- N7 — Tier 3 `actual_signature` does not catch `subprocess.TimeoutExpired`
- N8 — `@log_function_call` on `_get_config` may log return value (signing key ID) → Decision #11 violation
- N9 — `@log_function_call` on `verify_git` may log full result dict → Decision #11 violation

Nits — 7 cosmetic items (parameter shadowing, defensive `getattr`, default value comment, etc.)

**Decisions:**

- C1 / C2 — **Accept**. File-size policy violations.
- N3 — **Accept**. Small, aligned with Decision #11 debug-logging guidance.
- N5 / N6 / N7 — **Accept**. Real reliability bugs — unhandled timeouts break the structured-results contract of `verify_git`.
- N8 / N9 — **Accept after investigation**. Engineer to read `mcp_coder_utils.log_utils` source first; fix only if real.
- N1 — **Skip**. Speculative cosmetic shape change; `overall_ok` already correct, no user-visible bug.
- N2 — **Skip**. Explicitly out of scope per Decision D-B (file existence only) — agent-loaded keys / inline keys deferred.
- N4 — **Skip**. Code works, tests cover it; readability concern doesn't justify churn.
- All nits — **Skip**. Cosmetic per knowledge base ("Don't change working code for cosmetic reasons").

**Changes implemented:**

- **N8 / N9 confirmed real:** `mcp_coder_utils.log_utils.log_function_call` logs argument values via `json.dumps` in `_log_call_start` and the full return value in `_log_call_success`. `sensitive_fields=[...]` only redacts dict-key names, not positional/return values. Decorator removed from `_get_config`, `_run`, `_run_with_input`, and `verify_git` and replaced with targeted `logger.debug(...)` calls that log only structural metadata (key name, binary path, project_dir, `overall_ok`) — never values, key IDs, signed payload, or the full result dict. Module docstring updated to record the decision.
- **N5 / N6 / N7:** Wrapped each of the three subprocess paths in `try/except subprocess.TimeoutExpired`. `signing_binary` emits `severity=error, value="<format> binary timed out"`; `agent_reachable` emits `severity=warning, value="gpg-agent unreachable (timeout)"`; `actual_signature` emits `severity=error, value="signing timed out (>15s)"`. Tests added for each branch.
- **N3:** Added `logger.debug("verify_head: outer failure: %s", exc)` inside the broad `except Exception`.
- **C1:** Extracted pure decision/classification helpers (no subprocess) to new `src/mcp_workspace/git_operations/_signing_helpers.py` (161 lines). `verification.py` reduced 604 → 565. No `.importlinter` change required (helper module does not import subprocess).
- **C2:** Moved Tier 1 signing-detection test classes to new `tests/git_operations/test_verification_tier1_signing.py` (417 lines). `test_verification.py` reduced 620 → 305.
- Added test `test_get_config_does_not_log_value` asserting the value of `user.signingkey` never appears in `caplog`.

**Status:** All quality checks pass (pylint, pytest 463 passed/1 skipped in git_operations + 1124 elsewhere, mypy strict, lint-imports 9/9 contracts, check_file_size clean). Ready to commit.


## Round 2 — 2026-05-01

**Findings (from `/implementation_review`):**

Critical: none.

Nice-to-have
- N1 — Adjacent f-string concat artifact at `verification.py:307` (`f"... timed out " "(>5s)"`)
- N2 — Dead `commit.gpgsign` guard inside `build_signing_consistency_result` helper (caller already checks)
- N3 — Sentinel-based control flow in openpgp `signing_binary` branch (round 1 N4 again)
- N4 — `test_yes_value_recognised` duplicates `test_commit_gpgsign_true` and doesn't actually exercise the `yes`/`on`/`1` canonicalisation it claims (canonicalisation is git's responsibility; what we test is the `--type=bool` flag, covered elsewhere)
- N5 — `_patch_baseline_ok` duplicated between `test_verification.py` and `test_verification_tier1_signing.py`; suggest move to `conftest.py`

Nits — 3 cosmetic items (docstring trim, helper-contract test note, forward-quoted `"CheckResult"` return type)

**Decisions:**

- N2 — **Accept**. Real DRY issue; single source of truth lives in caller.
- N4 — **Accept**. Delete; current test is redundant and the `--type=bool` plumbing is covered by `test_extra_args_passed_to_config`.
- N1 — **Skip**. Adjacent string concatenation is idiomatic Python for line-length wrapping.
- N3 — **Skip**. Already considered & skipped in round 1.
- N5 — **Skip**. Moderate refactor; per knowledge base "Don't refactor beyond what the task requires."
- All nits — **Skip**. Cosmetic / minor.

**Changes implemented:**

- N2 — Removed the dead `if not flags_truthy.get("commit.gpgsign"):` early-return in `build_signing_consistency_result` (`_signing_helpers.py`). Updated the helper's docstring to declare the precondition (`commit.gpgsign` truthy). The inline caller in `verification.py` remains the single source of truth for the "not applicable" path.
- N4 — Deleted `test_yes_value_recognised` from `test_verification_tier1_signing.py`. No cross-references in any other test.

**Status:** All quality checks pass (pylint, pytest 1586 passed/2 skipped, mypy strict, lint-imports 9/9, no new file-size offenders introduced — 12 pre-existing offenders are unrelated to this PR and out of scope). Ready to commit.


## Round 3 — 2026-05-01

**Findings (from `/implementation_review`):** 0 critical, 0 nice-to-have, 0 nits.

**Verdict:** Production-ready. Round-1 fixes (logging discipline, explicit timeouts, file splits, helper extraction) and round-2 cleanup (dead-guard removal, redundant test deletion) are stable. Helper has exactly one caller; no orphan code; all quality gates green (1586 tests passed, 2 skipped, mypy strict, lint-imports 9/9, no new file-size offenders).

**Decisions:** None — nothing to triage.

**Changes implemented:** None.

**Status:** Loop terminated.


## Final Status

**Rounds:** 3 (round 3 produced zero findings, terminating the loop).

**Commits produced by the supervisor:**
- `46f0936` — round-1 fixes: removed `@log_function_call` value leak, added 3× `subprocess.TimeoutExpired` handlers, debug log on `verify_head` outer exception, split `verification.py` (604 → 565) by extracting `_signing_helpers.py`, split `test_verification.py` (620 → 305) by extracting `test_verification_tier1_signing.py`, added timeout-branch tests + no-key-leak test.
- `a9e4643` — round-2 cleanup: removed dead `commit.gpgsign` guard in `build_signing_consistency_result`, deleted redundant `test_yes_value_recognised`.

**Supervisor-run final checks:**
- `run_vulture_check`: no unused code.
- `run_lint_imports_check`: 9 contracts kept, 0 broken (Layered Architecture, PyGithub Isolation, Requests Isolation, MCP Isolation, GitPython Isolation, Structlog Isolation, Python JSON Logger Isolation, Subprocess Ban, Source/Test Independence).

**Notable issues caught and fixed:**
- **Decision #11 violation** — `mcp_coder_utils.log_utils.log_function_call` decorator logs argument and return values via `json.dumps`. Without intervention, every `_get_config("user.signingkey")` would have leaked the signing key ID to debug logs, and `verify_git`'s return would have logged the full result dict (including any signed-payload-derived data). Decorator removed from helpers + the public function and replaced with targeted `logger.debug` calls that log only structural metadata. No-leak invariant now asserted by tests.
- **Three propagating `subprocess.TimeoutExpired` paths** — `signing_binary --version`, `agent_reachable gpg-connect-agent /bye`, and `actual_signature gpg --clearsign` would have raised an unhandled exception on stalled binaries / pinentry, breaking the structured-results contract. All three now wrapped and emit a structured `CheckResult` instead.
- **File-size policy violations** — both `verification.py` (604) and `test_verification.py` (620) were over the 600-line cap. Split via clean module/file boundaries (pure helper extraction; Tier-1 signing tests moved to a sibling test file).

**Skipped findings (with reasons preserved in round logs):** SSH inline-key form (out of scope per Decision D-B), `signing_consistency` value="unknown" cosmetic, sentinel-based control flow in openpgp `signing_binary` branch, adjacent f-string concatenation (idiomatic Python), `_patch_baseline_ok` consolidation to `conftest.py` (speculative refactor), various nits.

**Quality gates at termination:** pylint=PASS, pytest=PASS (1586 passed, 2 skipped of 1588), mypy=PASS strict, lint-imports=PASS (9/9), vulture=PASS, file-size=PASS (no NEW offenders introduced).

**Branch state:** 2 commits ahead of origin, working tree clean, not pushed.
