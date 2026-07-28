# Step 3 — Configurable default + threading (`--fail-on-reviews`)

**One commit: tests + implementation + all three checks passing.**

Implements Item 3 of `summary.md`. Wires the review-gate flag end to end:
`--fail-on-reviews` server flag sets a per-server default; the tool parameter
overrides per call. The `Optional[bool]` tri-state lives at **exactly one
boundary** (the `check_branch_status` parameter); everything downstream is a
plain resolved `bool`. Depends on Step 2 (`format_for_llm` must accept
`fail_on_reviews: bool`). Wiring mirrors `--file-size-limit`.

## WHERE

- `src/mcp_workspace/checks/branch_status_polling.py` — thread the bool.
- `src/mcp_workspace/server.py` — global + setter + tool param + `run_server`.
- `src/mcp_workspace/main.py` — argparse flag + pass-through.
- Tests: `tests/checks/test_branch_status_polling.py`,
  `tests/test_server_fail_on_reviews.py` (new), `tests/test_reference_projects.py`.

## WHAT (signatures)

1. **`branch_status_polling.py`**
   ```python
   async def async_poll_branch_status(
       project_dir: Path,
       max_log_lines: int = 300,
       ci_timeout: int = 0,
       pr_timeout: int = 0,
       fail_on_reviews: bool = False,   # NEW, plain bool (already resolved)
   ) -> str:
   ```
   Both `report.format_for_llm(...)` call sites pass
   `fail_on_reviews=fail_on_reviews`.

2. **`server.py`**
   ```python
   _fail_on_reviews: bool = False        # module global, near _file_size_limit

   @log_function_call
   def set_fail_on_reviews(value: bool) -> None: ...   # mirrors set_file_size_limit

   @mcp.tool()
   @log_function_call
   async def check_branch_status(
       max_log_lines: int = 300,
       ci_timeout: int = 300,
       pr_timeout: int = 0,
       fail_on_reviews: Optional[bool] = None,   # NEW — the ONLY Optional[bool]
   ) -> str: ...

   def run_server(
       project_dir: Path,
       reference_projects: Optional[Dict[str, ReferenceProject]] = None,
       file_size_limit: Optional[int] = None,
       fail_on_reviews: bool = False,            # NEW
   ) -> None: ...
   ```

3. **`main.py`** — new argparse flag and pass-through to `run_server`:
   ```python
   parser.add_argument("--fail-on-reviews", action="store_true",
       help="Default for check_branch_status' review gate; the tool "
            "parameter overrides per call.")
   ...
   run_server(project_dir, reference_projects=..., file_size_limit=...,
              fail_on_reviews=args.fail_on_reviews)
   ```

## HOW (integration points)

- `check_branch_status` resolves the tri-state **once**, then passes a bool:
  ```python
  effective = fail_on_reviews if fail_on_reviews is not None else _fail_on_reviews
  return await async_poll_branch_status(..., fail_on_reviews=effective)
  ```
- `run_server` calls `set_fail_on_reviews(fail_on_reviews)` (alongside the
  existing `set_file_size_limit(file_size_limit)`).
- `set_fail_on_reviews` uses `global _fail_on_reviews` + a `logger.info` line,
  copying `set_file_size_limit` verbatim in shape.
- Docstring: document `fail_on_reviews` on `check_branch_status` — "When omitted,
  uses the server's --fail-on-reviews default (off unless set)."

## ALGORITHM (tri-state resolution — the whole point of Step 3)

```
# check_branch_status (server.py) — resolve exactly here, nowhere else
effective = fail_on_reviews if fail_on_reviews is not None else _fail_on_reviews
# None  -> server default (_fail_on_reviews)
# True  -> on  (overrides a False default)
# False -> off (overrides a True default)   <-- why Optional[bool], not bool
return await async_poll_branch_status(..., fail_on_reviews=effective)
```

## DATA

- `_fail_on_reviews: bool` module state (default `False`).
- `check_branch_status` still returns the report `str`.
- `async_poll_branch_status` still returns the `format_for_llm()` `str`.

## TESTS (write first, TDD)

1. **`tests/test_server_fail_on_reviews.py`** (new; model on
   `tests/test_server_file_size.py`):
   - `test_set_fail_on_reviews_sets_global` — `set_fail_on_reviews(True)` sets
     `server._fail_on_reviews is True`; reset in teardown.
   - `test_run_server_threads_fail_on_reviews` — patch
     `mcp_workspace.server.set_fail_on_reviews`; assert `run_server(...,
     fail_on_reviews=True)` calls it with `True`.
   - `test_check_branch_status_none_uses_server_default` — set
     `_fail_on_reviews=True`; patch `async_poll_branch_status`; call the tool with
     `fail_on_reviews=None`; assert it was awaited with `fail_on_reviews=True`.
   - `test_check_branch_status_false_overrides_true_default` — `_fail_on_reviews=
     True`, call with `fail_on_reviews=False`; assert downstream got `False`.
   - `test_check_branch_status_true_overrides_false_default` — `_fail_on_reviews=
     False`, call with `fail_on_reviews=True`; assert downstream got `True`.
2. **`tests/checks/test_branch_status_polling.py`**:
   - `test_async_poll_passes_fail_on_reviews_to_format` — mock the report; assert
     `format_for_llm` received `fail_on_reviews=True` (via
     `call_args.kwargs["fail_on_reviews"]`).
   - Default path: existing tests still pass (default `False` threads through).
3. **`tests/test_reference_projects.py`** (alongside existing `main`/arg tests):
   - `test_main_passes_fail_on_reviews` — `parse_args`/`main` with
     `--fail-on-reviews` results in `run_server(..., fail_on_reviews=True)`.
   - `test_main_fail_on_reviews_default_false` — without the flag → `False`.

## CHECKS

Run and pass all three MCP checks (same invocation as Step 1), including the
polling-integration-free unit subset.

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`. Implement Step 3
> only: wire the review-gate flag end to end, mirroring the existing
> `--file-size-limit` pattern. Follow TDD — first add the tests listed (new
> `tests/test_server_fail_on_reviews.py`, additions to
> `tests/checks/test_branch_status_polling.py` and
> `tests/test_reference_projects.py`), then implement: the `fail_on_reviews: bool
> = False` parameter on `async_poll_branch_status` (passed into both
> `format_for_llm` calls); the `_fail_on_reviews` global, `set_fail_on_reviews`
> setter, `fail_on_reviews: Optional[bool] = None` tool parameter (resolving
> `effective = fail_on_reviews if fail_on_reviews is not None else
> _fail_on_reviews` and passing the resolved bool downstream), and the new
> `run_server` parameter calling `set_fail_on_reviews`; and the `--fail-on-reviews`
> `store_true` argparse flag in `main.py` passed through to `run_server`. The
> `Optional[bool]` must appear ONLY on the tool parameter — everything downstream
> is a plain resolved `bool`. Do not change existing default behaviour. Use MCP
> `mcp__workspace__*` tools. After every edit run the three `mcp__tools-py__run_*`
> checks (pytest with the `-n auto` + `not <integration>` exclusions) and fix all
> issues. Produce exactly one commit.
