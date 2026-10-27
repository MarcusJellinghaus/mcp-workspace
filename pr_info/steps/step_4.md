# Step 4 — Per-process `Repository` raw-data cache

## LLM prompt
Read `pr_info/steps/summary.md`, then implement this step (`pr_info/steps/step_4.md`)
only. First run the scratch probe below. Write the tests first, then the
implementation. Run pylint, pytest (`-n auto`) and mypy; all must pass. Delete
`.scratch/`, run format_code, then make exactly one commit.

## Precondition — scratch probe
Save `.scratch/test_probe.py` and run it with
`run_pytest_check(extra_args=["-p", "no:cacheprovider", ".scratch/test_probe.py"])`.
Verify with the installed PyGithub, without network:
- `Github.create_from_raw_data(Repository, raw_data, headers)` exists and returns
  a `Repository` whose `_requester` is the calling client's requester;
- on such an object, reading `.raw_data`, `.raw_headers`, `.full_name` and
  `.default_branch` makes no HTTP request (patch `Requester.requestJsonAndCheck`
  to raise).

If either check fails, write one line to `pr_info/.blocked.txt` and stop.
Delete the probe with `delete_directory(".scratch", recursive=True)`.

## WHERE
- `src/mcp_workspace/github_operations/base_manager.py`
- `src/mcp_workspace/github_operations/__init__.py` — export `clear_repository_cache`
- `tests/conftest.py` (root) — autouse fixture
- `tests/github_operations/test_base_manager.py`

## WHAT
```python
def _token_key(base_url: str, token: str) -> tuple[str, str]
    # (base_url, sha256(token).hexdigest()); used by _cached_login too

# (api_base_url, sha256(token), full_name.lower()) -> (raw_data, raw_headers)
_repository_cache: dict[tuple[str, str, str], tuple[dict[str, Any], dict[str, Any]]] = {}

def clear_repository_cache() -> None
    """Forget every cached repository (used by tests)."""
```
`BaseGitHubManager._get_repository` signature unchanged.

## HOW
- `_cached_login` uses `key = _token_key(base_url, token)` (behaviour unchanged).
- Add `"clear_repository_cache"` to `__all__` in `base_manager.py` and to the
  import + `__all__` in `github_operations/__init__.py`.
- Root `tests/conftest.py`:
  ```python
  @pytest.fixture(autouse=True)
  def _reset_repository_cache() -> Generator[None, None, None]:
      clear_repository_cache(); yield; clear_repository_cache()
  ```
- `self._repository` stays the first-level, per-instance cache (tests set it directly).
- Update the `_get_repository` docstring Note (per-process raw-data cache).

## ALGORITHM
```
if self._repository is not None: return it
try: ident = self._repo_identifier
     key = (*_token_key(ident.api_base_url, self.github_token), ident.full_name.lower())
     if key in _repository_cache:
         raw, headers = _repository_cache[key]
         self._repository = self._github_client.create_from_raw_data(Repository, raw, headers); return it
     repo = self._github_client.get_repo(ident.full_name)
     _repository_cache[key] = (repo.raw_data, repo.raw_headers); self._repository = repo; return repo
except ...: unchanged error handling (nothing cached)
```
`self._repo_identifier` is read inside the `try`, as today: in `project_dir`
mode with no git remote its `ValueError` is caught by the existing
`except Exception` branch and the method returns `None`.

## DATA
Cache values are plain dicts. No lock: a simultaneous miss in two threads costs
one extra `get_repo`.

## Tests (`test_base_manager.py`)
Patch `build_github_client` to return a distinct `Mock` per manager.
- Two managers, same repo/token/host → `get_repo` called once in total; second
  manager's `create_from_raw_data` called with `(Repository, raw_data, raw_headers)`.
- Each manager's repository comes from its **own** client (second manager's
  object is the return value of its own client's `create_from_raw_data`, not
  the first manager's object) — covers "never share a Requester".
- Different token, different host, or different repo → cache miss; same repo
  with different case in `full_name` → hit.
- `get_repo` raising 404 → returns None, next manager calls `get_repo` again.
- `clear_repository_cache()` forces a new `get_repo`.
- Second call on the same manager uses `self._repository` (no client call).
- `project_dir` mode with `git_operations.get_repository_identifier` patched to
  return `None` → `_get_repository()` returns `None` (no exception), nothing cached.
- `_cached_login` tests still pass.

Existing tests that build several managers against one mocked `get_repo` and
now break: adjust them (set `_repository` directly or configure
`create_from_raw_data`); do not weaken assertions.
