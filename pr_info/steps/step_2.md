# Step 2 — Shrink the docstring and the `usage` value

One commit, test-first. Read [summary.md](./summary.md) first.

## WHERE

| File | Lines |
|---|---|
| `tests/test_reference_projects_mcp_tools.py` | 58-64, 92-98 |
| `src/mcp_workspace/server_reference_tools.py` | 37-50 (docstring), 78-84 (`usage`) |
| `README.md` | 383 |

## WHAT

The new `usage` value, used verbatim in all four places:

```
Pass a name as reference_name to the reference file tools, git(), and the GitHub read tools; issues can also be created, edited and commented on
```

No trailing period (matching the current value), no project count, no tool roster.
The claim is scoped to the **read** tools plus issue writes: `github_pr_create` has no
`reference_name` parameter (`src/mcp_workspace/server.py:1464`), so "the GitHub tools"
without qualification would be false and would contradict the bullet step 3 writes at
`README.md:460`.

### 1. Tests first

Both expectations are exact full-dict comparisons — one at three projects, one at one
project. With the count gone from `usage`, the two expected strings become identical.
Replace the five-line parenthesised string in each:

```python
# tests/test_reference_projects_mcp_tools.py:58-64 and 92-98
"usage": (
    "Pass a name as reference_name to the reference file tools, git(), "
    "and the GitHub read tools; issues can also be created, edited and "
    "commented on"
),
```

`test_get_reference_projects_empty` (line 24-29) is **unchanged** — the `count: 0`
branch keeps `"No reference projects available"`.

Run pytest and confirm `test_get_reference_projects_sorted` and
`test_get_reference_projects_logging` fail before touching the source.

### 2. Then the source

```python
@log_function_call
def get_reference_projects() -> Dict[str, Any]:
    """Get available reference project names.

    Returns:
        Dictionary containing:
        - count: Number of available projects
        - projects: List of {"name", "url"} dicts, sorted by name
        - usage: Instructions for next steps

    Pass a name as reference_name to the reference file tools, git(), and the
    GitHub read tools; issues can also be created, edited and commented on.
    """
```

Three changes: the capability paragraph after `Returns:` is deleted and replaced by the
one-line pointer; `projects` is corrected from "List of project names" to the actual
`{"name", "url"}` dicts; the summary line and the `Returns:` block otherwise stand.

Keep the `Returns:` block — **ruff DOC201 fails without it.** Free-form prose after
`Returns:` lints clean, which is why the pointer goes last.

In the body, the f-string at lines 78-84 becomes a plain literal:

```python
return {
    "count": len(projects),
    "projects": projects,
    "usage": (
        "Pass a name as reference_name to the reference file tools, git(), "
        "and the GitHub read tools; issues can also be created, edited and "
        "commented on"
    ),
}
```

### 3. Then the README example

`README.md:383`, inside the `Get Reference Projects` example block:

```
#   "usage": "Pass a name as reference_name to the reference file tools, git(), and the GitHub read tools; issues can also be created, edited and commented on"
```

`README.md:374` (the `projects` field description) and the surrounding `**Returns:**`
list stay as they are.

## HOW

No signature, import, decorator or return-type change. `get_reference_projects()`
keeps its `@log_function_call` decorator and its `Dict[str, Any]` return type, and
stays registered by `register()` at the bottom of the module.

## ALGORITHM

The function body is otherwise untouched:

```
if no reference projects:  return {count: 0, projects: [], usage: "No reference projects available"}
projects = sorted([{name, url} for each project], key=name)     # never path
log count and names
return {count: len(projects), projects: projects, usage: <new constant string>}
on exception: log and re-raise
```

## DATA

Return shape is unchanged: `{"count": int, "projects": list[dict], "usage": str}`.
`projects` entries stay `{"name": str, "url": str | None}` — **`path` must never be
added**; no filesystem path may reach the model.

## Checks

`run_format_code`, then `run_pylint_check`, `run_pytest_check` with
`extra_args: ["-n", "auto"]`, `run_mypy_check`, `run_ruff_check` (the `D`/`DOC` rules
are the point here). `tests/LLM_Test.md:104` asserts only that `usage` is a `str`, so
it needs no edit.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`.
>
> Implement step 2 test-first: update both `usage` expectations in
> `tests/test_reference_projects_mcp_tools.py` (lines 58-64 and 92-98) to the new
> string, confirm the two tests fail, then shrink the `get_reference_projects`
> docstring and `usage` value in `src/mcp_workspace/server_reference_tools.py` and
> update the quoted example at `README.md:383`. Use the exact strings given in the
> step. Leave the `count: 0` branch and its test alone, and keep the `Returns:` block
> — ruff DOC201 needs it.
>
> Use the `mcp__mcp-workspace__*` tools for all file access. Then run
> `run_format_code`, `run_pylint_check`, `run_pytest_check` with
> `extra_args: ["-n", "auto"]`, `run_mypy_check` and `run_ruff_check`, and commit
> once with all checks passing.
