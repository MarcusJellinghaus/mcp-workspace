# Step 3 — Operation-level absolute-traversal coverage

Read [summary.md](./summary.md) first. Depends on step 1. Test-only commit.

The existing blind spot runs right through `tests/file_tools/test_file_operations.py`: the
traversal tests for `read_file`, `save_file`/`append_file`, `delete_file` and
`delete_directory` are **all relative-only**, which is exactly why five researchers found
this before the test suite did. A generic "traversal test" would not have caught it; an
absolute-form one for each operation would.

## WHERE

`tests/file_tools/test_file_operations.py` — one parametrized test added. Nothing else
changes; no source file is touched in this step.

## WHAT

```python
@pytest.mark.parametrize("operation", [...], ids=[...])
def test_operations_reject_absolute_traversal(
    project_dir: Path, operation: Callable[[str, Path], object]
) -> None: ...
```

## HOW

- One parametrized test over seven callables, not seven near-identical test functions. The
  bodies differ only in which function is called.
- Build the escape path from the `project_dir` fixture (which is `tmp_path`), never from a
  hardcoded POSIX string — `Path("/tmp/x").is_absolute()` is `False` on Windows, so a
  hardcoded path would test the relative branch there and prove nothing.
- `move_file` passes source **and** destination through `normalize_path` independently
  (`file_operations.py:503-504`), so each argument gets its own parameter. Neither path needs
  to exist: both `normalize_path` calls run before any existence check.
- The existing relative-form security tests stay exactly as they are — they are the controls
  that isolate the defect to the absolute branch, and four of them
  (`test_save_file_security`, `test_read_file_security`, `test_delete_file_security`,
  `test_append_file_security`) now assert a message produced by the `..` guard rather than
  the containment guard. If any needs editing, step 1's message helper is wrong.

## ALGORITHM

```
escape = str(project_dir / ".." / "outside_project.txt")   # absolute, contains '..'
with pytest.raises(ValueError, match="Security error"):
    operation(escape, project_dir)
```

## DATA

The seven parameters, with readable `ids`:

| id | callable |
|---|---|
| `read_file` | `lambda p, d: read_file(p, project_dir=d)` |
| `save_file` | `lambda p, d: save_file(p, "x", project_dir=d)` |
| `append_file` | `lambda p, d: append_file(p, "x", project_dir=d)` |
| `delete_file` | `lambda p, d: delete_file(p, project_dir=d)` |
| `delete_directory` | `lambda p, d: delete_directory(p, d, recursive=True)` |
| `move_file_source` | `lambda p, d: move_file(p, "dest.txt", project_dir=d)` |
| `move_file_destination` | `lambda p, d: move_file("source.txt", p, project_dir=d)` |

Check each import is already present at the top of the module and add only what is missing.

## Checks

`run_format_code`, then `run_pylint_check`, `run_pytest_check` (`extra_args: ["-n", "auto"]`),
`run_mypy_check`.

## Commit

`test(file_operations): cover absolute-path traversal (#290)`

## LLM prompt

> Implement step 3 of the plan in `pr_info/steps/step_3.md`, using `pr_info/steps/summary.md`
> for context. Steps 1 and 2 must already be committed.
>
> This is a test-only commit: add one parametrized test to
> `tests/file_tools/test_file_operations.py` covering the absolute form of the traversal
> check for all seven operations in the DATA table, including both arguments of `move_file`
> separately. Build the escape path from the `project_dir` fixture, not from a hardcoded
> `/tmp/...` string. Change no source file and no existing test — the existing relative-form
> security tests are deliberate controls.
>
> Verify the new test fails against the pre-step-1 `normalize_path` if you want confirmation
> it bites (revert-check optional; do not commit that state). Then run `run_format_code`,
> `run_pylint_check`, `run_pytest_check` with `extra_args: ["-n", "auto"]`, and
> `run_mypy_check`. One commit for the step.
