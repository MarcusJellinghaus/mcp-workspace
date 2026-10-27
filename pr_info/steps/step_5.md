# Step 5: `caching/pull_requests.py` — layer 1 (open-PR snapshot, base tips, save/merge)

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_5.md` exactly.
> TDD: write the tests first, then the code. Run pylint, pytest (`-n auto`) and mypy;
> all must pass. One commit.

## Probe first

Before writing the parser, run a scratch probe (`.scratch/test_probe.py`, see CLAUDE.md
"Scratch probes") that builds a PyGithub `PullRequest` from a pull-request-simple JSON
payload (`github.PullRequest.PullRequest(requester, {}, raw, completed=False)` with a Mock
requester) and asserts that reading `number`, `head.ref`, `head.sha`, `head.label`,
`base.ref`, `updated_at`, `user.login`, `author_association`, `draft` makes **no**
requester call. If it does, parse from `pr._rawData` (dict) instead. Delete `.scratch/` afterwards.

## WHERE

- Create `src/mcp_workspace/github_operations/caching/pull_requests.py`
- Tests: `tests/github_operations/caching/test_pull_requests_snapshot.py`

## WHAT

```python
PRS_CACHE_VERSION = 1

class OpenPullRequest(TypedDict):
    number: int
    head_branch: str
    head_sha: str
    head_label: str          # "<owner>:<branch>"
    base_branch: str
    updated_at: str | None
    user: str | None
    author_association: str
    draft: bool

class PullRequestCache:
    @classmethod
    def load(cls, pr_manager: PullRequestManager) -> "PullRequestCache": ...
    def find_pr(self, branch: str) -> OpenPullRequest | None: ...
    def base_tip(self, base_branch: str) -> str: ...            # used by step 6
    def save(self) -> None: ...

def _fetch_open_prs(repo: Repository) -> list[OpenPullRequest]: ...   # private, undecorated
def _parse_pr(pr: PullRequest) -> OpenPullRequest: ...                # no _pr_to_data
```

## HOW

- `load`: `path = cache_file_path(pr_manager.repo_identifier, "prs")`;
  `data = load_json(path, PRS_CACHE_VERSION)`; keep `self._loaded_snapshot = data.get("snapshot")`,
  `self._loaded_results = data.get("results", {})`, `self._fetched_results = {}`,
  `self._snapshot = None` (filled lazily), `self._rate_limited = False`.
- Snapshot is fetched **lazily** on first `find_pr` / `base_tip` call:
  - If the loaded snapshot's `fetched_at` is within `DUPLICATE_PROTECTION_SECONDS` →
    use it as-is (list **and** base tips skipped).
  - Else `with rate_limit_guard(): prs = _fetch_open_prs(repo)` using
    `pr_manager._get_repository()` (raise `RuntimeError` if `None`); new snapshot
    `{"fetched_at": now, "prs": {str(n): pr}, "base_tips": {}}`, mark it fetched.
- `base_tip(base)`: return `snapshot["base_tips"][base]` if present, else
  `with rate_limit_guard(): sha = repo.get_branch(base).commit.sha`, store in the snapshot
  (once per distinct base per run). Within the duplicate window a missing base is still fetched.
- `find_pr(branch)`: `f"{repo_identifier.owner}:{branch}"` matched against `head_label`
  (fork PRs with the same branch name don't match). `None` if no match.
- `_fetch_open_prs`: `repo.get_pulls(state="open")`, iterate all pages, `_parse_pr` each.
  Undecorated: every exception propagates (never `list_pull_requests`, which returns `[]`).
- Any `GitHubRateLimitError` raised from a public method sets `self._rate_limited = True`
  (one small helper `_guarded(fn, *args)` used by every public method).
- `save()`: no-op if `_rate_limited`, or nothing fetched this run. Else:
  reload `disk = load_json(path, PRS_CACHE_VERSION)`;
  snapshot = newer of (disk snapshot, my snapshot) by `fetched_at`;
  results = disk results, drop expired slots (via `_store.is_expired`), overlay my fetched
  results (per PR, per slot — step 6 fills them), then drop PR keys not in the snapshot;
  write `{"version": 1, "snapshot": ..., "results": ...}`.

## ALGORITHM

```
_snapshot_or_fetch():
    if self._snapshot: return it
    s = loaded_snapshot
    if s and within(s.fetched_at, DUPLICATE_PROTECTION_SECONDS): self._snapshot = s
    else: self._snapshot = {fetched_at: now, prs: _fetch_open_prs(repo), base_tips: {}}; mark fetched
save: pick newer snapshot; merge results (disk − expired) ∪ mine; prune keys ∉ snapshot.prs; write
```

## DATA

`.prs.json`:
```json
{"version": 1,
 "snapshot": {"fetched_at": "...", "prs": {"42": {OpenPullRequest}}, "base_tips": {"main": "sha"}},
 "results": {"42": {"mergeable_state": {"fp": [...], "value": "clean", "expires_at": "..."}}}}
```

## Tests (`test_pull_requests_snapshot.py`, Mock `PullRequestManager` + Mock repo)

- Parser: list item mock → `OpenPullRequest`; `_pr_to_data` not used; `mergeable` not accessed
  (use a Mock with `PropertyMock` on `mergeable*`/`merged` that fails the test if read).
- Pagination: all items from `get_pulls` iterated.
- `find_pr` matches own `owner:branch`; fork PR (`other:branch`) → `None`; no PR → `None`.
- Duplicate protection: snapshot saved < 60 s ago → `get_pulls` and `get_branch` not called;
  older → called.
- `base_tip` called twice for `main` → one `get_branch` call.
- `get_pulls` raises 500 → exception propagates, `save()` writes nothing new
  (a fetch error is never stored as "no PR").
- `get_pulls` raises rate limit → `GitHubRateLimitError`; `save()` writes no file.
- Corrupt / version-mismatched `.prs.json` → rebuild, no exception.
- Merge: disk has a newer snapshot than mine → disk snapshot kept; disk results for a PR
  not in the resulting snapshot are pruned (closed PR does not come back).
