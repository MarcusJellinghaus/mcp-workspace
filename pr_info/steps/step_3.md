# Step 3 — Network diagnostics helper + once-per-process error logging (Part B)

> Read `pr_info/steps/summary.md` first. When a GitHub call finally fails on an
> unreachable host, emit one WARNING line that reveals the API URL, Python proxy
> config (host:port), PAC presence, and a fix hint — once per process. The helper
> **owns** the exception gating so call sites stay one line and do not import
> `requests.exceptions`.

## WHERE
- **Create** `src/mcp_workspace/github_operations/_network.py`
- **Create** `tests/github_operations/test_network.py`
- **Modify** `tests/github_operations/conftest.py` — autouse guard-reset fixture
- **Modify** `src/mcp_workspace/github_operations/base_manager.py`
  - `get_authenticated_username()` — generic `except Exception` branch (has `base_url`)
  - `_get_repository()` — generic `except Exception` branch
    (use `self._repo_identifier.api_base_url`)
- **Modify** `src/mcp_workspace/github_operations/verification.py`
  - auth-probe generic `except Exception` branch (has `api_base_url`)

## WHAT
```python
# _network.py
def _collect_network_diagnostics(api_base_url: str) -> dict[str, str]: ...
def maybe_log_network_diagnostics(exc: BaseException, api_base_url: str) -> None: ...
def _reset_network_diagnostics_guard() -> None: ...        # test-only
# private: _proxy_host_port(url) -> str
#          _tcp_probe(host: str) -> str   # "ok"|"refused"|"timeout"|"dns_error"
#          _read_pac_autoconfig_url() -> str | None
```

## HOW (integration points)
- Each wired site adds, in its existing generic `except Exception as e:` branch
  (connection/read-timeout errors surface as `requests` exceptions → they land
  here, not in the `GithubException` branch):
  `maybe_log_network_diagnostics(e, <api_base_url-in-scope>)`
  then continues its current behaviour (return None / re-raise as ValueError).
- Import: `from mcp_workspace.github_operations._network import maybe_log_network_diagnostics`.
- `maybe_log_network_diagnostics` imports `from requests.exceptions import
  ConnectionError, Timeout` at `_network.py` module top (allowed by
  `requests_isolation` whitelist) and isinstance-gates on them — so base_manager
  / verification do **not** import `requests`.
- `winreg` is imported **lazily inside** the `sys.platform == "win32"` branch of
  `_read_pac_autoconfig_url` only.

## ALGORITHM
```
_tcp_probe(host):
    try: socket.create_connection((host, 443), timeout=3).close(); return "ok"
    except socket.gaierror:                 return "dns_error"   # DNS first (OSError subclass)
    except (socket.timeout, TimeoutError):  return "timeout"
    except ConnectionRefusedError:          return "refused"
    except OSError:                         return "refused"

_collect_network_diagnostics(api_base_url):
    host = urlsplit(api_base_url).hostname
    proxies = {s: _proxy_host_port(u) for s,u in getproxies().items() if s in ("http","https")}
    proxy_env = [n for n in ("HTTPS_PROXY","HTTP_PROXY","NO_PROXY") if n in os.environ or n.lower() in os.environ]
    pac = _read_pac_autoconfig_url()                  # "present" | None (win32 only)
    return {api_base_url, python_proxies, proxy_env, pac, tcp_probe=_tcp_probe(host)}

maybe_log_network_diagnostics(exc, api_base_url):
    global _LOGGED
    if not isinstance(exc, (ConnectionError, Timeout)): return
    if _LOGGED: return
    diag = _collect_network_diagnostics(api_base_url)
    logger.warning("GitHub API host unreachable: %s ; hint: if your browser uses a PAC proxy, set HTTPS_PROXY", diag)
    _LOGGED = True

_proxy_host_port(url):  p = urlsplit(url); return f"{p.hostname}:{p.port}"   # .hostname drops user:pass@
```

## DATA
- `_collect_network_diagnostics` returns `dict[str, str]` with keys:
  `api_base_url`, `python_proxies` (comma-joined `host:port`), `proxy_env`
  (comma-joined names or `"none"`), `pac` (`"present"`/`"absent"`),
  `tcp_probe` (`ok`/`refused`/`timeout`/`dns_error`).
- Module-level `_LOGGED: bool = False`.

## TDD — tests first (`test_network.py`)
- Monkeypatch `socket.create_connection`, `urllib.request.getproxies`, and
  (where invoked) `winreg`:
  - `gaierror` raised → `tcp_probe == "dns_error"` (asserts catch order).
  - `socket.timeout` → `"timeout"`; `ConnectionRefusedError` → `"refused"`;
    success → `"ok"`.
  - proxy URL `http://user:pass@proxy.corp:8080` reduces to `proxy.corp:8080`
    (no credentials).
- `maybe_log_network_diagnostics` fires exactly **once** across two calls
  (caplog at WARNING); a non-`ConnectionError/Timeout` exc logs nothing.
- `tests/github_operations/conftest.py`: add an `autouse=True` fixture that calls
  `_reset_network_diagnostics_guard()` so tests are order-independent.

## Checks before commit
- `run_pylint_check`, `run_mypy_check`, `run_pytest_check` (fast-unit markers)
  pass. Also run `run_lint_imports_check` (new module imports `requests.exceptions`
  — confirm `requests_isolation` still green). `./tools/format_all.sh` first.

## Commit
One commit: `_network.py` + 3 site wirings + conftest fixture + tests.
