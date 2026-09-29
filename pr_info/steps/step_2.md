# Step 2 — `file_sizes` retyping

Removes three normalization workarounds by deleting the `Path` round-trip that creates the
problem they work around. **Depends on step 1** — see the ordering note at the end.

## WHERE

| File | Role |
|---|---|
| `src/mcp_workspace/checks/file_sizes.py` | `FileMetrics`, `get_file_metrics`, `check_file_sizes`, `render_output`, `render_allowlist` |
| `tests/checks/test_file_sizes.py` | four `FileMetrics(path=Path(...))` constructions; new `get_file_metrics` test |

## WHAT

```python
@dataclass
class FileMetrics:
    path: str            # was: Path
    line_count: int

def get_file_metrics(files: List[str], project_dir: Path) -> List[FileMetrics]: ...
#                           ^^^ was: List[Path]
```

Four bodies change:

```python
# get_file_metrics — abs_path = project_dir / file_path still works unchanged (Path / str)

# check_file_sizes
raw_files = list_files(".", project_dir)
metrics = get_file_metrics(raw_files, project_dir)   # the [Path(f) for f in raw_files] line goes
...
normalized = m.path                                  # was: str(m.path).replace("\\", "/")

# render_output
lines.append(f"  - {v.path}: {v.line_count} lines")  # display_path local goes

# render_allowlist
return "\n".join(v.path for v in violations)         # was: str(v.path).replace(...)
```

`load_allowlist` is **unchanged** and keeps its `replace` at line 76. It normalizes
hand-written allowlist entries, which are caller input, not server output.

## HOW

- `FileMetrics` is internal to `checks/file_sizes.py` and its tests; `CheckResult` carries
  it outward but nothing outside the module reads `.path` as a `Path`. Confirm with
  `find_references` before editing.
- `project_dir / file_path` in `get_file_metrics` accepts a `str` right-hand side, so the
  body needs no change beyond the annotation.
- `list_files` returns `List[str]`, so after the retyping `get_file_metrics`' parameter type
  matches its only caller's data exactly and the round-trip has no reason to exist.
- The `Path` import stays — `count_lines`, `load_allowlist` and the `project_dir` parameter
  still use it.
- This is a mypy-level change, not a runtime one: the four test constructions break type
  checking, not execution.

## ALGORITHM

Why the round-trip is the bug and the `replace` is only its dressing:

```
list_files returns "src/mcp_workspace/server.py"           (forward slash, after step 1)
Path(f) then str(...) yields "src\mcp_workspace\server.py" (native, on Windows)
str(m.path).replace("\\","/") undoes it                    (workaround)
--- with FileMetrics.path: str ---
the string is carried through untouched                    (no round-trip, no workaround)
```

## DATA

- `FileMetrics.path` — `str`, project-relative, forward-slash separated.
- `check_file_sizes` → `CheckResult` unchanged in shape; `violations` entries now carry
  `str` paths. `stale_entries` was already `List[str]` and is unchanged.
- `render_output` / `render_allowlist` → `str`, byte-identical to today's output on POSIX
  and corrected on Windows.
- The `_MAX_REPORT_VIOLATIONS` and `_MAX_STALE_ENTRIES` caps are untouched.

## Tests (write first)

New:

1. `get_file_metrics` has no test today. Add one: a temp project with a nested file and a
   binary/non-UTF-8 file; assert the returned `path` values are exactly the input strings
   (forward-slash separated, not round-tripped) and that the unreadable file is excluded
   (`count_lines` returns `-1`).

Modified:

2. The four `FileMetrics(path=Path(...))` constructions at `tests/checks/test_file_sizes.py`
   lines 41, 145, 250 and 251 become `path="..."`.

Keep:

3. `test_normalizes_backslashes` (line 83) covers `load_allowlist`, which is unchanged.
   Leave it alone.

Also assert that allowlist matching still works: a violation whose nested path is listed in
the allowlist must be counted as allowlisted, not reported as a violation or as stale.

## Ordering

Land **after step 1**. Removing the `.replace` while `_discover_files` still emits
backslashes silently breaks allowlist matching on Windows, and every CI job runs on
`ubuntu-latest`, so nothing would catch it. Step 1 does not break `file_sizes` in the
meantime: the `Path` round-trip plus the `.replace` is idempotent on forward-slash input.

## Checks

`run_format_code`, then `run_pylint_check`, `run_pytest_check` with `["-n", "auto"]`,
`run_mypy_check`. One commit.

---

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`, then implement step 2.
> Step 1 must already be committed.
>
> Retype `FileMetrics.path` from `Path` to `str` in `src/mcp_workspace/checks/file_sizes.py`.
> This deletes the `[Path(f) for f in raw_files]` round-trip in `check_file_sizes` and the
> three `str(...).replace("\\", "/")` calls it forced, in `check_file_sizes`, `render_output`
> and `render_allowlist`.
>
> Leave `load_allowlist` alone — its `replace` normalizes hand-written caller input, not
> server output, and `test_normalizes_backslashes` pins it.
>
> Work test-first: add the missing `get_file_metrics` test and update the four
> `FileMetrics(path=Path(...))` constructions in `tests/checks/test_file_sizes.py` first.
> Run `find_references` on `FileMetrics` before editing to confirm nothing outside the
> module treats `.path` as a `Path`.
>
> Use the MCP tools per `CLAUDE.md`. Run `run_format_code`, then `run_pylint_check`,
> `run_pytest_check` with `extra_args: ["-n", "auto"]`, and `run_mypy_check`. All must pass.
> Commit once.
