# Summary — Issue #188: per-permission GitHub probes in `verify_github`

## Goal

Replace the opaque `Repo accessible [ERR] not accessible (Repository returned None from GitHub API)` message with **6 per-permission read probes** that name the missing fine-grained PAT permission, the HTTP status, and the probed URL — so the user can tell which of *missing permission*, *awaiting org approval*, *renamed/transferred repo*, or *invalid token* is the actual cause.

Probes only run when `repo_accessible.ok=True`. All probes use `severity="warning"` and must NOT flip `overall_ok`. The four existing error-severity checks (`token_configured`, `authenticated_user`, `repo_url`, `repo_accessible`) remain authoritative.

## The 6 probes

| Result key | Permission | Endpoint |
|---|---|---|
| `perm_contents_read` | Contents: Read | `GET /repos/{o}/{r}/contents/` |
| `perm_administration_read` | Administration: Read | `GET /repos/{o}/{r}/branches/{default}/protection` |
| `perm_pull_requests_read` | Pull requests: Read | `GET /repos/{o}/{r}/pulls?state=all` |
| `perm_issues_read` | Issues: Read | `GET /repos/{o}/{r}/issues?state=all` |
| `perm_workflows_read` | Actions: Read | `GET /repos/{o}/{r}/actions/workflows` |
| `perm_statuses_read` | Commit statuses: Read | `GET /repos/{o}/{r}/commits/{default}/status` |

## Architectural / design changes

1. **New private module** `src/mcp_workspace/github_operations/_permission_probes.py` — self-contained probe orchestrator + classifier. Same package layer as `verification.py`; no new layer crossings. Module is private (leading underscore), not re-exported from `github_operations/__init__.py`.

2. **New property** `RepoIdentifier.web_host` (`src/mcp_workspace/utils/repo_identifier.py`) — three-branch host resolution mirroring `hostname_to_api_base_url` but without the `api.` subdomain or `/api/v3` suffix. Used to build the settings URL appended to 404 hints on `github.com` / `*.ghe.com`. (Deviation from issue text on GHES branch — issue says `https://<host>`, plan says `None`. User-approved per round 1 review; consolidates host classification into the property.)

3. **`CheckResult` shape unchanged** — no new fields. Probed URL is appended into `error` on failures only; `value="OK"` on success carries no URL.

4. **Probes reuse `manager._github_client` and the existing `repo` object** — same TLS context, same host as the repo-access check. Probe URLs are built statically from `f"{api_base_url}/repos/{full_name}/..."`; PyGithub internals (`Github._Github__requester`) are NEVER touched.

5. **Skip-when-unreachable lives inside the probe module** — `run_permission_probes(manager, repo)` accepts `repo: Repository | None`; when `None`, returns 6 placeholder rows. `verification.py` becomes a single unconditional call. Eliminates duplicated placeholder logic.

6. **Result-key ordering preserved** — 6 probe keys appended after `auto_delete_branches` and before `overall_ok`, in the order listed above.

## KISS simplifications applied

- Pure-function classifier `_classify_permission_response(name, status, url, web_host)` — `web_host: str | None` (pre-resolved by orchestrator) replaces passing `hostname` and re-deriving the host class. Host-classification rule lives in exactly one place: the new `web_host` property.
- Single `_run_probe` helper wraps the try/except + classify pattern. Each of the 4 simple probes is a one-line callable + URL pair fed into the helper. Only `perm_statuses_read` and `perm_administration_read` have dedicated functions (each requires two-call attribution: `get_commit`/`get_combined_status` and `get_branch`/`get_protection` respectively).
- Tests use `pytest.mark.parametrize` for the success-path × 6 probes and failure-status × probe matrices — keeps coverage explicit while collapsing ~24 near-duplicate test functions.

## Files to be created or modified

**Create:**
- `src/mcp_workspace/github_operations/_permission_probes.py`
- `tests/github_operations/test_permission_probes.py`
- `pr_info/steps/summary.md` (this file)
- `pr_info/steps/step_1.md`
- `pr_info/steps/step_2.md`

**Modify:**
- `src/mcp_workspace/utils/repo_identifier.py` — add `web_host` property
- `tests/utils/test_repo_identifier.py` — tests for `web_host`
- `src/mcp_workspace/github_operations/verification.py` — call `run_permission_probes(manager, repo)` once, before `overall_ok` calculation
- `tests/github_operations/test_verification.py` — integration tests (skip-when-unreachable shape, key ordering, `overall_ok` unaffected)

## Steps (one commit each)

| # | Title | Scope |
|---|---|---|
| 1 | `RepoIdentifier.web_host` property | Add property + DEBUG log + tests. Independent; no other code change. |
| 2 | `_permission_probes.py` module + integration | All 6 probes + classifier + orchestrator + integration into `verify_github` + full test coverage. Single cohesive change — splitting it would create an intermediate state with an unused module or partial probe set. |

## Constraints honored (from issue)

- All 6 probe keys present, exact names from the issue table.
- All probes `severity="warning"`. `overall_ok` unaffected.
- Hint includes permission name + HTTP status + `(GET <url>)` on failures; `value="OK"` on success.
- 404 host-branching: fine-grained-PAT explanation + settings URL only on `github.com` / `*.ghe.com`; GHES gets plain "missing permission OR resource not found (404)".
- `perm_administration_read` 404 special-cased: `missing permission Administration: Read OR no branch protection configured (404)`.
- `perm_statuses_read` two-call attribution: `get_commit` failure emits `value="not checked", error="commit lookup failed (covered by perm_contents_read)"` and skips classifier.
- `.totalCount` read on all 3 lazy `PaginatedList` probes (pulls, issues, workflows) to force the GET.
- URLs built statically from `f"{api_base_url}/repos/{full_name}/..."`; no PyGithub internals.
- Reuse `manager._github_client`; no new client construction.
- Skip-when-unreachable: 6 placeholder rows when `repo_accessible.ok=False`, zero PyGithub calls.

## Out of scope (per issue)

Write-permission probes; GraphQL fallback for EMU enterprises; `branch_protection` / `perm_administration_read` dedup; `--quick` opt-out flag; downstream renderer (`mcp_coder#946`).
