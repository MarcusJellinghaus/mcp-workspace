# Implementation Summary — Issue #314: read-only security-settings probes

## Goal

Add four new read-only GitHub security probes (`dependabot_alerts`,
`dependabot_security_updates`, `secret_scanning`,
`secret_scanning_push_protection`) in a new `_security_probes.py` module,
exposing `verify_github_security(project_dir) -> dict[str, CheckResult]`.
Companion to mcp_coder#1180, which renders these as a "GITHUB SECURITY"
section. Builds on the tri-state `CheckResult` convention from
mcp-workspace#301 (merged): `ok=True|False|None`, where `None` means
"cannot verify", never "off".

## Architectural / design changes

- **New sibling module, not an extension of `_permission_probes.py`.**
  `_permission_probes.py` solves a different problem (fine-grained PAT
  404-vs-403 ambiguity across six generic read permissions) and its
  host-aware URL/hint machinery doesn't apply here — these four checks have
  an unambiguous three-way split handed to us directly by the two GitHub API
  shapes involved. `_security_probes.py` is deliberately smaller: no
  `web_host`/`base`-URL plumbing, no embedded request URLs in error text.
- **Two independent classification axes, matching the two data sources:**
  - `dependabot_alerts` bypasses `Repository.get_vulnerability_alert()`
    entirely (confirmed via PyGithub source: it calls `Requester.requestJson()`,
    which never raises and collapses every non-204 status into a bare
    `False`) and instead calls `repo.requester.requestJson(...)` directly,
    classifying the raw HTTP status: `204 → ok=True`, `404 → ok=False` (a
    verified "disabled", not an error), anything else → `ok=None`.
  - `dependabot_security_updates` / `secret_scanning` /
    `secret_scanning_push_protection` come from `repo.security_and_analysis`
    (a `SecurityAndAnalysis` object of `SecurityAndAnalysisFeature`
    sub-fields). `security_and_analysis is None` (token lacks
    `Administration: Read`, still a 200 response) and a missing sub-feature
    are classified by the *same* function, the same way (`ok=None`) — the
    issue treats them as one case, so the code does too, rather than
    special-casing "attribute absent on the container" separately from
    "attribute absent on the sub-object".
- **Independent auth/repo resolution.** `verify_github_security()` builds
  its own `BaseGitHubManager` and resolves the repo itself — it does not
  take a client or repo object from `verify_github()`. This matches
  `_permission_probes.py`'s existing shape and mcp_coder#1180's Decisions
  table (accepted second auth round-trip; `verify` is infrequent).
  `verify_github_security()` is **not** merged into `verify_github()`'s
  result dict — mcp_coder renders it as a separate section via a separate
  call.
- **No new status marker, no new `CheckResult` fields.** Reuses the
  existing `CheckResult` TypedDict and `ok=None` convention as-is.

## Files to create / modify

| Path | Change |
|---|---|
| `src/mcp_workspace/github_operations/_security_probes.py` | **New.** Classifiers, probe, and `verify_github_security()`. |
| `tests/github_operations/test_security_probes.py` | **New.** Unit tests, built up across steps 1-3. |
| `src/mcp_workspace/github_operations/__init__.py` | **Modified.** Import and export `verify_github_security`. |
| `tests/github_operations/test_package_exports.py` | **Modified.** Assert `verify_github_security` is exported. |

No other files change. No new dependencies (PyGithub's `Consts` and
`Repository.requester` are already used/available at the project's floor
`PyGithub>=2.7.0`). No docs updates — `docs/ARCHITECTURE.md` does not
document `_permission_probes.py`, so no parallel entry is needed for its
sibling.

## Steps

1. [Step 1](./step_1.md) — pure classifier functions + tests
2. [Step 2](./step_2.md) — `dependabot_alerts` probe (low-level `requestJson`) + tests
3. [Step 3](./step_3.md) — `verify_github_security()` orchestration + tests
4. [Step 4](./step_4.md) — public export wiring

Each step is one commit: tests + implementation + all checks passing
(`run_pylint_check`, `run_pytest_check -n auto`, `run_mypy_check`), formatted
with `run_format_code` before committing.
