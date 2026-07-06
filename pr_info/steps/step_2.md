# Step 2 — `main.py`: `--file-size-limit` CLI flag, fail-fast validation, wiring

**Read `pr_info/steps/summary.md` first.** This step implements the CLI half of issue #221.
It depends on Step 1 (`run_server` must already accept `file_size_limit`). This is one
commit (tests + implementation + checks passing).

Follow TDD: write the tests first, then implement in `src/mcp_workspace/main.py`, then run
all checks.

## WHERE

- `src/mcp_workspace/main.py`
- `tests/test_reference_projects.py` (existing home of `parse_args` / `main()` tests)

## WHAT (signatures)

No new functions. In `parse_args()` add an argument; in `main()` add validation and pass
the value through:

```python
# in parse_args(), alongside the other parser.add_argument(...) calls
parser.add_argument(
    "--file-size-limit",
    type=int,
    default=None,
    help="Default line limit for check_file_size when max_lines is omitted "
         "(must be > 0; falls back to 600 if not set).",
)
```

## HOW (integration points)

- `type=int` makes argparse exit automatically on non-integer input — no manual handling
  needed for that case.
- Add the `<= 0` guard in `main()` **right after `parse_args()`**, matching the existing
  `--project-dir` validation style (`print(...)` then `sys.exit(1)`):

  ```python
  if args.file_size_limit is not None and args.file_size_limit <= 0:
      print(f"Error: --file-size-limit must be a positive integer: {args.file_size_limit}")
      sys.exit(1)
  ```

- Update the `run_server(...)` call at the end of `main()` to pass the value as a keyword,
  mirroring `reference_projects=`:

  ```python
  run_server(
      project_dir,
      reference_projects=reference_projects,
      file_size_limit=args.file_size_limit,
  )
  ```

## ALGORITHM

```
args = parse_args()
validate project_dir (existing)
if args.file_size_limit is not None and args.file_size_limit <= 0: print(...); sys.exit(1)
... existing logging / truststore / reference-project setup ...
run_server(project_dir, reference_projects=..., file_size_limit=args.file_size_limit)
```

## DATA

- `args.file_size_limit`: `int | None` (`None` when flag omitted).
- No return-value changes.

## Tests (write first, `tests/test_reference_projects.py`)

Mirror the existing `sys.argv`-patching and `main()`-mocking patterns already in this file
(`test_parse_single_reference_project`, `test_main_with_reference_projects`).

1. **`parse_args` parses the flag** — `sys.argv = ["script.py", "--project-dir", "/tmp",
   "--file-size-limit", "750"]`; assert `args.file_size_limit == 750`.
2. **`parse_args` default is `None`** — `sys.argv = ["script.py", "--project-dir", "/tmp"]`;
   assert `args.file_size_limit is None`.
3. **`main()` fails fast on `<= 0`** — patch `Path.exists`/`Path.is_dir` (True),
   `mcp_workspace.main.setup_logging`, and `mcp_workspace.server.run_server`;
   `sys.argv = [..., "--file-size-limit", "0"]`; assert `pytest.raises(SystemExit)` and
   that `run_server` was **not** called.
4. **`main()` passes the value through** — same mocks; `sys.argv = [..., "--file-size-limit",
   "750"]`; call `main()`; assert
   `mock_run_server.call_args[1]["file_size_limit"] == 750`.
5. **Backward compatibility** — no flag; assert
   `mock_run_server.call_args[1]["file_size_limit"] is None`.

## Definition of done

- New tests pass; existing tests still pass.
- Run all checks and fix any issue before committing:
  - `mcp__tools-py__run_pylint_check`
  - `mcp__tools-py__run_pytest_check` with
    `extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"]`
  - `mcp__tools-py__run_mypy_check`
- Exactly one commit for this step (run `./tools/format_all.sh` before committing).
- All issue acceptance criteria are now met; if the full arch suite (lint-imports,
  vulture, tach) is part of the gate, run it and confirm green.
