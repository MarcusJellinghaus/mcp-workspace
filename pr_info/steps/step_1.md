# Step 1 — Tolerant, raising `parse_args()`

Read `pr_info/steps/summary.md` first for the overall design. This step only
touches `parse_args()`; the two-stage pre-parser and the `main()`/`_main()` split
come in step 2.

## Precondition

`src/mcp_workspace/main.py` contains exactly one `parse_args()` function that
builds one `argparse.ArgumentParser`, sets `required=True` on `--project-dir` and
`choices=[...]` on `--log-level`, and returns `parser.parse_args()`. If this
function has already been changed to return a tuple, or no longer matches this
shape, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/main.py`
- `tests/test_reference_projects.py`

## WHAT

Add, in `src/mcp_workspace/main.py`:

```python
class StartupArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None: ...  # raises ValueError(message)
```

Change the existing `parse_args() -> argparse.Namespace` to:

```python
def parse_args(
    argv: Optional[List[str]] = None,
) -> Tuple[argparse.Namespace, List[str]]: ...
```

## HOW

- `parse_args` builds a `StartupArgumentParser` (not the plain base class) with
  `allow_abbrev=False`.
- `--project-dir`: drop `required=True`; keep `type=str`; help text keeps the
  word "required" (e.g. `"Base directory for all file operations (required)"`).
- `--log-level`: drop `choices=[...]`; keep `default="INFO"`; help text spells
  out the five level names.
- Everything else (`--version`, `--log-file`, `--console-only`,
  `--reference-project`, `--file-size-limit`, `--fail-on-reviews`) is unchanged.
- Return `parser.parse_known_args(argv if argv is not None else sys.argv[1:])`
  instead of `parser.parse_args()`.
- Update `main()`'s single call site: `args = parse_args()` becomes
  `args, _unknown = parse_args()`. Nothing else in `main()` changes in this step
  (the `_unknown` list is wired up for real in step 3).

## ALGORITHM

```
error(message):
    raise ValueError(message)        # instead of print + sys.exit(2)

parse_args(argv=None):
    build StartupArgumentParser(allow_abbrev=False)
    add all options as today, minus required=True and choices=[...]
    return parser.parse_known_args(argv or sys.argv[1:])
```

## DATA

- Return value: `(argparse.Namespace, list[str])` — the namespace as before, plus
  the list of tokens `argparse` did not recognize.
- A missing value for a known flag, or a non-integer `--file-size-limit`, now
  raises `ValueError` instead of raising `SystemExit(2)`.

## Tests (write first)

In `tests/test_reference_projects.py`, update the seven existing tests that call
`parse_args()` directly to unpack `args, unknown = parse_args()`:

- `test_parse_single_reference_project`
- `test_parse_multiple_reference_projects`
- `test_parse_file_size_limit`
- `test_parse_file_size_limit_default`
- `test_parse_file_size_limit_rejects_non_integer` — change
  `with pytest.raises(SystemExit): parse_args()` to
  `with pytest.raises(ValueError): parse_args()`
- `test_parse_fail_on_reviews`
- `test_parse_fail_on_reviews_default`

Add one new test, `test_parse_abbreviated_flag_is_unknown`: call `parse_args()`
with `sys.argv` patched to
`["script.py", "--project-dir", "/tmp", "--project", "/other"]` (`--project` is
an abbreviation of `--project-dir` that used to resolve via `argparse`'s default
abbreviation matching) and assert `"--project"` and `"/other"` both appear in the
returned `unknown` list, and `args.project_dir == "/tmp"` (the full flag, not the
abbreviation, won).

## Checks

Run `mcp__mcp-tools-py__run_pytest_check` (with `extra_args: ["-n", "auto"]`),
`run_pylint_check`, `run_mypy_check`. Confirm the rest of
`tests/test_reference_projects.py` (the `main()`-level tests) still passes
unchanged — it should, since `main()`'s behavior is otherwise untouched in this
step.

## Commit

One commit: `feat(main): raise instead of exit on CLI parse errors`

## LLM prompt for this step

> Read `pr_info/steps/summary.md` for the overall design, then implement
> exactly `pr_info/steps/step_1.md`. Follow TDD: write/update the tests in
> `tests/test_reference_projects.py` first, see them fail for the right reason,
> then change `src/mcp_workspace/main.py`. Do not touch `main()`'s control flow
> beyond the one-line unpack described in the step. Run pytest, pylint, and
> mypy via the MCP tools and make sure all three pass before committing. If the
> precondition in the step file does not hold, write one line to
> `pr_info/.blocked.txt` and stop.
