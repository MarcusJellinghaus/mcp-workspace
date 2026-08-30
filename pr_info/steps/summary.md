# Summary — Issue #250: GraphQL errors render as a bare "GithubException 400"

## Problem

`check_branch_status` reports:

```
PR Reviews:
[unavailable] threads: GithubException 400
```

with no reason, while the PR genuinely has review content. Three defects share one
root cause: **the code treats GraphQL error bodies as REST error bodies.**

| # | Defect | Location |
|---|--------|----------|
| 1 | Renderer reads `exc.data["message"]` — a REST key. GraphQL bodies carry `exc.data["errors"][*]["message"]`, so the reason is dropped and a bare `GithubException 400` is shown. | `exception_renderer.py:17` |
| 2 | The retry keys on status 400/404, but PyGithub *synthesises* those for GraphQL. GitHub answered HTTP **200**. A permanent error costs 3 attempts and ~3s, then reports nothing. | `_pr_feedback_sources.py:72-82` |
| 3 | `graphql_query` raises whenever `errors` is present, **even when `data` is populated**, so partial results are discarded. | PyGithub `Requester.graphql_query` |

A fourth, same-class defect is fixed here because step 4 calls the same method:
`fetch_code_scanning_alerts` unpacks `requestJsonAndCheck` three ways, but it returns a
**2-tuple**. It has raised `ValueError` against real GitHub since #175, hidden by a mock
that feeds a 3-tuple the API cannot produce.

## Verified against installed PyGithub (not assumed)

```python
# Requester.graphql_query
response_headers, data = self.requestJsonAndCheck("POST", self.graphql_url, input=input_)
if "errors" in data:
    if len(data["errors"]) == 1:
        error = data["errors"][0]
        if error.get("type") == "NOT_FOUND":
            raise github.UnknownObjectException(404, data, response_headers, error.get("message"))
    raise self.createException(400, response_headers, data)
return response_headers, data
```

- `requestJsonAndCheck` is annotated `-> tuple[dict[str, Any], Any]` — a 2-tuple.
- Reaching `createException(400, ...)` **proves HTTP was 200**; `requestJsonAndCheck`
  raises before the `errors` check on any genuine HTTP failure.
- `createException` derives its message from `output.get("message")`, absent in a GraphQL
  body, and every special branch is keyed to 401/403/404 — so for status 400 it provably
  returns a plain `GithubException(400, data, headers, None)`.

## Architectural / design changes

### 1. New shared parser, package-private

`extract_graphql_errors(body)` joins `extract_diagnostic_headers` in `_diagnostics.py`,
the established home for pulling diagnostics out of failure payloads. The module docstring
widens: it previously described extraction *from a `GithubException`*, and this parser
takes a raw response body.

**It has two consumers, not the three the issue anticipated.** The renderer and the retry
classifier use it. Exception *construction* must not: the parser drops entries lacking a
usable `message`, so `{"errors": [{"type": "NOT_FOUND", "message": "x"}, {"type": "OTHER"}]}`
would parse to one pair and yield a 404 where PyGithub yields a 400. Construction keys on
the raw `errors` list, which is what the issue's own class-preservation decision requires.

### 2. Renderer gains a third dispatch arm

`render_exception_for_display` becomes a 3-way dispatch: GraphQL body → REST body →
non-`GithubException`. The GraphQL arm **drops the synthetic status from display** —
rendering `GithubException 400` asserts an HTTP status that never existed and sends readers
to debug a phantom. The number stays reachable in the WARNING log.

The 200-char cap moves **per message** on this arm so the `(+N more)` suffix always
survives. A single `_cap()` helper serves both arms.

The `isinstance(exc.data, dict)` guard is hoisted into a local so the dict check cannot be
forgotten — on a string body, `"errors" in exc.data` is a substring test.

**Dispatch is narrowed beyond the issue's wording.** The issue says "GraphQL branch when
`exc.data` is a dict containing `errors`". That alone is wrong: GitHub REST 422 bodies are
`{"message": "Validation Failed", "errors": [{..., "message": "..."}]}` — an `errors` array
whose entries carry parseable messages — and would render as `GraphQL error — <msg>` with the
real HTTP status thrown away. The rule is therefore `errors` present **and no top-level
`message`**, which is exactly what distinguishes the two shapes. The synthesized
null-`pullRequest` body has no top-level `message` either, so it still takes the GraphQL arm.

### 3. `fetch_review_data` becomes tolerant; the return contract widens

It calls `requestJsonAndCheck` directly instead of `graphql_query`, so `data` and `errors`
arrive **together** and partial results survive. It returns a 4-tuple; the 4th element is
the `GithubException` PyGithub *would* have raised, or `None`.

Surviving partial data also requires the **parsing** to tolerate it. A partial GraphQL
response sets the errored field to `null`, and the existing lookups
(`_pr_feedback_sources.py:84, 90, 95, 111`) use `.get(key, {})`, which returns `None` for a
present-but-null key and raises `AttributeError` on the next `.get`. All of them move to
`.get(key) or {}` — otherwise the recovery path crashes on exactly the shape it exists for
and the `[unavailable]` line degrades to an internal `AttributeError` instead of the GraphQL
reason.

**This is scoped to `fetch_review_data` only.** The other four `graphql_query` call sites
(`issues/branch_manager.py:220,530,676`, `pr_manager.py:615`) keep raise-on-error semantics.

### 4. Retry re-keys from status to usability

Old trigger: "status is 400 or 404". New trigger: **"nothing usable came back
(`pullRequest` is null) **and** no error type is permanent"** (`FORBIDDEN`,
`INSUFFICIENT_SCOPES`, `RATE_LIMITED`). Attempts and backoff are unchanged (3, 1s/2s).

An allow-list ("retry only `NOT_FOUND`") would be a guess — #228's error type was never
recorded, and it cannot have been a lone `NOT_FOUND` or PyGithub would have raised 404, not
the 400 that was reproduced. Keying on "did we get usable data?" avoids the guess.

Genuine HTTP failures still raise out of `requestJsonAndCheck` and are **not** retried by
this loop; `build_github_client`'s `GithubRetry(total=2)` already covers 403/5xx.

### 5. Fail-closed is preserved deliberately

**Any GraphQL error keeps `threads` flagged even when threads were recovered.** Recovered
items still render — the change is strictly *additive information*. Letting partial data
clear the flag would let `check_branch_status` report "Reviews: clean" while an errored
field hid a blocking thread: a fail-open regression, and the exact failure today's design
avoids. `collect_pr_feedback` (`checks/pr_feedback.py:157-159`) turns the flag into
`undeterminable`, so the verdict is UNKNOWN, not clean.

A null `pullRequest` is now flagged rather than silently returned as `([], 0, [])` — the
same fail-closed rule, including for legitimately absent or invisible PRs.

### 6. The WARNING log becomes explicit, not incidental

After step 4 the exception is *returned*, not raised, so `pr_manager.py:655-660`'s `except`
never fires for it. `get_pr_feedback` must log it explicitly. Without this, dropping the
status from the display would make it unreachable entirely.

### Rendered output shape is unchanged

Only the *content* of the `[unavailable]` line changes. `format_pr_feedback` and
`collect_pr_feedback` need no edits. `render_exception_for_display` has one caller
(`checks/pr_feedback.py:125`), so the change is contained.

New line formats:

```
GraphQL FORBIDDEN — Resource not accessible
GraphQL error — Field 'x' doesn't exist on type 'Y'          # validation error, no type
GraphQL FORBIDDEN — a; GraphQL error — b (+2 more)           # first two, then the count
GraphQL error — pullRequest not returned                     # null PR, no error named
```

## Files created / modified

No new folders or modules. No new public API.

### Source — modified (4 files)

| File | Change | Step |
|------|--------|------|
| `src/mcp_workspace/github_operations/_diagnostics.py` | Add `extract_graphql_errors`; widen module docstring | 1 |
| `src/mcp_workspace/github_operations/exception_renderer.py` | Add GraphQL branch + `_cap` + `_render_graphql_errors`; hoist dict guard; update docstring | 2 |
| `src/mcp_workspace/github_operations/_pr_feedback_sources.py` | Fix alerts 2-tuple unpack (step 3); tolerant fetch, 4-tuple, `_build_graphql_exception`, retry re-key, module comment + `Raises:` docstring (step 4) | 3, 4 |
| `src/mcp_workspace/github_operations/pr_manager.py` | Unpack 4-tuple, log + flag the returned exception | 4 |

### Tests — modified (3 files)

| File | Change | Step |
|------|--------|------|
| `tests/github_operations/test_diagnostics.py` | New `TestExtractGraphqlErrors` class | 1 |
| `tests/github_operations/test_exception_renderer.py` | New `TestGraphqlErrors` class; existing REST cases stay green | 2 |
| `tests/github_operations/test_pr_manager_feedback.py` | Alerts 2-tuple mock + regression test (step 3); `_setup_mocks` verb dispatch, GraphQL bodies replace REST-shaped fakes, call-count assertions move (step 4) | 3, 4 |

### Verified unchanged (assert, do not edit)

- `tests/checks/test_branch_status_pr_feedback.py:228-268` — uses REST-shaped payloads, so
  it should stay green. **Confirm rather than assume** (step 4).
- `src/mcp_workspace/checks/pr_feedback.py` — output shape is unchanged.
- `issues/branch_manager.py:220,530,676` and `pr_manager.py:615` — out of scope.

### Plan documents — created

`pr_info/steps/summary.md`, `step_1.md`, `step_2.md`, `step_3.md`, `step_4.md`

## Steps

Each step is exactly one commit: tests + implementation + all four checks green
(pylint, pytest, mypy, ruff).

| Step | Scope | Depends on |
|------|-------|------------|
| [1](./step_1.md) | `extract_graphql_errors` parser | — |
| [2](./step_2.md) | Renderer GraphQL branch | 1 |
| [3](./step_3.md) | `fetch_code_scanning_alerts` 2-tuple fix | — |
| [4](./step_4.md) | Tolerant fetch, retry re-key, WARNING log | 1, 2, 3 |

Steps 1-3 are independently committable and leave the tree green. Step 4 is not further
splittable: once `fetch_review_data` calls `requestJsonAndCheck`, `graphql_query` no longer
raises, so the old retry trigger is dead the same instant — and the 4-tuple cannot land
without its `pr_manager` unpack.

## Mandatory checks (after every step)

```
mcp__tools-py__run_pylint_check
mcp__tools-py__run_pytest_check   extra_args=["-n","auto"]  (git_integration needed here)
mcp__tools-py__run_mypy_check
mcp__tools-py__run_ruff_check
mcp__tools-py__run_format_code    steps=["isort","black"]
```

**`run_format_code` is an exit criterion too.** CI runs `isort --check --profile=black
--float-to-top src tests` and `black --check` as separate jobs, so a formatting drift turns
the pipeline red even when the four checks above are green. Note that `pyproject.toml`
declares `isort>=9.0.1` unpinned and CI installs without a lockfile, so CI may resolve a
newer isort than the local environment; a green local `run_format_code` is necessary but not
always sufficient.

**`run_ruff_check` is an exit criterion for every step, not an optional extra.**
`pyproject.toml` sets `[tool.ruff.lint] select = ["D", "DOC"]` with `preview = true`, so the
pydocstyle **and** pydoclint rules are enforced across `src/`. Every step in this plan edits
docstrings — the `_diagnostics.py` module docstring (1), `render_exception_for_display` plus
two new private helpers (2), and `fetch_review_data`'s `Raises:` section plus the
`get_pr_feedback` docstring (4) — and `_pr_feedback_sources.py` is **not** in
`[tool.ruff.lint.per-file-ignores]`, so `DOC502` applies to it (see step 4's `# noqa`
requirement). Neither pylint nor mypy catches these.

`TestGetPRFeedback` is marked `git_integration`, so the usual fast-unit exclusion pattern
skips the tests that matter for steps 3 and 4. Run those with `markers=["git_integration"]`
in addition to the fast pass.
