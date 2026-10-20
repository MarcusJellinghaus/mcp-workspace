# Step 1 — `_LoggingGithubRetry` with tests

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_1.md`.
> TDD: write the tests first, then the class. Do not touch `build_github_client`
> yet (that is step 2). Run pylint, pytest (`-n auto`), mypy, and
> lint-imports; all must pass. Run format_code, then make exactly one commit.

## Precondition

If `github.GithubRetry` no longer replaces `get_backoff_time` on the instance
returned from `increment`, or `GithubRetry.new` no longer forwards kwargs to
`Retry.new` (check with `get_library_source`), write one line to
`pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/github_operations/_client.py`
- `tests/github_operations/test_client.py`

## WHAT

```python
class _LoggingGithubRetry(GithubRetry):
    """GithubRetry that logs any sleep longer than 15s on our own logger."""

    def sleep(self, response: BaseHTTPResponse | None = None) -> None: ...
```

## HOW

Top of `_client.py`:

```python
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from github import Auth, Github, GithubRetry

if TYPE_CHECKING:
    from urllib3 import BaseHTTPResponse

logger = logging.getLogger(__name__)
```

No other module changes. Keep everything inside `sleep()` (no helper function).

## ALGORITHM

```
retry_after = self.get_retry_after(response) if self.respect_retry_after_header and response else None
wait = retry_after or self.get_backoff_time()          # truthy check: Retry-After 0 -> backoff
if wait > 15:
    headers = response.headers if response is not None else {}
    if "Retry-After" in headers: msg = Retry-After text
    elif headers.get("X-RateLimit-Remaining") == "0": msg = primary text (+ " (resets HH:MM:SS UTC)" if reset.isdigit())
    else: msg = secondary text
    if self.history: msg += f" ({self.history[-1].method} {self.history[-1].url})"
    logger.info(msg)
super().sleep(response)                                 # response unchanged; raw wait slept
```

Reset time: `datetime.fromtimestamp(int(reset), timezone.utc).strftime("%H:%M:%S")`.
Seconds in the message: `round(wait)`. Exact texts are in `summary.md`.

## DATA

`sleep()` returns `None`. One `logging.INFO` record on
`mcp_workspace.github_operations._client` per sleep > 15s; none otherwise.

## Tests (`tests/github_operations/test_client.py`)

Imports: `io`, `json`, `logging`, `time`, `pytest`, `urllib3`,
`from urllib3.util.retry import Retry`, and `_LoggingGithubRetry`. Reuse the
existing `MODULE` constant.

Helper:

```python
def _run(caplog: pytest.LogCaptureFixture, headers: dict[str, str], message: str = "") -> tuple[float, list[str], Retry]:
    """Run increment -> sleep on a 403 stub; return (slept, our messages, new retry)."""
    caplog.set_level(logging.INFO, logger=MODULE)
    body = io.BytesIO(json.dumps({"message": message}).encode())
    stub = urllib3.HTTPResponse(body=body, headers=headers, status=403, preload_content=False)
    new_retry = _LoggingGithubRetry(total=2).increment("GET", "/user", response=stub)
    with patch("urllib3.util.retry.time.sleep") as mock_sleep:
        new_retry.sleep(stub)
    slept = mock_sleep.call_args.args[0]
    return slept, [r.getMessage() for r in caplog.records if r.name == MODULE], new_retry
```

Cases:

1. **Primary** — message `"API rate limit exceeded for user ID 1."`, headers
   `X-RateLimit-Remaining: "0"`, `X-RateLimit-Reset: str(int(time.time()) + 600)`.
   Assert `595 < slept <= 602`, one message containing
   `"rate limit exhausted"`, `f"{round(slept)}s"`, `"resets"`, `"(GET /user)"`, and
   `type(new_retry) is _LoggingGithubRetry`.
2. **Secondary** — message `"You have exceeded a secondary rate limit."`, no
   `Retry-After`, no `X-RateLimit-Remaining: 0`. Assert `slept == 60`, one
   message containing `"secondary rate limit"` and `"60s"`.
3. **Retry-After 120** — headers `Retry-After: "120"`. Assert `slept == 120`,
   one message containing `"Retry-After"` and `"120s"`.
4. **Boundary** — `@pytest.mark.parametrize("seconds", ["14", "15"])`, headers
   `Retry-After: seconds`. Assert `slept == int(seconds)` and no messages.

Check only reason text and seconds, not the full message.

## Commit

`feat(github_operations): log GithubRetry sleeps over 15s (#330)`
