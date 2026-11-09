# Step 1 — Label disk cache: `new_expiry(max_age)` + `caching/labels.py`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **Step 1** exactly as described
> in `pr_info/steps/step_1.md`. Write the tests first, then the code. Run pylint,
> pytest (`-n auto`), mypy and lint-imports via the MCP tools until all pass,
> format the code, and make exactly one commit.

## WHERE

- `src/mcp_workspace/github_operations/caching/_store.py` (modify)
- `src/mcp_workspace/github_operations/caching/labels.py` (new)
- `tests/github_operations/caching/test_store.py` (extend)
- `tests/github_operations/caching/test_labels.py` (new). The existing
  autouse `cache_dir` fixture in `tests/github_operations/caching/conftest.py`
  already isolates the cache dir.

## WHAT

```python
# _store.py
def new_expiry(now: datetime, max_age: timedelta = MAX_AGE) -> str: ...

# labels.py
LABELS_CACHE_VERSION = 1
LABELS_MAX_AGE = timedelta(hours=24)
_SUFFIX = "labels"

class CachedLabels(NamedTuple):
    labels: list[LabelData]
    footer: str          # "Label cache last updated <fetched_at>[ — refresh failed: ...]"

def get_cached_labels(manager: IssueManager, refresh: bool = False) -> CachedLabels: ...
```

## HOW

- `labels.py` imports `LabelData` from `..labels_manager`, the `_store`
  helpers, `GitHubRateLimitError` and `rate_limit_guard` from `.errors`, and
  `format_for_cache`, `parse_iso_timestamp` and `utc_now` from
  `mcp_workspace.utils.timezone_utils`.
- Import `IssueManager` under `TYPE_CHECKING` only (see the cycle note in
  `caching/__init__.py`). Only `manager.repo_identifier` and
  `manager.get_available_labels()` are used.
- Do not add anything to `caching/__init__.py`.
- `new_expiry` keeps the 0.75–1.0 jitter: `now + max_age * jitter`.

## ALGORITHM

```
path = cache_file_path(manager.repo_identifier, "labels")
entry = _valid_entry(load_json(path, LABELS_CACHE_VERSION))   # None if fetched_at/labels malformed
now = utc_now()
if entry and not refresh and not is_expired(entry, now): return CachedLabels(entry.labels, _footer(entry.fetched_at))
try: with rate_limit_guard(): labels = manager.get_available_labels()
except GitHubRateLimitError as e: if entry is None: raise; return CachedLabels(entry.labels, _footer(entry.fetched_at, e))
fetched_at = format_for_cache(now); _save_cache_file(path, {version, fetched_at, expires_at=new_expiry(now, LABELS_MAX_AGE), labels})
return CachedLabels(labels, _footer(fetched_at))
```

`_valid_entry`: `fetched_at` must be a parseable str, and `labels` a list of
dicts that each have a str `name`. Otherwise return None (treated as missing).

## DATA

Footer strings (exact):
- `Label cache last updated <fetched_at>`
- `Label cache last updated <fetched_at> — refresh failed: rate limited until <format_for_cache(e.reset_at)>`
- `Label cache last updated <fetched_at> — refresh failed: rate limited (reset time unknown)` when `e.reset_at is None`

## Tests (write first)

`test_store.py`:
- `new_expiry(now, timedelta(hours=24))` lies within `[now+18h, now+24h]`.
- The default stays within `[now+4.5h, now+6h]`.

`test_labels.py` (a `MagicMock` manager with `repo_identifier = RepoIdentifier("owner", "repo")`):
- miss → fetches once, writes `owner…repo.labels.json` with all four LabelData fields, `fetched_at` and `expires_at`, and returns the plain footer
- valid entry → no fetch
- expired entry → refetch
- `refresh=True` on a valid entry → refetch
- rate limit (GithubException 403 with `x-ratelimit-remaining: 0` and a reset header) with an expired entry → returns the old labels and a footer containing `rate limited until`. The file is unchanged.
- rate limit with `refresh=True` on a valid entry → same fallback
- `RetryError` with unknown status (`make_retry_error` with a non-matching reason, or a bare `RetryError`) with an entry → footer `rate limited (reset time unknown)`
- rate limit with no entry → raises `GitHubRateLimitError`, and no file is written
- a 500 `GithubException` with an entry → raises, and the file is unchanged
- a corrupt file or a version mismatch → treated as a miss
- github.com and GHE repos with the same owner/name use different files
