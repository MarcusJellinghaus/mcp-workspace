# Issue #236 — Branch status: missing-token degradation + opt-in fail-on-reviews

## Goal

Bring `mcp_workspace.checks.branch_status` up to the mcp-coder fork's capability
**plus two new opt-in features**, so mcp-coder #1068 can replace its forked
`checks/branch_status.py` with a thin shim over this module. This issue must
merge before #1068.

Three changes, delivered as three one-commit steps:

1. **Missing-token degradation** (port from fork) — CI-only.
2. **Opt-in review-gate header** (new) — three-state, text signal only.
3. **Configurable default + wiring** (new) — `--fail-on-reviews` server flag,
   per-call override.

## Guiding principle: pure-additive

When `fail_on_reviews` is off/unset **and** a token is present, the existing
report format and MCP tool behaviour are **unchanged**. Item 1 changes only the
token-*absent* path (today `NOT_CONFIGURED` → now `UNAVAILABLE`); the
token-present path is untouched.

## Architectural / design changes

- **New CI state `CIStatus.UNAVAILABLE`** distinguishes "no GitHub token, CI
  truth unknown" from "CI genuinely not configured". Scope is **CI-only** —
  matching the fork exactly keeps the shim behaviour identical. PR / label /
  feedback keep their current fallbacks.
- **Token gate moved to the top of `_collect_ci_status`**: a `get_github_token()
  is None` check returns `UNAVAILABLE` *before* any `CIResultsManager`
  construction or network call, so a missing token degrades cleanly instead of
  crashing.
- **New review-gate header** is a pure function of two fields already on the
  report (`ci_status`, `pr_feedback_blocks_merge`) plus one resolved flag. It
  reuses `ci_status == UNAVAILABLE` as the "no token" signal — **no second token
  lookup**. Rendered via one shared helper (`_review_gate_header`), mirroring the
  existing `_format_wait_line` helper, and appended in **both** `format_for_human`
  and `format_for_llm`. Text signal only — no exception, no nonzero exit.
- **Three-state header, never a misleading binary:**
  - `BLOCKED (reviews)` — `pr_feedback_blocks_merge` is True
  - `clean` — feedback present, nothing blocking
  - `UNKNOWN (no token)` — `ci_status == UNAVAILABLE`; review state
    undeterminable, must never render `clean` or `BLOCKED`
  Blocking keys off `pr_feedback_blocks_merge` **only** — never `mergeable_state`.
- **Tri-state resolved at exactly one boundary.** The `Optional[bool]` tri-state
  exists only to tell "caller didn't pass" from "explicit False" (per-call
  overrides server default). That only matters at the tool parameter, so
  `check_branch_status` resolves `effective = fail_on_reviews if fail_on_reviews
  is not None else _fail_on_reviews` **once**, and threads a plain `bool`
  downstream through `async_poll_branch_status` → `format_for_llm`. One
  `Optional[bool]` in the whole change; everything downstream is a plain `bool`.
- **Server default wiring mirrors `--file-size-limit`**: `main.py` arg →
  `set_fail_on_reviews(...)` module global in `server.py` → override at the tool
  call site. Reusing the existing pattern is the maintainable choice.

## Header format (for the #1068 merge-gate parser)

One plain, greppable, un-truncatable line placed near the top of both formats:

```
Review Gate: BLOCKED (reviews)
Review Gate: clean
Review Gate: UNKNOWN (no token)
```

Rendered only when the effective flag is true; absent otherwise (additive).

## Files created / modified

| File | Change |
|------|--------|
| `src/mcp_workspace/checks/branch_status.py` | **Modified** — Steps 1 & 2: `CIStatus.UNAVAILABLE`, `GITHUB_TOKEN_HINT`, `get_github_token` import + gate, UNAVAILABLE rendering, `_review_gate_header` helper, `fail_on_reviews` param on both formatters |
| `src/mcp_workspace/checks/branch_status_polling.py` | **Modified** — Step 3: thread `fail_on_reviews: bool` through `async_poll_branch_status` into `format_for_llm` |
| `src/mcp_workspace/server.py` | **Modified** — Step 3: `_fail_on_reviews` global, `set_fail_on_reviews`, `fail_on_reviews` param on `check_branch_status`, `run_server` param |
| `src/mcp_workspace/main.py` | **Modified** — Step 3: `--fail-on-reviews` argparse flag, pass to `run_server` |
| `tests/checks/test_branch_status.py` | **Modified** — Steps 1 & 2: UNAVAILABLE + review-gate tests |
| `tests/checks/test_branch_status_polling.py` | **Modified** — Step 3: threading test |
| `tests/test_server_file_size.py` *(or new `tests/test_server_fail_on_reviews.py`)* | **Modified/New** — Step 3: setter + `run_server` wiring test |
| `tests/test_reference_projects.py` | **Modified** — Step 3: `--fail-on-reviews` arg parsing test (alongside existing `main`/arg tests) |

No new folders or modules are introduced.

## Decisions carried from the issue

| # | Topic | Decision |
|---|-------|----------|
| 1 | UNAVAILABLE scope | CI-only; match the fork. PR/label/feedback keep current fallbacks |
| 2 | BLOCKED trigger | `pr_feedback_blocks_merge` only; not `mergeable_state` |
| 3 | Header location | Both `format_for_human` and `format_for_llm` |
| 4 | `fail_on_reviews` type | `Optional[bool] = None` at the tool param only; resolved to `bool` downstream |
| 5 | Blocking mechanism | Text header signal only — no exception, no nonzero exit |
| 6 | No-token + fail_on_reviews | Three-state header: `BLOCKED (reviews)` / `clean` / `UNKNOWN (no token)` |

## Testing note (from CLAUDE.md)

Run all three MCP checks after every edit:
`mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_pytest_check`
(with `-n auto` and the `not <integration>` exclusions), `mcp__tools-py__run_mypy_check`.
The UNAVAILABLE/review-gate tests are pure unit tests (no `git_integration` /
`github_integration` markers needed).
