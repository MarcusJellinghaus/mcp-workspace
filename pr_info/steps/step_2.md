# Step 2 — Bounded connect timeout on the raw artifact download (Part A′)

> Read `pr_info/steps/summary.md` first. The CI artifact ZIP download bypasses
> PyGithub with a raw `requests.get(timeout=60)` that also hangs up to 60s on an
> unreachable host. Give it a `(connect, read)` tuple so connect fast-fails in
> 10s while large downloads keep the 60s read budget. Independent of Step 1.

## WHERE
- **Modify** `src/mcp_workspace/github_operations/ci_results_manager.py`
  - class constant block near line 139 (`DEFAULT_REQUEST_TIMEOUT: int = 60`)
  - `_download_and_extract_zip` `requests.get(...)` call near line 325
- **Modify** `tests/github_operations/test_ci_results_manager_artifacts.py`

## WHAT
- Add a class constant `DEFAULT_CONNECT_TIMEOUT: int = 10  # seconds` next to
  `DEFAULT_REQUEST_TIMEOUT`.
- Change the call to:
```python
response = requests.get(
    url,
    headers=headers,
    allow_redirects=True,
    timeout=(self.DEFAULT_CONNECT_TIMEOUT, self.DEFAULT_REQUEST_TIMEOUT),
)
```

## HOW
- Single edit to the existing `requests.get` keyword; no new imports.
- `requests` interprets a 2-tuple as `(connect_timeout, read_timeout)`.

## ALGORITHM
None (single keyword change).

## DATA
- `timeout` is now `(10, 60)` instead of `60`.

## TDD — tests first
- Add a NEW test in the artifact test module that patches `requests.get` (as
  imported in `ci_results_manager`) to return a fake response wrapping a small
  in-memory ZIP; call `_download_and_extract_zip(url)`; assert `requests.get` was
  called with `timeout=(10, 60)`.
  (The existing artifact test mocks `_download_and_extract_zip` wholesale, so it
  makes no `timeout` assertion and needs no change.)

## Checks before commit
- `run_pylint_check`, `run_mypy_check`, `run_pytest_check` (fast-unit marker set
  as in Step 1) all pass. `./tools/format_all.sh` before committing.

## Commit
One commit: constant + call change + test.
