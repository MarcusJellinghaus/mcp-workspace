# Summary — #370 probe the code-scanning alerts token scope in `verify_github_security`

## Goal

`verify_github_security` gains a fifth, report-only result under the key
`code_scanning_alerts`. It tells `mcp-coder verify` (MarcusJellinghaus/mcp_coder#1374)
whether the token can read code-scanning alerts, so a `403` from
`check_branch_status` ("alerts not checked") is no longer unexplained.

## Architectural / design changes

- **One more probe in the existing module.** No new module, class, or public API.
  `verify_github_security` keeps its signature `(project_dir: Path) -> dict[str, CheckResult]`.
  It now returns five keys instead of four.
- **Status mapping beside the existing one.** New pure function
  `_classify_code_scanning_alerts(status: int) -> CheckResult`, next to
  `_classify_vulnerability_alerts`. It does not reuse
  `_permission_probes._classify_permission_response`, whose wording has no slot for
  scope-specific hints.
- **Raising HTTP call, status from the exception.** The probe uses
  `repo.requester.requestJsonAndCheck` (the Dependabot probe uses the non-raising
  `requestJson`). A normal return means 200. On failure the exception carries the status
  and headers.
- **Rate limit is checked before status.** Rate-limit exceptions are `GithubException`s
  with status 403, so `format_rate_limit_error(exc)` (from `_diagnostics`, the helper
  the PR-feedback path already uses) runs first. Otherwise a rate limit would read as
  "scope missing". `RetryError` and network errors have no `.status`, so they fall
  through to `network error: {exc}`.
- **HTTP call inline** in `verify_github_security`, in a try block before the return
  dict, as the issue's Decisions table says. The URL is built from `repo.url`, like
  `_probe_dependabot_alerts`. That is the same endpoint as `/repos/{owner}/{repo}/...`
  and also correct on GHE.
- **Report-only, exit-neutral**, like the other security probes. Every result has
  `severity="warning"`.

## Result mapping (`code_scanning_alerts`)

| Outcome | ok | value | error |
|---|---|---|---|
| 200 (normal return) | True | `scope present` | — |
| 403, not rate-limited | False | `scope missing or Advanced Security not enabled` | — |
| 404 | False | `scope missing or not configured` | — |
| Rate-limited (`format_rate_limit_error` non-None) | None | `not accessible` | helper message |
| Other `GithubException` status | None | `not accessible` | `HTTP {status}` |
| Any other exception | None | `not accessible` | `network error: {exc}` |
| Repository not resolvable (existing path) | None | `not checked` | `repository not accessible` |

## Files modified

- `src/mcp_workspace/github_operations/_security_probes.py`: new key, new classifier,
  inline probe, docstring counts four → five.
- `tests/github_operations/test_security_probes.py`: key-order test, `_make_repo` default
  for `requestJsonAndCheck`, one parametrized probe test, one call-shape test.

No files are created. No other module changes: `__init__.py` already exports
`verify_github_security`.

## Steps

- [Step 1](./step_1.md): add the `code_scanning_alerts` probe, with its tests (one commit).
