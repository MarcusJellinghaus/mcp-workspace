# Step 2 — Renderer GraphQL branch

**Depends on:** step 1 (`extract_graphql_errors`). **Commit:** tests + implementation +
checks green.

## Goal

Stop rendering a bare `GithubException 400`. Add a GraphQL arm that surfaces the actual
reason and **drops the synthetic status** from display.

## WHERE

- `src/mcp_workspace/github_operations/exception_renderer.py` (modify)
- `tests/github_operations/test_exception_renderer.py` (modify — add a class)

## WHAT

```python
_MAX_RENDERED_CHARS = 200
_MAX_GRAPHQL_ERRORS_SHOWN = 2

def _cap(text: str) -> str:
    """Return `text` capped at _MAX_RENDERED_CHARS, with '...' appended if cut."""

def _render_graphql_errors(pairs: list[tuple[str | None, str]]) -> str:
    """Return (type, message) pairs rendered as a single line, status omitted."""

def render_exception_for_display(exc: Exception) -> str:   # signature unchanged
```

## HOW

- Import: `from ._diagnostics import extract_graphql_errors`.
- Python is `>=3.11`, so `str | None` in annotations needs no `__future__` import.
- `_cap` replaces the duplicated truncation idiom and is used by **both** arms.
- **Both helper docstrings must start with "Return".** Ruff's `DOC201` (`select = ["D", "DOC"]`,
  `preview = true`) requires a `Returns:` section on any value-returning function whose summary
  line does not — compare `checks/pr_feedback.py:36` and `ci_results_manager.py:162` (explicit
  `Returns:`) against `utils/repo_identifier.py:148` (one-liner, exempt because it starts with
  "Return"). Adding a full `Returns:` section to each helper is the equally acceptable
  alternative; a one-line `"""Truncate ..."""` / `"""Render ..."""` is **not**.
- Update the `render_exception_for_display` docstring: *"Truncated at 200 chars"* stops
  being true for the GraphQL arm, where the cap applies **per message** so the `(+N more)`
  suffix always survives.
- `render_exception_for_display` has one caller (`checks/pr_feedback.py:125`). Do not change
  its signature and do not touch that file.

## ALGORITHM

Dispatch — hoist the dict check into a local so it cannot be forgotten. Shown in its
enclosing context: the new code lives **inside** the existing
`if isinstance(exc, GithubException):` branch, because `exc.data` only exists there — the
`else` branch (`TestGenericException`) must keep using `str(exc)` untouched:

```python
type_name = type(exc).__name__
if isinstance(exc, GithubException):
    data = exc.data if isinstance(exc.data, dict) else None
    if data and "errors" in data and "message" not in data:
        pairs = extract_graphql_errors(data)
        if pairs:
            return _render_graphql_errors(pairs)   # early return: no final _cap
    raw = data.get("message") if data else None    # existing REST path, unchanged
    msg = re.sub(r"\s+", " ", raw).strip() if raw else ""
    rendered = f"{type_name} {exc.status}" + (f" — {msg}" if msg else "")
else:
    ...                                            # unchanged generic-exception path
return _cap(rendered)
```

**The dispatch rule, stated explicitly:** take the GraphQL arm when `exc.data` is a dict that
has an `errors` key **and no top-level `message` key**, and the parser yields at least one
pair. Anything else takes the REST arm.

Two independent reasons for that rule:

- **The `isinstance` guard must precede the `in` test** — on a string body, `in` is a
  substring test. The existing `test_non_dict_data_omits_message_segment` uses `"raw text"`,
  which contains no `errors`, so it will not catch a missing guard. Test 9 below does.
- **`errors` alone does not mean GraphQL.** GitHub REST validation failures (422) send
  `{"message": "Validation Failed", "errors": [{"resource": ..., "code": "custom",
  "message": "No commits between main and topic"}]}`. Those entries *do* carry a `message`,
  so `extract_graphql_errors` parses them and the body would render as
  `GraphQL error — No commits between main and topic` — mislabelled, with the real HTTP 422
  discarded. A GraphQL body has **no** top-level `message` (that is the whole premise of this
  issue), so `"message" not in data` separates the two shapes exactly. Test 14 below covers it.

`_render_graphql_errors`:

```
for (err_type, message) in pairs[:_MAX_GRAPHQL_ERRORS_SHOWN]:
    msg = _cap(collapse_whitespace(message))                # re.sub(r"\s+", " ").strip()
    part = f"GraphQL {err_type} — {msg}" if err_type else f"GraphQL error — {msg}"
rendered = "; ".join(parts)
extra = len(pairs) - _MAX_GRAPHQL_ERRORS_SHOWN
return rendered + (f" (+{extra} more)" if extra > 0 else "")
```

Newlines are collapsed to spaces because `format_pr_feedback` joins sections with `\n`
(`checks/pr_feedback.py:125,133`) — an embedded newline would corrupt the block. The
rendered value stays a **single line**.

## DATA

- **Returns:** `str` — the portion after `'<section>: '`. Unchanged contract.
- Em-dash separator is U+2014 `—`, matching the existing REST output.
- Zero usable pairs → fall through to today's REST rendering. Never raise.

Output shapes:

| Input | Output |
|-------|--------|
| one error, `type` present | `GraphQL FORBIDDEN — Resource not accessible` |
| one error, no `type` | `GraphQL error — Field 'x' doesn't exist on type 'Y'` |
| two errors | `GraphQL A — a; GraphQL error — b` |
| four errors | `GraphQL A — a; GraphQL B — b (+2 more)` |

## TDD — write these first (`TestGraphqlErrors`)

Build inputs as realistic bodies: `GithubException(400, {"data": None, "errors": [...]}, None)`.

Formatting (parametrize 1-6 — they are input/output one-liners):
1. `type` present → `GraphQL FORBIDDEN — Resource not accessible`
2. No `type` → `GraphQL error — Field 'x' doesn't exist on type 'Y'`
3. Two errors → single line joined with `; `, **no** `(+N more)`; assert `"\n" not in result`
4. Three errors → first two, then ` (+1 more)`
5. Five errors → ` (+3 more)`
6. Message containing `\n` → collapsed to a space; assert `"\n" not in result`

Structural:
7. **Long first message does not truncate away the suffix** — first message 300 chars, three
   errors total: assert `result.endswith("(+1 more)")`. This is the whole point of moving the
   cap per-message.
8. `UnknownObjectException(404, {"data": None, "errors": [{"type": "NOT_FOUND", "message": "Could not resolve to a PullRequest"}]}, None, "Could not resolve to a PullRequest")`
   → `GraphQL NOT_FOUND — Could not resolve to a PullRequest`. The GraphQL arm handles this
   unaided: no separate 404 handling, no `exc.message` fallback.
9. **Guard proof** — `GithubException(500, "raw errors text", None)` (a non-dict body that
   *contains* the substring `errors`) → `GithubException 500`.
10. Status never leaks — for any GraphQL case assert `"400" not in result` and
    `"GithubException" not in result`.

Fall-through (unparseable `errors` → REST rendering, no crash):
11. `errors` not a list: `{"message": "boom", "errors": "nope"}` → `GithubException 400 — boom`
12. Entries not dicts: `{"errors": ["a", "b"]}` → `GithubException 400`
13. `errors` present but empty: `{"errors": []}` → REST path
14. **REST 422 with a message-bearing `errors` array is not misclassified** —
    `GithubException(422, {"message": "Validation Failed", "errors": [{"resource": "PullRequest",
    "code": "custom", "message": "No commits between main and topic"}]}, None)` →
    `GithubException 422 — Validation Failed`. Assert `"GraphQL" not in result` and that the
    status `422` is present. This is the test for the `"message" not in data` half of the
    dispatch rule; without it the body renders as `GraphQL error — No commits between main
    and topic` with the status dropped.

Regression: **every existing test in the file must stay green unchanged**, including
`test_truncation_at_200_chars` (203 chars) — the REST arm keeps the whole-line cap.

## Verification

All four MCP checks green — `run_pylint_check`, `run_pytest_check`, `run_mypy_check`, and
`run_ruff_check`. Ruff matters here: this step rewrites `render_exception_for_display`'s
docstring and adds two private helpers, all of which the repo-wide `["D", "DOC"]` selection
covers.

Fast-unit exclusion pattern is sufficient; this file carries no integration marker. Confirm
the pre-existing `TestGithubException` and `TestGenericException` classes pass without edits.

## Commit message

```
Render GraphQL errors with their reason instead of a bare status

exception_renderer read exc.data["message"], the REST shape, so every
GraphQL failure rendered as "GithubException 400" with the reason discarded.
Add a GraphQL arm that reads the errors array and omits the status entirely:
PyGithub synthesises 400/404 for GraphQL, and GitHub answered 200, so the
number asserts something that never happened. The 200-char cap applies per
message on this arm so the "(+N more)" suffix always survives.
```

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`. Step 1 is already merged, so
> `extract_graphql_errors` exists in `_diagnostics.py`.
>
> Implement step 2 only: add the GraphQL branch, `_cap`, and `_render_graphql_errors` to
> `src/mcp_workspace/github_operations/exception_renderer.py`, and update its docstring.
>
> Follow TDD — write the `TestGraphqlErrors` cases in
> `tests/github_operations/test_exception_renderer.py` first, watch them fail, then implement.
>
> Three things that are easy to get wrong:
> - Hoist `isinstance(exc.data, dict)` into a local **before** testing `"errors" in ...`, or a
>   string body turns it into a substring test. Test 9 exists to catch this.
> - The GraphQL arm requires `"message" not in data` as well as `"errors" in data`. REST 422
>   bodies carry **both** keys and their `errors` entries have `message` fields, so keying on
>   `errors` alone mislabels them `GraphQL error — ...` and throws away the HTTP status. Test
>   14 exists to catch this.
> - The GraphQL arm returns **early**, bypassing the final whole-line `_cap`, so `(+N more)`
>   is never truncated away. Test 7 exists to catch this.
>
> Do not change the signature of `render_exception_for_display` and do not touch
> `checks/pr_feedback.py`. Do not touch `_pr_feedback_sources.py` or `pr_manager.py` — step 4.
> All pre-existing tests in the renderer test file must stay green **without edits**.
>
> Use MCP tools exclusively. Run `run_pylint_check`, `run_pytest_check`, `run_mypy_check`,
> and `run_ruff_check` and fix everything before reporting done. Ruff enforces `D`/`DOC`
> docstring rules repo-wide.
