# Step 3 — Exception mapping on the editor and token-user paths

Read [summary.md](./summary.md) first. It has the decision order and design.

## LLM prompt

> Implement Step 3 of `pr_info/steps/summary.md` as described in `pr_info/steps/step_3.md`.
> Use TDD. First add every case listed below to
> `tests/github_operations/issues/test_body_trust.py`. Then add `_call` to
> `issues/body_trust.py` and route the editor GraphQL query and the token-user lookup
> through it. Run pylint, pytest (`-n auto`), mypy, lint-imports and vulture. All must pass.
> Run format_code, then make one commit.

## Precondition

`body_trust.py` defines `_LookupFailed` and `_editor_login` (Step 2 is done), and
`caching/errors.py` defines `to_rate_limit_error`. If not, write one line to
`pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/github_operations/issues/body_trust.py`
- `tests/github_operations/issues/test_body_trust.py`

## WHAT

```python
def _call(fn: Callable[[], T]) -> T: ...
```

## HOW

- Add `to_rate_limit_error` to the `..caching.errors` import.
- Wrap the GraphQL query and `_cached_login` from Step 2 as zero-argument callables
  (e.g. `lambda`) passed to `_call`. Both calls stay inside the existing
  `try ... except _LookupFailed` block.

## ALGORITHM

```
_call(fn):  try fn() / except Exception as exc:
            rl = to_rate_limit_error(exc); if rl: raise rl from exc
            raise _LookupFailed(type(exc).__name__) from exc
```

## DATA

- The reason is a fixed constant or an exception type name, never exception text.
- Raises `GitHubRateLimitError` for every rate-limit shape on the editor and token-user
  paths.

## Tests — `tests/github_operations/issues/test_body_trust.py`

Use the harness from [step_1.md](./step_1.md).

### Parametrized table: exceptions by path (path, exception → expected)

- **Editor path** (`graphql` side effect):
  - `UnknownObjectException` → "UnknownObjectException".
  - A 400 with several errors, a 400 with NOT_FOUND plus another error, or a 400 with
    `errors: []` → "GithubException".
  - `GithubException` 401 / 403 or 500 → "GithubException".
  - `TypeError` → "TypeError".
  - `ConnectionError` → "ConnectionError", and the reason contains no message text.
  - A 5xx `RetryError` → "RetryError".
  - `RATE_LIMITED` in `data` (400, and also 502), a rate-limit header,
    `RateLimitExceededException`, a 429, or a `RetryError` with status 403 / 429 /
    unknown → `GitHubRateLimitError`.
- **Token-user path** (`get_user` side effect, editor not on the allowlist):
  - `GithubException` 500 → "GithubException".
  - A 5xx `RetryError` → "RetryError".
  - A rate-limit header, or a `RetryError` with status 403 / 429 / unknown →
    `GitHubRateLimitError`.

Existing `test_base_branch_trust.py` must still pass unchanged.
