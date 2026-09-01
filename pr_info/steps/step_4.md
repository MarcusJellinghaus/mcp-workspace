# Step 4 — Document glob semantics in all three docstrings, guarded by a test

Read [summary.md](./summary.md) first.

The docstring in `search.py` is the only correct one today, and it is the one callers never
see. The MCP tool descriptions do reach callers and say only `File path pattern`. All three
get the same four points; a guard test fails CI on the next drift.

## WHERE

- `src/mcp_workspace/server.py` — `search_files` docstring (`glob:` arg, `Raises:`)
- `src/mcp_workspace/server_reference_tools.py` — `search_reference_files` docstring
  (`glob:` arg, plus a `Raises:` block it does not have at all today)
- `src/mcp_workspace/file_tools/search.py` — `search_files` docstring, aligned for
  consistency
- `tests/test_tool_descriptions.py` — **new file**

New file because both natural homes are at the size cap: `tests/test_server.py` is 738 lines
and `tests/test_reference_projects_mcp_tools.py` is 739. There is no precedent for this kind
of test in the repo.

## WHAT — test first

```python
"""Guard tests: MCP tool descriptions document glob semantics."""

GLOB_DOC_PHRASES = [
    "gitignore",
    "brace expansion is not supported",
    "any depth",
    "case-insensitive",
    "git ls-files",
]

@pytest.mark.parametrize("phrase", GLOB_DOC_PHRASES)
@pytest.mark.parametrize(
    "func",
    [server.search_files, server_reference_tools.search_reference_files],
    ids=["search_files", "search_reference_files"],
)
def test_tool_description_documents_glob_semantics(
    func: Any, phrase: str
) -> None:
    assert phrase in (func.__doc__ or "").lower()
```

Compare against `.lower()` so the docstrings stay free to capitalise. Annotate both
parameters — mypy strict applies to `tests/` (only `unreachable` and `union-attr` are
disabled there).

## HOW

`FastMCP.tool()` returns the function unchanged and `log_function_call` uses
`functools.wraps`, so `server.search_files.__doc__` and
`server_reference_tools.search_reference_files.__doc__` are readable directly. No
`list_tools()` plumbing, no server instantiation.

`search_reference_files` is `async`; the test only reads `__doc__`, so it is a plain sync
test with no `pytest.mark.asyncio`.

## DATA — the shared `glob:` text

Same four points in all three docstrings (wording may differ slightly to fit each signature,
but every phrase in `GLOB_DOC_PHRASES` must survive):

```
glob: File path pattern with gitignore/wildmatch semantics — e.g. "**/*.py",
    "tests/**/test_*.py", "/README.md" (root only).
    Brace expansion is NOT supported: "{a,b}/f.py" matches a literal "{a,b}"
    directory. Issue one call per alternative, or widen to "*" and filter.
    A bare "*.py" is unanchored and matches at any depth, unlike a shell glob.
    On Windows, matching is case-insensitive by design, so a glob cannot detect
    a filename casing mismatch — use `git ls-files`, which reports the name as
    recorded in the index.
```

`Raises:` additions:

- `server.search_files` — extend the existing entry: project directory not set, **or** the
  glob matches nothing by construction
- `search_reference_files` — new `Raises:` block for the same glob `ValueError`; it
  propagates from the util through the async `log_function_call` wrapper, which
  logs-then-re-raises
- `file_tools.search.search_files` — already covered in step 2

## Ruff DOC502 risk

`D`/`DOC` rules run with `preview` on `src/`. DOC502 flags an exception that is documented
but not raised in the function body — likely for `search_reference_files`, which only
propagates. If it fires, add the module to the existing DOC502 `per-file-ignores` list in
`pyproject.toml`, next to `file_operations.py` and `read_operations.py`, with the same
rationale comment. Do not delete the documentation and do not add inline `noqa`.

## Checks

`run_format_code`, then pylint / pytest (`-n auto`) / mypy / ruff.

Sanity check that the guard works: temporarily remove one phrase from one docstring, confirm
the test fails, restore it.

## Commit

`docs(search): document glob semantics in tool descriptions`

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_4.md`.
>
> Create `tests/test_tool_descriptions.py` with the parametrized guard test, confirm it
> fails, then write the four documented behaviours into the `glob:` argument of all three
> docstrings — `server.search_files`, `server_reference_tools.search_reference_files`, and
> `file_tools.search.search_files` — and add the `Raises:` entries. Only docstrings change in
> `src/`; no logic.
>
> Then run `run_format_code`, `run_pylint_check`, `run_pytest_check` with
> `extra_args: ["-n", "auto"]`, `run_mypy_check`, and `run_ruff_check`. If ruff reports
> DOC502, add the affected module to the DOC502 `per-file-ignores` in `pyproject.toml`.
> Commit as `docs(search): document glob semantics in tool descriptions`.
