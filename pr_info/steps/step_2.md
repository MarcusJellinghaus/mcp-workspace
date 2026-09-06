# Step 2 — State `check_file_size`'s scan scope in its docstring

Read [summary.md](summary.md) first.

Documentation-only. Single commit. Independent of steps 1, 3 and 4.

## WHERE

`src/mcp_workspace/server.py`, the `check_file_size` docstring at lines 1532-1544.

## WHAT

`check_file_size(max_lines: Optional[int] = None) -> str` — **signature and body unchanged**. Only
the docstring gains a paragraph.

## HOW

The docstring today opens with `"""Check file line counts against threshold."""` and never states
what it scans. That first line **stays exactly as it is** — #235's salience pattern is deliberately
first-line-terse, because the first line is what the MCP client surfaces in tool listings.

The scope goes in a **body paragraph after the first line and before `Args:`**:

> Counts lines in every UTF-8 file under the project directory — all file types, tracked or not —
> excluding `.git/` and anything the project-root `.gitignore` matches. Nested `.gitignore` files
> are not read.

Resulting shape:

```python
def check_file_size(max_lines: Optional[int] = None) -> str:
    """Check file line counts against threshold.

    <scope paragraph>

    Args:
        max_lines: ...

    Returns:
        ...

    Raises:
        ...
    """
```

Em dashes are used freely in this codebase's docstrings and comments, so the wording can be pasted
verbatim.

## Why this wording is accurate

Verified against the code, not inferred:

- `check_file_sizes` calls `list_files(".", project_dir)` (`file_sizes.py:104`) — the whole project
  tree, with no file-type filter.
- `_discover_files` skips `.git` directories (`directory_utils.py`, `dirs[:] = [d for d in dirs if
  not is_path_in_git_dir(d)]`).
- `filter_with_gitignore` reads exactly one `.gitignore` — the one in `base_dir`
  (`directory_utils.py:166`), which here is the project root. Nested `.gitignore` files are never
  consulted.
- `count_lines` returns `-1` for non-UTF-8/binary files and `get_file_metrics` drops those, so only
  UTF-8-decodable files are counted.

"Tracked or not" is the load-bearing correction: the scan walks the filesystem, it does not consult
git's index.

## ALGORITHM

None — no executable change.

## DATA

None — no change to return values or data structures.

## TESTS

None. No behaviour changes, and no existing test asserts on this docstring.
`tests/test_server_file_size.py` exercises the resolution chain (`max_lines` → `--file-size-limit`
→ 600) and is unaffected.

## CHECKS

```
mcp__mcp-tools-py__run_format_code
mcp__mcp-tools-py__run_pylint_check
mcp__mcp-tools-py__run_pytest_check   (extra_args: ["-n", "auto"])
mcp__mcp-tools-py__run_mypy_check
```

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`.
>
> Implement step 2 only: add the scan-scope paragraph to `check_file_size`'s docstring in
> `src/mcp_workspace/server.py` (around line 1532), placed after the terse first line and before
> `Args:`. Use the exact wording given in step_2.md.
>
> Constraints: the first docstring line must stay byte-identical. Do not change the function
> signature or body. Do not touch any other docstring.
>
> Then run format, pylint, pytest (`-n auto`) and mypy, and commit as
> `docs(server): state check_file_size scan scope`.
