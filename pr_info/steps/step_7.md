# Step 7 — `origin_fetch`: fetch with retry

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_7.md`.
> Write the tests first, then the implementation. Use the MCP tools from `.claude/CLAUDE.md`.
> Run pylint, pytest (`extra_args: ["-n", "auto"]`), mypy and lint-imports; all must pass.
> Run `run_format_code`, then make exactly one commit for this step.

## WHERE

- `src/mcp_workspace/git_operations/origin_fetch.py` (new; nothing imports it yet)
- `tests/git_operations/test_origin_fetch.py` (new)

## WHAT

```python
FETCH_ARGS: tuple[str, ...] = (
    "-c", "maintenance.auto=false", "-c", "gc.auto=0",
    "fetch", "--quiet", "--no-recurse-submodules", "--no-prune", "origin",
)

class FetchOutcome(NamedTuple):
    attempted: bool          # False: not a git repo, or no origin remote
    failure: str | None      # None on success; scrubbed reason otherwise

def has_origin_remote(path: Path) -> bool: ...
def fetch_origin(path: Path, timeout: float = 10.0) -> FetchOutcome: ...
```

## HOW

- `has_origin_remote` opens `Repo(path, search_parent_directories=False)` (GitPython opens
  the reference path itself before any subprocess runs, so a parent repo is never fetched);
  `InvalidGitRepositoryError` / `NoSuchPathError` → `False`; closes via `_close_repo_safely`.
- `fetch_origin` uses `run_git_timed(path, *FETCH_ARGS, timeout=timeout)` from
  `_subprocess_git` (kills on timeout, non-interactive env, scrubbed output). Not
  `remotes.fetch_remote` (bool only).
- Timeout is detected from the result (`returncode is None` and "timed out" in `error`),
  never from stderr text.

## ALGORITHM

```
if not has_origin_remote(path): return FetchOutcome(False, None)
for _ in range(2):
    out = run_git_timed(path, *FETCH_ARGS, timeout=timeout)
    if out["success"]: return FetchOutcome(True, None)
    reason = first non-empty line of out["stderr"] or out["error"]
    if out["returncode"] is None and "timed out" in (out["error"] or ""): break
return FetchOutcome(True, reason)
```

## DATA

`FetchOutcome(attempted=True, failure="git fetch timed out after 10 s")`,
`FetchOutcome(True, "fatal: unable to access 'https://127.0.0.1:1/x.git/': …")`,
`FetchOutcome(True, None)`, `FetchOutcome(False, None)`.

## Tests (write first)

- Real local origin: push a new commit from a second clone; `fetch_origin(work)` →
  `FetchOutcome(True, None)` and `refs/remotes/origin/main` now has the new SHA; `HEAD`,
  the checked-out branch, the index (`git diff --cached` empty) and a dirty working-tree
  file are unchanged (AC: auto-fetch never modifies the working tree, index or branch).
- No origin / plain folder / folder nested inside a checkout → `FetchOutcome(False, None)`
  and `run_git_timed` is not called (patch it).
- Mock `run_git_timed`:
  - fail (exit 1, stderr "fatal: x\nmore") then succeed → `(True, None)`, 2 calls;
  - fail twice → `(True, "fatal: x")`, 2 calls;
  - fail with empty stderr → reason is `error` ("git fetch failed (exit 1)");
  - timeout (`returncode=None`, error "git fetch timed out after 10 s") → 1 call,
    reason "git fetch timed out after 10 s".
- Called arguments equal `FETCH_ARGS` and `timeout=10.0` by default.
