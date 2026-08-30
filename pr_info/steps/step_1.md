# Step 1 — `extract_graphql_errors` parser

**Depends on:** nothing. **Commit:** tests + implementation + checks green.

## Goal

Add the shared, defensive parser that turns a GraphQL response body into `(type, message)`
pairs. No callers yet — steps 2 and 4 consume it.

## WHERE

- `src/mcp_workspace/github_operations/_diagnostics.py` (modify)
- `tests/github_operations/test_diagnostics.py` (modify — add a class)

The module is package-private and deliberately **not** re-exported via
`github_operations/__init__.py`. Keep it that way.

## WHAT

```python
def extract_graphql_errors(body: Any) -> list[tuple[str | None, str | None]]:
    """Return (type, message) pairs from a GraphQL response body's `errors` array."""
```

## HOW

- The file already has `from __future__ import annotations`. Add `Any` to the imports:
  `from typing import Any`.
- Widen the module docstring. It currently reads *"Private helpers for extracting
  diagnostic information from GithubException."* — this parser takes a **raw response
  body**, not an exception. Reword to cover both, and keep the existing sentences about
  allow-listed header dumps and the module being private to the package.
- No new constants. No changes to `extract_diagnostic_headers` or `DIAGNOSTIC_HEADERS`.

## ALGORITHM

```
if body is not a dict:                          return []
errors = body.get("errors")
if errors is not a list:                        return []
for entry in errors:
    skip if entry is not a dict
    err_type = entry.get("type") if it is a non-blank str else None
    message = entry.get("message") if it is a non-blank str else None
    skip if err_type is None and message is None
    append (err_type, message)
return pairs
```

Parse defensively at **every** level: `errors` may not be a list, and entries may not be
dicts. Do **not** collapse whitespace or truncate here — the parser stays dumb and the
renderer owns presentation (step 2). Return messages verbatim.

## DATA

- **Returns:** `list[tuple[str | None, str | None]]`, source order preserved. Empty list for
  any unusable input — never raises.
- `type` is `None` for GraphQL validation errors, which carry no `type` at all. **A missing
  `type` does not mean transient** — step 4 depends on this.
- `message` is `None` for entries that carry only a `type`. An entry is kept when **either**
  element is usable; only entries with neither are dropped. A type-only
  `{"type": "RATE_LIMITED"}` names a real failure, and dropping it would put the renderer
  back on the bare-`GithubException 400` path this issue exists to remove.

## TDD — write these first (`TestExtractGraphqlErrors`)

Import: `from mcp_workspace.github_operations._diagnostics import extract_graphql_errors`

Well-formed input:
1. Single error with `type` → `[("FORBIDDEN", "Resource not accessible")]`
2. Single error without `type` → `[(None, "Field 'x' doesn't exist on type 'Y'")]`
3. Three errors → three pairs, **source order preserved**
4. Realistic partial-data body `{"data": {...}, "errors": [...]}` → errors parsed, `data`
   ignored

Defensive input — each returns `[]` or skips, never raises:
5. `body` is not a dict (`"raw text"`, `None`, `[]`) → `[]`
6. `body` has no `errors` key (e.g. `{"message": "boom"}`) → `[]`
7. `errors` is not a list (`"nope"`, `{"message": "x"}`, `None`) → `[]`
8. `errors` is `[]` → `[]`
9. Entries are not dicts (`["a", None, 42]`) → `[]`
10. Neither `type` nor `message` usable (`{}`, `{"message": 42}`, `{"message": "   "}`,
    `{"type": 42}`) → skipped
11. `type` is non-str (`{"type": 42, "message": "x"}`) → `[(None, "x")]`
12. Usable `type`, no usable `message` (`{"type": "RATE_LIMITED"}`) → `[("RATE_LIMITED", None)]`
13. Mixed valid + invalid entries → only the usable pairs returned
14. Multi-line message is returned **verbatim**, newline intact (proves the parser does not
    format)

Use `pytest.mark.parametrize` for the `[]`-returning cases (5-9); they are one-line
input/output pairs.

## Verification

All four MCP checks green — `run_pylint_check`, `run_pytest_check`, `run_mypy_check`, and
`run_ruff_check`. Ruff matters here: `pyproject.toml` selects `["D", "DOC"]`, and this step
rewrites the `_diagnostics.py` module docstring and adds a new public function docstring.

`run_pytest_check` with the fast-unit exclusion pattern is sufficient for this step —
`test_diagnostics.py` carries no integration marker.

## Commit message

```
Add extract_graphql_errors parser for GraphQL error bodies

GraphQL errors live at body["errors"][*]["message"], not the REST key
body["message"]. Add a defensive shared parser in _diagnostics.py for the
renderer and retry classifier to consume. Parses at every level: errors may
not be a list, entries may not be dicts.
```

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`.
>
> Implement step 1 only: add `extract_graphql_errors` to
> `src/mcp_workspace/github_operations/_diagnostics.py` and widen that module's docstring.
>
> Follow TDD — write the `TestExtractGraphqlErrors` cases in
> `tests/github_operations/test_diagnostics.py` first, watch them fail, then implement.
>
> Do **not** touch `exception_renderer.py`, `_pr_feedback_sources.py`, or `pr_manager.py`;
> those are steps 2-4. Do not re-export the new function from
> `github_operations/__init__.py`. Do not collapse whitespace or truncate messages in the
> parser — the renderer owns presentation.
>
> Use MCP tools exclusively (`mcp__workspace__*` for files, `mcp__tools-py__*` for checks).
> Run `run_pylint_check`, `run_pytest_check`, `run_mypy_check`, and `run_ruff_check` and fix
> everything before reporting done. Ruff enforces `D`/`DOC` docstring rules repo-wide.
