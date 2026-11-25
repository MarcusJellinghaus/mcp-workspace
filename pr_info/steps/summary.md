# Summary — Retry git push on GitHub HTTP 500 (all push paths), issue #421

## Goal

A `git push` that GitHub answers with HTTP 500 is retried (3 attempts total,
waits 5 s then 15 s). Every other failure behaves exactly as today. Return
values, error messages and final-failure logging of the four push functions
are unchanged.

## Architectural / design changes

- **New private module `git_operations/_push_retry.py`** holding:
  - `_RETRY_WAITS = (5.0, 15.0)` — the waits; attempt count is `len(_RETRY_WAITS) + 1`.
  - `_match_500(stderr)` — returns the first stderr line that shows a GitHub
    HTTP 500, stripped, else `None`. Line-by-line search, not anchored to the
    line start (GitPython decorates stderr as `\n  stderr: '...'`), no `->`
    required (remote delete shape).
  - `retry_500(fn, *args)` — one retry loop for both push mechanisms:
    - GitPython (`repo.git.push`) **raises** `GitCommandError` → match `e.stderr`;
      no match → bare `raise`.
    - `run_git_timed` **returns** a dict with `success`/`stderr` → match `stderr`
      only when `success` is False; no match → return the result.
    - On a match: one WARNING (attempt, total, wait, scrubbed line), `time.sleep(wait)`.
    - The last attempt is a plain `return fn(*args)` outside the loop, so the
      last attempt's exception/result reaches the caller unchanged.
- **Call sites wrapped, nothing else restructured.** `repo.git.push(...)` →
  `retry_500(repo.git.push, ...)`; `run_git_timed(...)` →
  `retry_500(run_git_timed, ...)`. The existing `except` blocks still receive
  the (last) `GitCommandError`, so `git_push`'s `error` format — and mcp_coder's
  `_REJECTED_STATUS_LINE` parsing of it — is unchanged.
- `_push_retry.py` does **not** import `run_git_timed`; `remotes.py` passes it
  in, so existing `patch("...remotes.run_git_timed")` tests keep working.
- Retry decision is purely a positive stderr match; exit codes are never used.
  Timeout / git-not-found results have `stderr=None` → never retried.
- No changes to: MCP tool docstrings/output, `fetch_remote`, `pull`, ls-remote
  probes, `tach.toml` (new module only uses `core.logger`, `utils.url_credentials`,
  `git.exc`, `re`, `time`), mcp_coder.

## Files

| Action | Path |
|---|---|
| create | `src/mcp_workspace/git_operations/_push_retry.py` |
| create | `tests/git_operations/test_push_retry.py` |
| modify | `src/mcp_workspace/git_operations/remotes.py` (`git_push`, `push_branch`, `push_current_branch`: call sites, docstring line, delete 5 step comments, 1 import) |
| modify | `src/mcp_workspace/git_operations/branches.py` (`delete_branch`: call site, docstring line, 1 import) |

## Line budget

`remotes.py` is 747 lines; CI fails above 750 and it is not on
`.large-files-allowlist`. Net change ≈ −1 (+1 import, +3 docstring lines,
−5 step comments, call sites stay one line each). Never add it to the
allowlist or move unrelated functions.

## Steps

1. `step_1.md` — `_push_retry.py` (matcher, loop, waits) + direct tests.
2. `step_2.md` — GitPython call sites: `git_push`, `push_branch`, `delete_branch` + call-site tests.
3. `step_3.md` — `push_current_branch` call site + tests + final file-size gate.

## Checks for every step

- `mcp__mcp-tools-py__run_pylint_check`
- `mcp__mcp-tools-py__run_pytest_check` with `extra_args=["-n", "auto"]`
- `mcp__mcp-tools-py__run_mypy_check`
- `mcp__mcp-tools-py__run_format_code` before committing
