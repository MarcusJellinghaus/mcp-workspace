# Step 4 — Tolerant fetch, retry re-key, explicit WARNING log

**Depends on:** steps 1, 2, 3. **Commit:** tests + implementation + checks green.

## Goal

Preserve partial GraphQL data, re-key the retry from a synthetic status to actual
usability, and make the WARNING log explicit now that the exception is returned rather than
raised.

**Why this is one step and not three:** the moment `fetch_review_data` calls
`requestJsonAndCheck`, `graphql_query` no longer raises, so the old 400/404 retry trigger is
dead code that same instant; and the 4-tuple cannot land without its `pr_manager` unpack.
Splitting leaves the tree red.

## WHERE

- `src/mcp_workspace/github_operations/_pr_feedback_sources.py` (modify)
- `src/mcp_workspace/github_operations/pr_manager.py:651-660` (modify)
- `tests/github_operations/test_pr_manager_feedback.py` (modify — harness + tests)
- `tests/checks/test_branch_status_pr_feedback.py` — **verify green, do not edit**

## WHAT

```python
_PERMANENT_GRAPHQL_ERROR_TYPES = frozenset({"FORBIDDEN", "INSUFFICIENT_SCOPES", "RATE_LIMITED"})

def _build_graphql_exception(
    requester: Any, headers: dict[str, Any], result: dict[str, Any]
) -> Optional[GithubException]:
    """Return the exception PyGithub's graphql_query would have raised, or None."""

def fetch_review_data(
    manager: "PullRequestManager", pr_number: int
) -> Tuple[list[dict[str, Any]], int, list[dict[str, Any]], Optional[GithubException]]:
```

`_REVIEW_DATA_MAX_ATTEMPTS = 3` and `_REVIEW_DATA_RETRY_BASE_DELAY_SECONDS = 1.0` are
**unchanged**.

## HOW

- Imports: add `from github.GithubException import GithubException, UnknownObjectException`
  and `from ._diagnostics import extract_graphql_errors`.
- Replace the `graphql_query` call with
  `requester.requestJsonAndCheck("POST", requester.graphql_url, input={"query": query, "variables": variables})`.
  The GraphQL query string itself is unchanged.
- **Collateral doc edits — both currently assert the false 400/404 premise:**
  - module comment at `_pr_feedback_sources.py:21-25`
  - `Raises:` docstring at `:38-41`

  Rewrite both to describe the usability-keyed retry, and note that genuine HTTP failures
  still raise out of `requestJsonAndCheck` and are not retried here.

- **Ruff `DOC502` on the rewritten `Raises:` section.** `pyproject.toml` selects `["D", "DOC"]`
  and `_pr_feedback_sources.py` is **not** in `[tool.ruff.lint.per-file-ignores]`. After this
  step the function body contains **no `raise` statement** — `requestJsonAndCheck` propagates
  and nothing is re-raised — so a documented `Raises:` trips `DOC502`. Keep the section (the
  propagation is worth documenting) and suppress it exactly as this file already does at
  `:133`:

  ```python
      Raises:
          GithubException: Propagated from `requestJsonAndCheck` on a genuine HTTP
              failure. GraphQL-level errors are returned as the 4th tuple element,
              not raised, and are not retried by this loop.
      """  # noqa: DOC502  # GithubException propagates from requestJsonAndCheck
  ```

  Dropping the `Raises:` section entirely is the acceptable alternative; do **not** leave it
  unsuppressed.
- `pr_manager.get_pr_feedback` docstring says *"the raised exception"* — widen to *"raised or
  returned"*.
- Keep `get_pr_feedback`'s existing broad `except` — genuine HTTP failures still raise.
- **Scope:** `fetch_review_data` only. Leave `issues/branch_manager.py:220,530,676` and
  `pr_manager.py:615` on `graphql_query`.

## ALGORITHM

### `_build_graphql_exception` — mirror PyGithub exactly

```
errors = result.get("errors")
if not errors:                                            return None
if isinstance(errors, list) and len(errors) == 1 and isinstance(errors[0], dict) \
        and errors[0].get("type") == "NOT_FOUND":
    return UnknownObjectException(404, result, headers, errors[0].get("message"))
return requester.createException(400, headers, result)
```

**Key on the raw `errors` list, never on `extract_graphql_errors` output.** The parser drops
entries lacking a usable `message`, so `[{"type": "NOT_FOUND", "message": "x"}, {"type": "OTHER"}]`
would parse to one pair and yield a 404 where PyGithub yields a 400. The exception *class* is
observable to callers.

The `NOT_FOUND` case is constructed **directly**; only the other branch goes through
`createException`. `graphql_query` does the same — and `createException(404, headers, graphql_body)`
derives its message from the top-level `message` key, which a GraphQL body lacks, so its
"not found" branch would never fire and it would return a plain `GithubException`, not an
`UnknownObjectException`.

### `fetch_review_data`

```
repo = manager._get_repository(); if None: return ([], 0, [], None)
requester = manager._github_client._Github__requester
headers, result, pr_data = {}, {}, None            # pre-init: mypy possibly-unbound
for attempt in range(_REVIEW_DATA_MAX_ATTEMPTS):
    headers, result = requester.requestJsonAndCheck("POST", requester.graphql_url, input=...)
    pr_data = ((result.get("data") or {}).get("repository") or {}).get("pullRequest")
    if pr_data is not None: break                                   # usable data
    if any(t in _PERMANENT_GRAPHQL_ERROR_TYPES for t, _ in extract_graphql_errors(result)): break
    if attempt == _REVIEW_DATA_MAX_ATTEMPTS - 1: break
    time.sleep(_REVIEW_DATA_RETRY_BASE_DELAY_SECONDS * 2**attempt)
error = _build_graphql_exception(requester, headers, result)
if error is None and pr_data is None:
    error = GithubException(200, {"errors": [{"message": "pullRequest not returned"}]}, headers)
if pr_data is None: return ([], 0, [], error)

# thread / review parsing — logic unchanged, but every nested lookup is coerced
thread_nodes  = (pr_data.get("reviewThreads") or {}).get("nodes") or []
    ...
    comment_nodes = (thread.get("comments") or {}).get("nodes") or []
review_nodes  = (pr_data.get("reviews") or {}).get("nodes") or []

return (unresolved_threads, resolved_count, changes_requested, error)
```

Five things that are easy to get wrong:

- **`(x.get(k) or {})`, not `.get(k, {})` — at *every* level, not just `data`.** GraphQL
  error bodies carry `"data": null`, and a **partial** response nulls exactly the field that
  errored: `{"data": {"repository": {"pullRequest": {"reviewThreads": null, "reviews": {...}}}},
  "errors": [...]}`. The default-arg form returns `None` for a present-but-null key and the
  next `.get` raises `AttributeError`. The three existing lookups at
  `_pr_feedback_sources.py:90, 95, 111` (`reviewThreads`, `comments`, `reviews`) all use the
  default-arg form and **must** be converted to `or {}` — otherwise the one shape this step
  exists to recover crashes, `get_pr_feedback`'s broad `except` swallows it, and `threads`
  renders as `AttributeError — 'NoneType' object has no attribute 'get'` instead of the
  GraphQL reason. Same for the `.get("nodes", [])` calls on those objects.
- **Do not zero the threads when `error` is not `None`.** Recovered partial data still
  renders; the flag is additive information. Letting it clear the flag is a fail-open
  regression.
- **Status 200 on the synthesized exception is the truth.** Fabricating a 400 would repeat
  the mistake this issue fixes. The renderer drops the status anyway, so it surfaces only in
  the log — and its synthesized body means the renderer needs no special case.
- **`requestJsonAndCheck` sits outside any `try`.** Genuine HTTP failures propagate to
  `get_pr_feedback`'s `except` unretried; `GithubRetry(total=2)` already covers 403/5xx.

### `pr_manager.get_pr_feedback`

```
threads, resolved_count, changes_requested, review_error = fetch_review_data(self, pr_number)
if review_error is not None:
    logger.warning(f"Failed to fetch review data for PR #{pr_number}: {review_error}")
    unavailable["threads"] = review_error
except Exception as e:                          # unchanged — genuine HTTP failures
```

The `except` no longer covers the returned-exception path, which is why the log must be
explicit. `GithubException.__str__` json-dumps the whole body, so the synthetic status and
the full `errors` array stay reachable there.

## DATA

`fetch_review_data` returns a 4-tuple; element 4 is `GithubException | None`:

| Response | Element 4 |
|----------|-----------|
| Clean data, no `errors` | `None` |
| Data + `errors` (partial) | 400 `GithubException`, **threads still populated** |
| Single `NOT_FOUND` | `UnknownObjectException(404, ...)`, `exc.message` set |
| Multiple errors / non-list `errors` | plain `GithubException(400, ...)`, `exc.message is None` |
| `pullRequest` null, no `errors` | `GithubException(200, {"errors": [{"message": "pullRequest not returned"}]}, headers)` |

Retry matrix:

| `pullRequest` | Error type | Retried? |
|---------------|-----------|----------|
| present | any / none | no — data is usable |
| null | none, or non-permanent (incl. `NOT_FOUND`, or no `type`) | yes, up to 3 attempts |
| null | `FORBIDDEN` / `INSUFFICIENT_SCOPES` / `RATE_LIMITED` | no |

`NOT_FOUND` stays retryable: #228's error type was never recorded, so an allow-list would be
a guess, and `NOT_FOUND` is exactly the eventual-consistency shape. A missing `type` is not
evidence of permanence — validation errors carry none.

## Test harness rewrite (`_setup_mocks`)

Both fetches now call `requestJsonAndCheck`, so the single mock must dispatch.
**All 11 tests routing through the helper are affected.**

Dispatch on **`verb`** — GraphQL is the only `POST`, alerts the only `GET`. Simpler than URL
matching and needs no string parsing.

```python
from github.Requester import Requester   # new import

# in _setup_mocks, replacing the graphql_query and requestJsonAndCheck setup:
mock_requester.graphql_url = "https://api.github.com/graphql"
mock_requester.createException = Requester.createException

post_bodies = iter(graphql_responses) if graphql_responses is not None else None

def _request(verb: str, url: str, **kwargs: Any) -> tuple[dict[str, Any], Any]:
    if verb == "POST":
        if graphql_raises is not None:
            raise graphql_raises
        if post_bodies is not None:
            return ({}, next(post_bodies))
        return ({}, graphql_response or {"data": {}})
    if alerts_raises is not None:
        raise alerts_raises
    return ({}, alerts_response or [])

mock_requester.requestJsonAndCheck = Mock(side_effect=_request)
```

Four harness points:

- **`graphql_url` must be a concrete string.** `mock_requester` is a bare `Mock()`
  (`:59`), so the attribute would auto-create a `Mock` and call-arg assertions become
  unreadable.
- **`createException` must be the real classmethod.** On a plain `Mock` it returns a `Mock`,
  and every `isinstance(..., GithubException)` assertion passes vacuously.
- **New `graphql_responses` parameter** (a list, one body per successive POST) for the retry
  tests. `graphql_response` keeps its meaning for the eight tests already using it —
  minimal churn. `graphql_raises` narrows to a single exception meaning *HTTP-level failure*.
- **`alerts_raises` must no longer be a bare `side_effect`.** Post-change the review-data POST
  hits it first and would wrongly flag `threads` unavailable too — this is why
  `test_code_scanning_403_silent_skip` (`:240`) and `test_code_scanning_500_unavailable`
  (`:266`) are in scope.

Call-count assertions at `:308, 364, 387, 409` no longer apply to `graphql_query`. Add a helper:

```python
def _post_call_count(manager: PullRequestManager) -> int:
    requester = manager._github_client._Github__requester
    return sum(1 for c in requester.requestJsonAndCheck.call_args_list if c.args[0] == "POST")
```

## TDD — write these first

**Rewrite** the three tests that build GraphQL failures from REST payloads
(`:351`, `:376`, `:398` — `GithubException(400, {"message": "not found yet"}, None)`). *That
shape is why this bug survived the suite*: they describe a GraphQL error with a REST body
GitHub cannot send. Use real
`{"data": {"repository": {"pullRequest": null}}, "errors": [{"message": ..., "type": ...}]}`.

Retry:
1. `test_review_data_retry_then_success` — `graphql_responses=[null-PR + non-permanent error, valid_response]`
   → 2 POSTs, threads populated, `"threads"` **not** in unavailable, 1 sleep
2. `test_review_data_retry_exhausted_unavailable` — persistent null PR + non-permanent error
   → 3 POSTs, 2 sleeps, flagged
3. `test_permanent_error_not_retried` — null PR + `FORBIDDEN` → **1 POST, 0 sleeps**, flagged
4. `test_usable_data_with_errors_not_retried` — data + errors → 1 POST, 0 sleeps

Partial data (the core fail-closed guarantee):
5. `test_partial_data_flagged_and_rendered` — use the **realistic** partial shape: the errored
   field is explicitly `null` while a sibling survives, plus an `errors` array naming it:

   ```python
   {
     "data": {"repository": {"pullRequest": {
         "reviewThreads": None,
         "reviews": {"nodes": [{"state": "CHANGES_REQUESTED",
                                "author": {"login": "alice"}, "body": "fix"}]},
     }}},
     "errors": [{"type": "FORBIDDEN", "message": "Resource not accessible",
                 "path": ["repository", "pullRequest", "reviewThreads"]}],
   }
   ```

   Assert **all three**: the surviving sibling is recovered
   (`len(result["changes_requested"]) == 1`), `"threads"` **is** in unavailable, and the
   flagged exception renders the GraphQL reason —
   `render_exception_for_display(result["unavailable"]["threads"])
   == "GraphQL FORBIDDEN — Resource not accessible"`. That last assertion is what proves no
   `AttributeError` was raised and swallowed: a nulled `reviewThreads` parsed with
   `.get("reviewThreads", {})` surfaces as `AttributeError — 'NoneType' object has no
   attribute 'get'` instead. Do **not** use a fully-populated `reviewThreads` block here —
   that shape cannot fail and defeats the test.

   Companion case (parametrize or a second test): `reviews` nulled and `reviewThreads`
   populated → unresolved threads recovered, `"threads"` still flagged.

Exception shape:
6. `test_single_not_found_yields_unknown_object_exception` — one `NOT_FOUND` error →
   `isinstance(exc, UnknownObjectException)`, `status == 404`, `exc.message` set. Retried 3×.
7. `test_multiple_errors_yield_plain_github_exception` — two errors →
   `type(exc) is GithubException`, `status == 400`, `exc.message is None`

Null `pullRequest`:
8. `test_null_pull_request_no_errors_flagged` — `{"data": {"repository": {"pullRequest": None}}}`
   → 3 POSTs, 2 sleeps, flagged; `status == 200`; and
   `render_exception_for_display(exc) == "GraphQL error — pullRequest not returned"`
9. `test_null_pull_request_with_error_flagged` — flagged and retried per the retry rule

Logging:
10. `test_returned_graphql_error_logged_at_warning` — `caplog` at WARNING contains
    `"Failed to fetch review data for PR #42"`. **The `except` block no longer covers this
    path, so it needs its own assertion.**

HTTP failure (semantics unchanged):
11. `test_graphql_http_failure` (was `test_graphql_failure`, `:293`) —
    `graphql_raises=GithubException(500, {"message": "boom"}, None)` → 1 POST, no sleep,
    `"threads"` in unavailable

Regression: `test_happy_path`, `test_clean_state`, both code-scanning tests, both
conversation-comment tests, and `test_invalid_pr_number` stay green through the new harness.

## Verification

- All four MCP checks green — `run_pylint_check`, `run_pytest_check`, `run_mypy_check`, and
  `run_ruff_check` — with pytest run **twice** (fast-unit exclusion, then
  `markers=["git_integration"]`). Ruff is not optional here: this step rewrites
  `fetch_review_data`'s `Raises:` section and the `get_pr_feedback` docstring, and
  `_pr_feedback_sources.py` is not exempt from `DOC502`.
- **`tests/checks/test_branch_status_pr_feedback.py:228-268`** asserts on rendered
  `[unavailable]` lines using REST-shaped payloads, so it should stay green.
  **Confirm by running it — do not assume, and do not edit it.**
- `mcp-coder check file-size --max-lines 750` — `_pr_feedback_sources.py` grows here.

## Commit message

```
Preserve partial GraphQL data and re-key the review-data retry on usability

graphql_query raises whenever an errors array is present, discarding data that
arrived with it. Call requestJsonAndCheck directly so data and errors arrive
together, and return the exception PyGithub would have raised as a 4th tuple
element instead of raising it.

Retry now triggers on "nothing usable came back and no permanent error type"
rather than on a 400/404 that PyGithub synthesised for an HTTP 200 response, so
permanent failures no longer cost 3 attempts and ~3s.

Any GraphQL error keeps threads flagged even when data was recovered: letting
partial data clear the flag would let check_branch_status report clean while an
errored field hid a blocking thread. Since the exception is now returned rather
than raised, get_pr_feedback logs it explicitly.
```

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_4.md`. Steps 1-3 are merged, so
> `extract_graphql_errors` exists, the renderer has its GraphQL arm, and the alerts unpack is
> already a 2-tuple.
>
> Implement step 4: make `fetch_review_data` tolerant, re-key the retry, and log the returned
> exception in `get_pr_feedback`.
>
> Follow TDD — rewrite the three REST-shaped GraphQL tests and add the new cases in
> `tests/github_operations/test_pr_manager_feedback.py` first, then implement. The harness
> rewrite lands with the tests.
>
> Six things that are easy to get wrong; the step file explains each:
> - `_build_graphql_exception` keys on the **raw `errors` list**, never on
>   `extract_graphql_errors` output — the parser drops message-less entries and would flip a
>   400 into a 404.
> - Use `(x.get(k) or {})`, not `.get(k, {})` — **at every level**, not just `data`. GraphQL
>   error bodies carry `"data": null`, and a partial response nulls the field that errored, so
>   the existing `reviewThreads` / `comments` / `reviews` lookups must be converted too. Test 5
>   exists to catch this.
> - Do **not** zero recovered threads when an error is present. Any error keeps `threads`
>   flagged **and** the recovered items render. This fail-closed rule is the point.
> - The synthesized null-`pullRequest` exception carries status **200**, not 400.
> - In `_setup_mocks`, set `graphql_url` to a real string and wire `createException` to the
>   real `Requester.createException` classmethod — otherwise `isinstance(..., GithubException)`
>   assertions pass vacuously against a `Mock`.
> - `requestJsonAndCheck` stays outside any `try`; genuine HTTP failures must keep propagating
>   unretried.
>
> Keep `fetch_review_data` the **only** tolerant call site — leave
> `issues/branch_manager.py:220,530,676` and `pr_manager.py:615` on `graphql_query`. Update the
> module comment at `_pr_feedback_sources.py:21-25` and the `Raises:` docstring at `:38-41`;
> both currently assert the false 400/404 premise.
>
> Run `tests/checks/test_branch_status_pr_feedback.py` to confirm it stays green, and do not
> edit it. Run pytest twice — with the fast-unit exclusion pattern and with
> `markers=["git_integration"]`, since `TestGetPRFeedback` is marked `git_integration`.
>
> Use MCP tools exclusively. Run `run_pylint_check`, `run_pytest_check`, `run_mypy_check`,
> and `run_ruff_check` and fix everything before reporting done. Ruff's `DOC502` will fire on
> the rewritten `Raises:` section unless you add the `# noqa: DOC502` the step file specifies.
