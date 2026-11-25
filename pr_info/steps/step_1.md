# Step 1 — `_push_retry.py`: 500 matcher and retry loop

## LLM prompt

Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_1.md`).
Implement Step 1 only, test first: write `tests/git_operations/test_push_retry.py`
with the tests below, then create `src/mcp_workspace/git_operations/_push_retry.py`.
Do not touch `remotes.py` or `branches.py` in this step. Run pylint, pytest
(`-n auto`) and mypy until all pass, run the formatter, and make exactly one commit.

## WHERE

- create `src/mcp_workspace/git_operations/_push_retry.py`
- create `tests/git_operations/test_push_retry.py`
- Not exported from `git_operations/__init__.py` (private module, like `_subprocess_git.py`).

## WHAT

```python
"""Retry a git push that GitHub answered with HTTP 500.

<module docstring: what is retried (only GitHub HTTP 500, recognised from
stderr, never by exit code), 3 attempts, waits 5 s / 15 s, one WARNING per
retry because a recovered 500 must stay visible (Jenkins build unstable).>
"""

import re
import time
from collections.abc import Callable
from typing import Any, TypeVar

from git.exc import GitCommandError

from mcp_workspace.utils.url_credentials import scrub_credentials

from .core import logger

T = TypeVar("T")

_RETRY_WAITS: tuple[float, ...] = (5.0, 15.0)

_HTTP_500 = re.compile(
    r"\[remote rejected\] .*\(Internal Server Error\)"
    r"|The requested URL returned error: 500\b"
)

def _match_500(stderr: str | None) -> str | None: ...
def retry_500(fn: Callable[..., T], *args: Any) -> T: ...
```

## HOW

- Imports only `core.logger`, `utils.url_credentials.scrub_credentials`,
  `git.exc.GitCommandError`, `re`, `time` — all already allowed for
  `mcp_workspace.git_operations` in `tach.toml`.
- Must NOT import `run_git_timed` (callers pass it in).
- Waits use `time.sleep` (module-level `import time`, so tests patch
  `mcp_workspace.git_operations._push_retry.time.sleep`).

## ALGORITHM

```
_match_500(stderr):
    for line in (stderr or "").splitlines():
        if _HTTP_500.search(line): return line.strip()
    return None

retry_500(fn, *args):
    for attempt, wait in enumerate(_RETRY_WAITS, start=1):
        try: result = fn(*args)
        except GitCommandError as e:
            line = _match_500(e.stderr);  if line is None: raise
        else:
            failed = isinstance(result, dict) and not result["success"]
            line = _match_500(result["stderr"]) if failed else None
            if line is None: return result
        logger.warning("git push got GitHub HTTP 500 (attempt %d of %d), retrying in %g s: %s",
                       attempt, len(_RETRY_WAITS) + 1, wait, scrub_credentials(line))
        time.sleep(wait)
    return fn(*args)
```

Any exception other than `GitCommandError` propagates on the first attempt
(not caught).

## DATA

- `_match_500` → the matched stderr line (stripped) or `None`.
- `retry_500` → whatever `fn` returns (GitPython push: `str`; `run_git_timed`:
  `GitOutput` dict). On final failure: the last attempt's exception is raised
  or the last attempt's failed result is returned.

## Tests (`tests/git_operations/test_push_retry.py`)

Module docstring + `MODULE = "mcp_workspace.git_operations._push_retry"`.
Patch `f"{MODULE}.time.sleep"` in every loop test. Build GitPython errors as
real `GitCommandError(["git", "push", "origin", "b"], 1, stderr=...)` so the
decorated `\n  stderr: '...'` form is produced by GitPython itself.

Matcher (`_match_500`), parametrized:
- `"remote: Internal Server Error\n ! [remote rejected] b -> b (Internal Server Error)\nerror: failed to push some refs to 'https://github.com/o/r.git'"` → matches the `[remote rejected]` line.
- `"remote: Internal Server Error\nfatal: unable to access 'https://github.com/o/r.git/': The requested URL returned error: 500"` → matches the `fatal:` line.
- remote-delete shape without `->`: `" ! [remote rejected] b (Internal Server Error)"` → matches.
- both shapes again taken from a real `GitCommandError(...).stderr` (decorated) → match.
- `"... The requested URL returned error: 5000"` → `None`.
- non-fast-forward `" ! [rejected]        b -> b (non-fast-forward)"` → `None`.
- `None` and `""` → `None`.

Loop (`retry_500`) with a fake `fn` (`MagicMock(side_effect=[...])`):
- GitPython shape: 500 error, then `"ok"` → returns `"ok"`, 2 calls, sleep called once with `5.0`.
- GitPython shape: 500 on all 3 attempts → raises the **third** error object (`pytest.raises` + `is` check), 3 calls, sleeps `[5.0, 15.0]`.
- dict shape (`run_git_timed`-like `{"success": False, "stderr": <500 text>, ...}`) then `{"success": True, ...}` → returns the success dict, 2 calls.
- dict shape 500 three times → returns the third failed dict, 3 calls.
- exactly one call, no sleep, for: non-fast-forward `GitCommandError`; stale lease (`" ! [rejected] b -> b (stale info)"`); auth failure (`"fatal: Authentication failed for 'https://github.com/o/r.git/'"`); timeout dict `{"success": False, "stderr": None, ...}`; `OSError` raised by `fn` (propagates).
- successful dict on first call → returned, one call.
- logging (`caplog` at WARNING): 500 twice then success → exactly 2 WARNING records; each contains `attempt 1 of 3` / `attempt 2 of 3` and the wait. With stderr `"fatal: unable to access 'https://user:secret@github.com/o/r.git/': The requested URL returned error: 500"` the WARNING text contains no `secret`.
