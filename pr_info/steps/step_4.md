# Step 4: `caching/branches.py` — `BranchLookupCache` + invalidation

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_4.md` exactly.
> TDD: write the tests first, then the code. Run pylint, pytest (`-n auto`) and mypy;
> all must pass. One commit.

## WHERE

- Create `src/mcp_workspace/github_operations/caching/branches.py`
- Modify `src/mcp_workspace/github_operations/issues/branch_manager.py` — invalidation hook
- Tests: `tests/github_operations/caching/test_branches.py`
  (uses the `cache_dir` autouse fixture from step 2's `conftest.py`)

## WHAT

```python
BRANCHES_CACHE_VERSION = 1

class BranchLookupCache:
    @classmethod
    def load(cls, manager: IssueBranchManager) -> "BranchLookupCache": ...
    def lookup(self, issue: IssueData) -> BranchLookup: ...
    def save(self) -> None: ...

def invalidate_branch_entry(repo_identifier: RepoIdentifier, issue_number: int) -> None:
    """Load the file, delete the issue's entry, save. Never raises."""
```

## HOW

- Add to `_store.py` (shared with step 5):
  `MAX_AGE = timedelta(hours=6)`;
  `def new_expiry(now: datetime) -> str` → `format_for_cache(now + MAX_AGE * random.uniform(0.75, 1.0))`;
  `def is_expired(entry: dict, now: datetime) -> bool` (missing/unparseable `expires_at` → expired).
- `load`: `path = cache_file_path(manager.repo_identifier, "branches")`;
  `entries = load_json(path, BRANCHES_CACHE_VERSION).get("entries", {})`.
  Keep `self._loaded`, `self._fetched: dict[str, dict] = {}`, `self._rate_limited = False`.
- `lookup(issue)`: key `str(issue["number"])`, `fp = [issue["updated_at"]]`.
  Hit if `entry["fp"] == fp` and not expired → `BranchLookup(entry["status"], entry["branch"])`.
  Miss → `with rate_limit_guard(): result = manager.resolve_branch_for_issue(n, owner, repo_name)`
  (owner/name from `manager.repo_identifier`). On `GitHubRateLimitError` set
  `_rate_limited = True` and re-raise. Any other exception propagates; nothing stored.
  On success store `{"fp", "status", "branch", "expires_at"}` in `_fetched`, return result.
  All three statuses are cached.
- `save()`: no-op if `_rate_limited` or nothing fetched. Else reload with `load_json`,
  drop expired, overlay `_fetched`, write `{"version": 1, "entries": ...}` with `_save_cache_file`.
- `invalidate_branch_entry`: `load_json` → `entries.pop(key, None)` → save if it was
  present. Wrap in `try/except Exception` → log warning (must never break branch creation).
- `branch_manager.create_remote_branch_for_issue`: on a successful result (before
  `return last_result` when `success`), call
  `from ..caching.branches import invalidate_branch_entry` **inside the method**
  (comment: avoids load-time cycle issues/_cache_io → caching._store / caching.branches → issues),
  then `invalidate_branch_entry(self.repo_identifier, issue_number)`.

## ALGORITHM

```
lookup(issue):
    e = fetched.get(k) or loaded.get(k)
    if e and e.fp == fp and not is_expired(e, now): return BranchLookup(e.status, e.branch)
    with guard: r = manager.resolve_branch_for_issue(...)
    fetched[k] = {fp, status=r.status, branch=r.branch, expires_at=new_expiry(now)}; return r
save: if rate_limited or not fetched: return; disk = load_json(...).entries; drop expired; disk.update(fetched); write
```

## DATA

`.branches.json`:
```json
{"version": 1, "entries": {"123": {"fp": ["2026-10-27T10:00:00Z"], "status": "not_found", "branch": null, "expires_at": "..."}}}
```

## Tests (`test_branch_manager` mocked via `Mock(spec=IssueBranchManager)`)

- Miss → resolver called, `save()` writes; second `load` + `lookup` with same `updated_at` → resolver not called.
- found / not_found / ambiguous each cached.
- Changed issue `updated_at` → re-resolved. Expired entry → re-resolved.
- Resolver raises `BranchLookupError` / 500 `GithubException` → propagates, entry not stored, file unchanged.
- Resolver raises rate limit → `GitHubRateLimitError`; later `save()` writes nothing (file absent).
- Corrupt file / version mismatch → empty cache, no exception.
- Two caches loaded from the same file, each fetches a different issue, both save → both entries present.
- Invalidation: A loaded with entry #5; `invalidate_branch_entry(...)` deletes it; A fetches #6 and saves → #5 still absent.
- Expired entry on disk is dropped at save.
- `create_remote_branch_for_issue` success → `invalidate_branch_entry` called; failure → not called.
