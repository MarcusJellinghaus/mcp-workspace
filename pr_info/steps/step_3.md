# Step 3: `__requestRaw` wrapper in `build_github_client`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_3.md` only.
> TDD: write the tests first, then the implementation. Run pylint, pytest
> (`extra_args: ["-n", "auto"]`), mypy, `run_lint_imports_check` and `run_tach_check` until all
> pass. Format with `run_format_code`, then make exactly one commit for this step.

## Precondition

`hasattr(github.Requester.Requester, "_Requester__requestRaw")` in the installed PyGithub.
If it is False, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/github_operations/_client.py`
- `tests/github_operations/test_client_traffic_log.py` (new)
- `tach.toml`: add `{ path = "mcp_workspace.traffic_log" }` to `mcp_workspace.github_operations` `depends_on`

## WHAT

```python
def _install_traffic_log(client: Github) -> None:
    """Wrap this client's ``Requester.__requestRaw`` so each HTTP hop writes one line."""
```

`build_github_client` builds the client as today, then:

```python
if config.get_traffic_log_dir() is not None:
    _install_traffic_log(client)
return client
```

Module flag `_warned_missing = False` for the warn-once.

## HOW

- Imports in `_client.py`: `import time`, `from mcp_workspace import config`,
  `from mcp_workspace.traffic_log import error_status, log_request`.
- `client.requester` is PyGithub's public property for the client's `Requester`.
- The wrapper is set as an **instance** attribute: `requester._Requester__requestRaw = wrapper`.
  PyGithub's inner calls `self.__requestRaw(...)` resolve to it, so each 202/301/302 hop passes
  the wrapper again.
- `_client.py` is in `traffic_log._SKIP_MODULES`, so the wrapper frames stay out of the chain.
- Update the `build_github_client` docstring with one sentence about the traffic log.

## ALGORITHM

```
original = getattr(requester, "_Requester__requestRaw", None)
if original is None: warn once on logger ("traffic log disabled: PyGithub internals changed"); return
def wrapper(cnx, verb, url, *args, **kwargs):
    logged_url = url.split("?", 1)[0] if kwargs.get("follow_302_redirect") else url
    start = time.monotonic()
    try: status, headers, output = original(cnx, verb, url, *args, **kwargs)
    except Exception as exc:
        if not getattr(exc, "_traffic_logged", False):
            log_request(verb, logged_url, error_status(exc), getattr(exc, "headers", None), ms(start))
            try: setattr(exc, "_traffic_logged", True) except Exception: pass
        raise
    log_request(verb, logged_url, str(status), headers, ms(start)); return status, headers, output
requester._Requester__requestRaw = wrapper
```

## DATA

- The wrapper returns PyGithub's `(status, headers, output)` tuple unchanged.
- Hop lines repeat the final status/headers; duration is cumulative (accepted, see README step).

## Tests (`tests/github_operations/test_client_traffic_log.py`)

Enable with `monkeypatch.setattr("mcp_workspace.config.get_traffic_log_dir", lambda: tmp_path)`.
Replace the class method **before** building the client:
`monkeypatch.setattr(Requester, "_Requester__requestRaw", fake)` where
`fake(self, cnx, verb, url, requestHeaders, input, stream=False, follow_302_redirect=False)`
returns a canned tuple, raises, or (for hops) calls `self._Requester__requestRaw(...)` once
with a new path. Call `client.requester._Requester__requestRaw(None, "GET", "/x", {}, None)`.
Read lines from the single file in `tmp_path`.

- `Requester._Requester__requestRaw` exists in the installed PyGithub (no fake)
- 200 with `{"x-ratelimit-resource": "core", "x-ratelimit-remaining": "4211"}` → one line with
  `GET /x | 200 | core 4211`
- 301 hop to `/y`, then 200 → two lines (`/y` then `/x`), both `200`
- fake raises `GithubException(403, {"message": "x"}, {})` → one line `ERR GithubException 403`
- 301 hop then `RateLimitExceededExceedsMaxWait` → exactly one `ERR RateLimitExceededExceedsMaxWait` line
- `follow_302_redirect=True` with `?sig=secret` → no `sig=` in the file
- off (fixture default) → `"_Requester__requestRaw" not in vars(client.requester)`, no file
- missing attr: `monkeypatch.delattr(Requester, "_Requester__requestRaw")` → building two
  clients logs the warning once (caplog), no exception
- no network: `client = build_github_client("tok", "https://api.github.com")`;
  `repo = client.get_repo("o/r")` (lazy construction, no request);
  assert `repo._requester is client._Github__requester` and `client.requester is client._Github__requester`.
  If the identity fails, write one line to `pr_info/.blocked.txt` and stop.
