# Plan Review Log — Issue #216

GitHub calls hang on unreachable API host — bound timeout/retry + add proxy/network diagnostics.

Supervisor-driven automated plan review. Plan under review: `pr_info/steps/` (step_1 … step_4, summary). Branch up to date with `main`; TASK_TRACKER empty (no implementation started — fresh plan).

## Round 1 — 2026-06-30

**Findings** (from engineer `/plan_review`):
- #1 step_4: `host` undefined in the `network_proxy` value snippet (`f"api={host}:443..."`) — `NameError` if copied literally (mechanical).
- #2 step_1: `Optional[str]` token passed into `str`-typed `build_github_client` re-introduces a mypy `arg-type` error at the verify site (mechanical).
- #3 step_3/Decision 6: plan has the helper own the `requests.exceptions` isinstance-gating, so call sites don't import `requests` — a deviation from the issue's literal "add the import at call sites" constraint (design confirmation).
- #4 step_2: instruction to "repair existing test asserting `timeout=60`" is speculative — no such assertion exists (mechanical).
- #5 step_4: `has_applicable_proxy` re-calls `getproxies()` instead of reusing collected diag (nit/efficiency).
- #6 step_3: `_collect_network_diagnostics` ALGORITHM pseudocode is a malformed dict (reads as a set) (nit).
- Note: Decision 9 skip can leave `overall_ok=True` on an untested no-proxy unreachable host — already explicit in the issue (skipped checks → `warning`).

**Verdict from review**: No blocking findings. Plan is faithful to all 11 decisions and all load-bearing constraints (30s timeout math, Decision 11 proxy gate, gaierror-before-OSError ordering, lazy `winreg`, `network_proxy` severity=warning, PyGithub>=2.1.0 bump, 4th raw-requests site, once-per-process guard + autouse reset fixture). 4 cohesive one-commit steps with a sound dependency chain.

**Decisions**:
- #1 — accept (fix): add a `host` key to `_collect_network_diagnostics`; consume `diag["host"]` in step_4.
- #2 — accept (fix): keep `# type: ignore[arg-type]` on the verify-site factory call.
- #3 — accept autonomously, no change: helper-owns-gating is functionally equivalent, cleaner, and matches the issue's own "Error detection (B)" prose; does not affect scope/architecture, so not escalated (default-to-simpler guidance).
- #4 — accept (fix): reword to describe a new test patching `requests.get` asserting `timeout=(10, 60)`.
- #5 — skip: harmless; keep the cleaner `has_applicable_proxy(api_base_url)` signature.
- #6 — accept (fix): rewrite pseudocode as a proper dict literal.
- overall_ok-on-skip — no action: already decided by the issue (Decision 9 + Acceptance).

**User decisions**: none — all items mechanical or already decided by the issue; nothing escalated this round.

**Changes** (applied by engineer via plan edits):
- step_1: note that the verify-site `build_github_client(token, api_base_url)` keeps `# type: ignore[arg-type]` (Optional token).
- step_2: reworded artifact test instruction to add a new `requests.get` patch test asserting `timeout=(10, 60)`.
- step_3: added `host` key to `_collect_network_diagnostics` return + DATA section; fixed malformed dict pseudocode.
- step_4: `network_proxy` value snippet now uses `diag['host']`.

**Status**: plan changed — committing; loop continues with a fresh review round.
