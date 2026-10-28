# Step 6 — `check_file_size(show_allowlisted=True)`

## LLM prompt

> Read `pr_info/steps/summary.md` (section 3) and this file, `pr_info/steps/step_6.md`.
> Implement exactly this step with TDD: write the tests first, then the code.
> Run pylint, pytest (`-n auto`) and mypy; all must pass. Run format_code, then make one commit.

## WHERE
- `src/mcp_workspace/checks/file_sizes.py` — new `render_allowlisted`; reword both cap comments
- `src/mcp_workspace/server.py` — `check_file_size`; import `render_allowlisted`
- `tests/checks/test_file_sizes.py` — `render_allowlisted` tests
- `tests/test_server_file_size.py` — routing tests

## WHAT

```python
def render_allowlisted(project_dir: Path, max_lines: int, allowlist: Set[str]) -> str:
    """List every allowlist entry with its size, largest first. Never reports a failure."""

def check_file_size(max_lines: Optional[int] = None, show_allowlisted: bool = False) -> str:
```

## HOW
- `check_file_size`: after loading the allowlist,
  `if show_allowlisted: return render_allowlisted(_project_dir, effective, allowlist)`;
  otherwise the existing `check_file_sizes` + `render_output` path, unchanged.
- Docstring: `show_allowlisted` lists only allowlist entries with size / `not scanned` / `missing`, largest first,
  uncapped, removable entries marked; a listing, never a failure; the gate is the call without the flag.
- Cap comments: replace "check_file_size has no lift parameter and is not getting one" with wording that the
  cap applies to the default report; `show_allowlisted=True` lists allowlist entries uncapped. Keep the
  narrowing advice in the violations comment.

## ALGORITHM

```
sizes = {m.path: m.line_count for m in get_file_metrics(list_files(".", project_dir), project_dir)}
for entry in allowlist:
    if entry in sizes:
        text = f"{sizes[entry]} lines" + ("  (under limit - can be removed)" if sizes[entry] <= max_lines else "")
        rows.append((0, -sizes[entry], entry, text))
    elif (project_dir / entry).is_file(): rows.append((1, 0, entry, "not scanned (gitignored/binary)"))
    else: rows.append((2, 0, entry, "missing   (can be removed)"))
lines = [f"Allowlisted files ({len(allowlist)}), limit {max_lines}:"] + [f"  {path}: {text}" for *_, path, text in sorted(rows)]
```

Under-limit means `line_count <= max_lines` (the default check's pass rule). A directory entry falls into `missing`.

## DATA
Example output:

```
Allowlisted files (4), limit 600:
  tests/a.py: 1390 lines
  src/foo.py: 540 lines  (under limit - can be removed)
  build/gen.py: not scanned (gitignored/binary)
  src/gone.py: missing   (can be removed)
```

Empty allowlist → only `Allowlisted files (0), limit 600:`.

## Tests

`tests/checks/test_file_sizes.py` (build files in `tmp_path`):
1. Order: sized desc, tie on line count broken by path, then not-scanned, then missing — exact output string.
2. Under-limit (including exactly `max_lines`) marked `(under limit - can be removed)`.
3. Gitignored entry (`.gitignore` with `build/`) and non-UTF-8 entry → `not scanned (gitignored/binary)`.
4. Missing file and a directory entry → `missing   (can be removed)`.
5. Empty allowlist → header with `(0)` only.
6. 60 entries over the limit → all 60 listed, no `... showing` line.
7. Output never contains `"failed"` or `"passed"`, even with non-allowlisted violations present.

`tests/test_server_file_size.py`:
8. `check_file_size(show_allowlisted=True)` calls `render_allowlisted` with the effective limit and does not call
   `check_file_sizes`.
9. Default call still calls `check_file_sizes` + `render_output` and not `render_allowlisted`.
