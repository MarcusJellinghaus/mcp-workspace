# Step 4 — Verify `network_proxy` probe + verify-local short-circuit (Parts C + C′)

> Read `pr_info/steps/summary.md` first. Add a proxy/reachability line to
> `verify_github`, and — only when the host is unreachable *and* no proxy applies
> — skip the two slow PyGithub calls so `verify` returns in ~3s instead of ~60s.
> Depends on Step 3 (`_collect_network_diagnostics`).

## WHERE
- **Modify** `src/mcp_workspace/github_operations/_network.py`
  - add `has_applicable_proxy(api_base_url: str) -> bool`
- **Modify** `src/mcp_workspace/github_operations/verification.py`
  - insert `network_proxy` `CheckResult` right after the `api_base_url` block
  - wrap the auth probe (`get_user`) **and** the `repo_accessible` block
    (`BaseGitHubManager` + `_get_repository`) in the short-circuit guard
- **Modify** `tests/github_operations/test_verification.py`

## WHAT
```python
# _network.py
def has_applicable_proxy(api_base_url: str) -> bool:
    """True if an http/https proxy is configured AND the host is not NO_PROXY-bypassed."""
```
```python
# verification.py — after api_base_url CheckResult:
diag = _collect_network_diagnostics(api_base_url)
result["network_proxy"] = CheckResult(
    ok=(diag["tcp_probe"] == "ok"),
    value=f"api={diag['host']}:443 tcp={diag['tcp_probe']} "
          f"proxy_env={diag['proxy_env']} pac={diag['pac']}",
    severity="warning",                     # never fail overall_ok on this
)
skip = diag["tcp_probe"] != "ok" and not has_applicable_proxy(api_base_url)
```

## HOW (integration points)
- Import `_collect_network_diagnostics`, `has_applicable_proxy` from `_network`.
- Place `network_proxy` so the section reads URL → proxy → auth (after
  `api_base_url`, before the auth probe).
- When `skip`:
  - `result["authenticated_user"] = CheckResult(ok=False,
    value="skipped — host unreachable", severity="warning")` — and do **not**
    call `github_client.get_user()`.
  - `result["repo_accessible"] = CheckResult(ok=False,
    value="skipped — host unreachable", severity="warning")` — and do **not**
    construct `BaseGitHubManager` / call `_get_repository()`.
  - `token_configured`, `repo_url`, branch-protection and permission-probe blocks
    already no-op safely when repo is not accessible (they issue zero API calls);
    leave them as-is.
- When **not** `skip` (tcp ok, *or* a proxy applies): run the existing checks
  unchanged so real auth/permission errors — and proxy-reachable hosts — surface.

## ALGORITHM
```
has_applicable_proxy(api_base_url):
    proxies = getproxies()
    if not ({"http","https"} & proxies.keys()): return False
    host = urlsplit(api_base_url).hostname
    return not urllib.request.proxy_bypass(host)     # proxy_bypass honours NO_PROXY
```
Severity rationale: `authenticated_user`/`repo_accessible` are normally
`severity="error"`; when skipped they become `"warning"` so a never-tested
network problem does not hard-fail `overall_ok`.

## DATA
- New result key `network_proxy: CheckResult` (`severity="warning"`), value is a
  single self-describing flattened line (renderer label tracked in mcp-coder #993).
- On skip: `authenticated_user`/`repo_accessible` carry
  `value="skipped — host unreachable"`, `ok=False`, `severity="warning"`.

## TDD — tests first (`test_verification.py`)
Monkeypatch `verification._collect_network_diagnostics`,
`verification.has_applicable_proxy`, the auth-probe client, and
`BaseGitHubManager._get_repository`:
- **tcp=ok** → auth probe + repo call **run** (assert they were invoked; normal
  results); `network_proxy.ok is True`, `severity == "warning"`.
- **tcp=timeout, no proxy** (`has_applicable_proxy → False`) → `get_user` and
  `_get_repository` **not called**; `authenticated_user`/`repo_accessible` ==
  `"skipped — host unreachable"`, `severity == "warning"`; `overall_ok` not
  forced False by these.
- **tcp=timeout, proxy applies** (`has_applicable_proxy → True`) → checks **run**
  normally (no skip).
- `has_applicable_proxy` unit tests: no proxy env → False; `HTTPS_PROXY` set and
  host not bypassed → True; host in `NO_PROXY` → False.

## Checks before commit
- `run_pylint_check`, `run_mypy_check`, `run_pytest_check` (fast-unit markers)
  pass. `./tools/format_all.sh` first.

## Commit
One commit: `has_applicable_proxy` + verify `network_proxy` + short-circuit + tests.
