# Summary — Issue #216: Bound GitHub timeout/retry + proxy/network diagnostics

## Problem

On restricted corporate networks, GitHub API calls hang for ~2.5 minutes then fail.
Two distinct root causes:

1. **The hang.** All `Github()` clients use bare defaults (`timeout=15`,
   `retry=GithubRetry(total=10)`). When the API host is silent, each request
   read-times-out at 15s and retries ~10× → minutes of opaque hang. A raw
   `requests.get(timeout=60)` in the CI artifact path hangs the same way.
2. **The opacity.** For `.ghe.com` data-residency tenants the API lives on a
   *different host* (`api.<tenant>.ghe.com`) than git/web. That host may be
   unreachable from Python specifically (no PAC-proxy support in `requests`),
   while git/the browser work. Nothing in the output made this visible.

## Goals (Acceptance)

- A *single* GitHub API call against an unreachable host fails in ~30s, not minutes.
- The raw artifact download connect-fails in ~10s instead of hanging 60s.
- 403 secondary-rate-limit backoff still works (do **not** use `retry=None`).
- On failure, logs reveal API URL + Python proxy config (host:port) + PAC
  presence + a fix hint, **once per process**.
- `mcp-coder verify` reports proxy/reachability without hanging: when the API
  host is unreachable **and no proxy is configured for it**, a ≤3s TCP probe
  triggers a verify-local short-circuit (returns in ~3s with
  `authenticated_user`/`repo_accessible` marked `"skipped — host unreachable"`).
  When the host is reachable **or** a proxy is configured, all checks run normally.

## Architectural / design changes

- **New centralized client factory (`_client.py`).** All three PyGithub client
  constructions now go through `build_github_client(token, base_url)`, which
  applies `timeout=10` and `retry=GithubRetry(total=2)`. This removes the three
  drifting bare-`Github()` call sites — the exact bug-class this issue is about.
  Timeout math is load-bearing: `10 × (1 + 2 retries) ≈ 30s` is the single-call
  acceptance bound. `GithubRetry(total=2)` also caps 403 backoff to 2 attempts —
  a deliberate trade-off, not an oversight.
- **New network-diagnostics module (`_network.py`).** Hosts
  `_collect_network_diagnostics(api_base_url)` (resolved URL, proxy host:port,
  proxy-env presence, Windows PAC presence, TCP-probe result) and
  `maybe_log_network_diagnostics(exc, api_base_url)`. The latter **owns** the
  `requests.exceptions.ConnectionError/Timeout` gating and a module-level
  once-per-process guard, so call sites need only one unconditional line and do
  **not** import `requests.exceptions`. A private `_reset_network_diagnostics_guard()`
  exists for test isolation. (Existing `_diagnostics.py` — header allow-list —
  is left unchanged.)
- **Verify-local short-circuit (`verification.py`).** A new `network_proxy`
  `CheckResult` (`severity="warning"`) is reported after `api_base_url`. When the
  TCP probe fails **and** no http/https proxy applies to the host
  (`urllib.request.proxy_bypass` honours `NO_PROXY`), the two slow PyGithub calls
  (`get_user` auth probe + `_get_repository`) are skipped and marked
  `"skipped — host unreachable"` (`severity="warning"`, so `overall_ok` is not
  hard-failed). This is sound **only** because the TCP probe, the auth probe, and
  the repo call all target the **same** `api_base_url` with the same token, and —
  per the proxy gate — take the same (direct) transport.
- **Dependency floor bump.** `pyproject.toml` `PyGithub>=1.59.0` → `>=2.1.0`
  (the `retry=`/`GithubRetry` API only exists from 2.1.0).
- **No import-linter / tach contract change.** `pygithub_isolation` and
  `requests_isolation` already whitelist `github_operations.**`, so the new
  `_client.py` (imports `github`) and `_network.py` (imports `requests.exceptions`,
  `socket`, `urllib`, lazy `winreg`) are compliant by location.

## Load-bearing constraints (do not "simplify" away)

- TCP-probe host is parsed from `api_base_url` via `urllib.parse`, **not** from
  `hostname` — or it probes the wrong host on `.ghe.com` tenants.
- `winreg` is imported **lazily inside** the `sys.platform == "win32"` branch —
  a top-level import breaks Linux CI at import time.
- TCP-probe exception order: catch `socket.gaierror` (DNS) **before**
  `ConnectionRefusedError`/`OSError` (gaierror is an OSError subclass).
  Map: `gaierror`→`dns_error`, `socket.timeout`/`TimeoutError`→`timeout`,
  `ConnectionRefusedError`→`refused`.
- The direct TCP probe ignores proxies; `requests`/PyGithub honour `HTTPS_PROXY`.
  So the short-circuit is gated on **no applicable proxy** — otherwise a user who
  set `HTTPS_PROXY` (the tool's own hint) would still see a stale "unreachable".
- `network_proxy` must stay `severity="warning"` (`overall_ok` counts only
  error-severity checks).
- Keep heavy imports (`github`) inside function bodies / dedicated modules — do
  not add module-top `github`/`git` imports to anything on the `server.py` import
  path (`tests/test_startup_performance.py` enforces this).

## Files created / modified

**Created**
- `src/mcp_workspace/github_operations/_client.py` — client factory + constants
- `src/mcp_workspace/github_operations/_network.py` — diagnostics + once-per-process log
- `tests/github_operations/test_client.py`
- `tests/github_operations/test_network.py`

**Modified**
- `src/mcp_workspace/github_operations/base_manager.py` — use factory at 2 sites;
  wire `maybe_log_network_diagnostics` at 2 sites
- `src/mcp_workspace/github_operations/verification.py` — use factory at auth
  probe; wire diagnostics; add `network_proxy` check + verify-local short-circuit
- `src/mcp_workspace/github_operations/ci_results_manager.py` — `(connect, read)`
  timeout tuple on the raw `requests.get`
- `pyproject.toml` — `PyGithub>=2.1.0`
- `tests/github_operations/conftest.py` — autouse fixture calling
  `_reset_network_diagnostics_guard()`
- `tests/github_operations/test_ci_results_manager_artifacts.py` — assert tuple timeout
- `tests/github_operations/test_verification.py` — short-circuit matrix

## Implementation steps (one commit each)

1. **Step 1 — Client factory (Part A)** + PyGithub floor bump. Foundation.
2. **Step 2 — Artifact download connect timeout (Part A′).** Independent of Step 1.
3. **Step 3 — Network diagnostics helper + once-per-process error logging (Part B).**
4. **Step 4 — Verify `network_proxy` probe + short-circuit (Parts C + C′).** Depends on Step 3.

## Related
- Downstream follow-up: **mcp-coder #993** — add `_LABEL_MAP` entry + rendering
  for the `network_proxy` check (renderer label; out of scope here).
