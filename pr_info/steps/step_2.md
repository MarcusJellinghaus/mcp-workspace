# Step 2 — `--enforce-base-branch-format` flag plumbing

See `pr_info/steps/summary.md` for full context. This step only adds the flag
and its plumbing; nothing reads it yet (the helper that will consult it is
added in step 3). The flag is inert in this step — it has no observable
effect — which is expected and correct.

## Precondition

`src/mcp_workspace/server.py` must contain `_fail_on_reviews`,
`set_fail_on_reviews`, and `run_server(..., fail_on_reviews: bool = False, ...)`
exactly as described in the summary, and `src/mcp_workspace/main.py` must have
a `--fail-on-reviews` `store_true` argument passed through to `run_server`. If
either does not match, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/server.py` (modify)
- `src/mcp_workspace/main.py` (modify)
- `tests/test_server_enforce_base_branch_format.py` (new)
- `tests/test_main.py` (modify — `parse_args` and `main()` tests; was `tests/test_reference_projects.py`, split to stay under the 750-line limit and mirror `src/mcp_workspace/main.py`)

## WHAT

`server.py`, next to `_fail_on_reviews`:

```python
_enforce_base_branch_format: bool = True
```

```python
@log_function_call
def set_enforce_base_branch_format(value: bool) -> None: ...
```

`run_server` gains one parameter, inserted after `fail_on_reviews`:

```python
def run_server(
    project_dir: Path,
    reference_projects: Optional[Dict[str, ReferenceProject]] = None,
    file_size_limit: Optional[int] = None,
    fail_on_reviews: bool = False,
    enforce_base_branch_format: bool = True,
) -> None: ...
```

`main.py`'s `parse_args`, next to `--fail-on-reviews`:

```python
parser.add_argument(
    "--enforce-base-branch-format",
    action=argparse.BooleanOptionalAction,
    default=True,
    help="Reject a malformed `### Base Branch` section (more than one line) "
    "when creating or editing an issue body. Disable with "
    "--no-enforce-base-branch-format.",
)
```

## HOW

- `server.py`: place `_enforce_base_branch_format: bool = True` directly below
  the `_fail_on_reviews` module global and its comment; add
  `set_enforce_base_branch_format` directly below `set_fail_on_reviews`,
  decorated with `@log_function_call` and logging via `logger.info`, matching
  that function's shape exactly.
- `run_server`: add the call `set_enforce_base_branch_format(enforce_base_branch_format)`
  directly below the existing `set_fail_on_reviews(fail_on_reviews)` call; add
  the matching docstring `Args:` line.
- `main.py`: add the `add_argument` call directly below the `--fail-on-reviews`
  one; in `main()`, add
  `enforce_base_branch_format=args.enforce_base_branch_format,` to the
  `run_server(...)` call, directly below `fail_on_reviews=args.fail_on_reviews,`.

## ALGORITHM

Pure plumbing, no branching logic:

```
parse_args(): add --enforce-base-branch-format (BooleanOptionalAction, default True)
main(): run_server(..., enforce_base_branch_format=args.enforce_base_branch_format)
run_server(..., enforce_base_branch_format=True): set_enforce_base_branch_format(enforce_base_branch_format)
set_enforce_base_branch_format(value): global _enforce_base_branch_format = value
```

## DATA

- `args.enforce_base_branch_format: bool` — `True` by default, `False` after
  `--no-enforce-base-branch-format`.
- `server_module._enforce_base_branch_format: bool` — module global, default
  `True`, mutated only by the setter.

## TDD order

1. Create `tests/test_server_enforce_base_branch_format.py`, modeled on
   `tests/test_server_fail_on_reviews.py`'s `TestSetFailOnReviews` and
   `TestRunServerFailOnReviews` classes, but with the default inverted to
   `True`:
   - fixture `_reset_global` resets `server_module._enforce_base_branch_format = True`
     after each test (not `False`).
   - `test_set_enforce_base_branch_format_sets_global`: call
     `set_enforce_base_branch_format(False)`, assert the global is `False`.
   - `test_run_server_threads_enforce_base_branch_format`: patch
     `mcp_workspace.server.set_enforce_base_branch_format`, call
     `run_server(Path("/test/project"), enforce_base_branch_format=False)`,
     assert `mock_setter.assert_called_once_with(False)`.
   - `test_run_server_default_is_true`: call `run_server(Path("/test/project"))`
     with the setter patched, assert `mock_setter.assert_called_once_with(True)`.
2. In `tests/test_main.py`, add next to `TestParseArgs`'s
   `test_parse_fail_on_reviews` / `test_parse_fail_on_reviews_default`:
   - `test_parse_enforce_base_branch_format_default`: no flag passed, assert
     `args.enforce_base_branch_format is True`.
   - `test_parse_no_enforce_base_branch_format`: pass
     `--no-enforce-base-branch-format`, assert
     `args.enforce_base_branch_format is False`.
   Add next to `TestMain`'s `test_main_passes_fail_on_reviews` /
   `test_main_fail_on_reviews_default_false`:
   - `test_main_passes_no_enforce_base_branch_format`: `sys.argv` includes
     `--no-enforce-base-branch-format`; assert
     `mock_run_server.call_args[1]["enforce_base_branch_format"] is False`.
   - `test_main_enforce_base_branch_format_default_true`: no flag; assert
     `mock_run_server.call_args[1]["enforce_base_branch_format"] is True`.
3. Run all four new/modified test groups — they fail (attributes/params do
   not exist yet).
4. Implement the global, setter, `run_server` parameter, and `main.py`
   argparse flag plus pass-through.
5. Re-run; all pass. Also run the full existing
   `tests/test_server_fail_on_reviews.py` and
   `tests/test_main.py`, `tests/test_main_validate_reference_projects.py`,
   `tests/test_server_reference_tools.py` and `tests/test_server.py` suites to
   confirm no regression from
   the new `run_server` parameter (e.g. any test that asserts the full kwargs
   of a mocked `run_server`/`main()` call) — if any such assertion breaks,
   add `enforce_base_branch_format=True` (or `False`, matching the scenario)
   to its expected kwargs; do not change the flag's default in `main.py` or
   `server.py` to make a stale test pass.

## Checks and commit

Run `mcp__mcp-tools-py__run_format_code`, then
`mcp__mcp-tools-py__run_pylint_check`, `mcp__mcp-tools-py__run_pytest_check`
(`extra_args: ["-n", "auto"]`), `mcp__mcp-tools-py__run_mypy_check`. All must
pass. Then one commit:

```
feat(server): add --enforce-base-branch-format flag (unused)

Plumbing only, mirroring --fail-on-reviews: main.py argparse ->
run_server -> set_enforce_base_branch_format -> module global.
Defaults to True throughout. No tool reads the flag yet.
```

## LLM prompt for this step

```
Read pr_info/steps/summary.md for context, then implement
pr_info/steps/step_2.md exactly as written. Follow TDD: write the new/updated
tests first (tests/test_server_enforce_base_branch_format.py,
tests/test_main.py), confirm they fail, then add the module
global, setter, run_server parameter in src/mcp_workspace/server.py and the
--enforce-base-branch-format / --no-enforce-base-branch-format flag plus
pass-through in src/mcp_workspace/main.py. Do not add any helper that reads
the flag yet (that is step 3) and do not touch github_issue_create or
github_issue_edit. Check whether any existing test asserts the full kwargs of
a mocked run_server or main() call and update it to include
enforce_base_branch_format if so, without changing any default. Run format,
pylint, pytest (-n auto), and mypy; all must pass. If the precondition in
step_2.md does not hold, write one line to pr_info/.blocked.txt and stop.
Make exactly one commit.
```
