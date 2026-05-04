# Plan Review Log — Issue #188

**Issue:** verify_github: probe per-permission REST endpoints to surface fine-grained PAT grant gaps
**Branch:** 188-verify-github-probe-per-permission-rest-endpoints-to-surface-fine-grained-pat-grant-gaps
**Started:** 2026-05-04

Plan files at start of review: `pr_info/steps/summary.md`, `pr_info/steps/step_1.md`, `pr_info/steps/step_2.md`.
No prior review logs. Branch up-to-date with `main`. `TASK_TRACKER.md` is empty (will be populated at implementation time).


## Round 1 — 2026-05-04

**Findings:**
- **Critical:** `perm_administration_read` two-call attribution missing. `lambda: repo.get_branch(default).get_protection()` wraps two calls; a `get_branch` failure misattributes to `Administration: Read`. Issue Decision #9 establishes the same pattern for `perm_statuses_read`.
- **Critical:** Orchestrator-vs-test inconsistency on `manager` passing — step_2 waffles between "always pass `manager`" and "or pass `manager=None`". Tests assert no manager dereference on skip path.
- **Accept:** Test 5 (statuses two-call) asserts implementation (classifier-was-NOT-invoked sentinel) instead of behavior; replace with output-shape assertion.
- **Accept:** `repo.default_branch` cost isn't documented — silent assumption it's a free attribute on the hydrated `Repository`.
- **Skip:** URL with embedded query string (literal f-string is fine; `urlencode` is over-engineering).
- **Skip:** Boy Scout opportunity in `verification.py` placeholder-construction duplication (out of scope).
- **Skip:** Test naming `test_permission_probes.py` (no underscore prefix) — matches existing project convention (e.g., `_diagnostics.py` → `test_diagnostics.py`).
- **Open Q1 (user):** `web_host` returns `None` for GHES per plan, vs. issue text saying `https://<host>` for GHES. Deviation justified by KISS — single source of truth for host classification.

**Decisions:**
- Critical #1 — accept; mirror `_probe_statuses` two-call pattern with new `_probe_administration` helper.
- Critical #2 — accept; pick single shape `manager` always non-None; only `repo` is `None` on skip.
- Accept #1 (test 5 + new 5b) — accept; assert output shape (`error` absence of "GET"/URL) instead of patching classifier.
- Accept #2 (`default_branch` cost) — accept; add one sentence to step_2 HOW.
- Open Q1 — escalated to user.

**User decisions:**
- Q1 (`web_host` for GHES): user confirmed plan's `None` approach (recommended). Deviation noted in step_1 + summary.md; PR description should mention.

**Changes:**
- `pr_info/steps/summary.md`: KISS bullet updated to mention both two-call probes; architectural-change #2 parenthetical for `web_host=None` rationale.
- `pr_info/steps/step_1.md`: Design-decision callout extended with user-confirmed-deviation paragraph for GHES.
- `pr_info/steps/step_2.md`: `perm_administration_read` split into dedicated `_probe_administration` helper (algorithm block + orchestrator-pseudocode update + new test 5b); orchestrator pseudocode lists `perm_administration_read` after the for-loop and before `_probe_statuses` to preserve `_PROBE_KEYS` ordering; "or pass `manager=None`" waffling removed; tests 5 + 5b switched to output-shape assertions; `repo.default_branch` HTTP-free note added under HOW.

**Status:** committed (see commit below).


## Round 2 — 2026-05-04

**Findings:**
- **Critical:** Orchestrator dict-insertion order does NOT match `_PROBE_KEYS`. Round 1 placed `_probe_administration` AFTER the simple-probes for-loop (which yielded `contents, pulls, issues, workflows`); the resulting dict order was `contents, pulls, issues, workflows, administration, statuses` — but `_PROBE_KEYS` requires `contents, administration, pulls, issues, workflows, statuses`. Would fail integration test #9.
- **Accept:** Test #3 wording silent on count (says "probe × status" without specifying which probes); after round 1 only 4 simple probes go through `_run_probe` directly.
- **Accept:** Test #11 patches `run_permission_probes` itself, defeating the purpose of exercising the real skip path.
- **Skip:** No new design questions or out-of-scope concerns.

**Decisions:**
- Critical (orchestrator order) — accept; chose Option C (drop for-loop, inline all 6 `out[k] = ...` assignments in `_PROBE_KEYS` order). KISS — order-correct by construction; with only 6 probes the loop pays no readability dividend.
- Accept #1 (test #3) — accept; explicitly name the 4 simple probes in test #3 and note admin/statuses are covered by #5/#5b.
- Accept #2 (test #11) — accept; rewrite to exercise the real skip path with no patching of `run_permission_probes`.

**User decisions:** None this round (the ordering bug is a clear mechanical fix among equivalent options; no requirements/design escalation).

**Changes:**
- `pr_info/steps/step_2.md`: Orchestrator pseudocode rewritten to 6 inline `out[k] = ...` assignments in `_PROBE_KEYS` order (no for-loop, no `_PROBE_TABLE`); "Probe data table" reframed as data reference (not loop input); stale "between the for-loop and `_probe_statuses`" narrative removed; replaced with "ordering is correct by construction"; test #3 narrowed to "4 simple probes" with explicit key list; test #11 rewrites to exercise the real skip path via `repo_accessible.ok=False` and assert zero PyGithub calls.
- `pr_info/steps/summary.md`: KISS bullet updated to describe inlined 6-assignment shape (no for-loop); confirms 4 simple probes share `_run_probe` while admin/statuses get dedicated helpers.

**Status:** committed (see commit below).


## Round 3 — 2026-05-04

**Findings:** None (Critical, Accept, Open Questions all empty).

**Verification:**
- Orchestrator pseudocode: 6 inline `out[k] = ...` assignments in `_PROBE_KEYS` order; no for-loop; no `_PROBE_TABLE`.
- `_PROBE_KEYS` referenced exactly once — in the skip-path dict-comprehension (correct).
- Test #3 explicitly names 4 simple probes; admin/statuses covered by #5/#5b.
- Test #11 exercises real skip path (no `run_permission_probes` patching).
- summary.md KISS bullet reflects inlined 6-assignment shape.
- "Probe data table" reframed as data reference; 4 rows; admin/statuses correctly excluded.
- No stale text: "5 simple probes", "between the for-loop", `_PROBE_TABLE` — all absent.
- Lambdas: `.totalCount` on 3 lazy probes only; `get_contents("")` (no `.totalCount`); URL `f"{base}/contents/"` has trailing slash.
- `admin_404` threading: `_probe_administration` → `_run_probe(admin_404=True)` → `_classify_permission_response`. All 4 simple inline calls default to `admin_404=False`.
- Issue Decisions 1–11 all preserved; `web_host=None` GHES deviation user-approved + documented.

**Status:** No changes — loop exits.

## Final Status

**Rounds run:** 3
**Plan-update commits:** 2 (`271773a`, `70e0b31`)
**Log commit:** pending end-of-review.
**User decisions captured:** 1 (Q1 — `web_host=None` for GHES, plan's approach approved as Recommended).

**Outcome:** Plan is ready for implementation. Step 1 (`RepoIdentifier.web_host` property) and Step 2 (`_permission_probes.py` module + `verify_github` integration) are both single-commit, TDD-ordered, with all 6 probes correctly attributed (two-call helpers for `perm_administration_read` and `perm_statuses_read`), order-correct by construction (orchestrator inlines 6 assignments in `_PROBE_KEYS` order), and aligned with issue #188 Decisions 1–11.

**Documented deviation from issue text:** `RepoIdentifier.web_host` returns `None` for GHES (issue suggested `https://<host>`). User-approved; rationale captured in `step_1.md` and `summary.md`. Note in eventual PR description.
