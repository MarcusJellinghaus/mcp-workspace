# Step 4 — `search_paths`: the search engine on an injected file list and reader

No behaviour change for `search_files`.

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_4.md`.
> Write the tests first, then the implementation. Use the MCP tools from `.claude/CLAUDE.md`.
> Run pylint, pytest (`extra_args: ["-n", "auto"]`) and mypy; all must pass. Run
> `run_format_code`, then make exactly one commit for this step.

## WHERE

- `src/mcp_workspace/file_tools/search.py`
- `tests/file_tools/test_search_paths.py` (new)

## WHAT

```python
def search_paths(
    files: list[str],
    read_lines: Callable[[str], list[str]],
    glob: str | None = None,
    pattern: str | None = None,
    context_lines: int = 0,
    max_results: int = 50,
    max_result_lines: int = 200,
) -> dict[str, Any]: ...

def search_files(project_dir: Path, glob=None, pattern=None, context_lines=0,
                 max_results=50, max_result_lines=200) -> dict[str, Any]:
    # unchanged signature and docstring; now a wrapper
```

`_search_content(files, compiled, read_lines, context_lines, max_results, max_result_lines)`
— `project_dir` replaced by `read_lines`.

## HOW

- `search_paths` = today's body of `search_files` minus `list_accessible_files`; `files` is
  used in the given order; `_match_glob`, `_glob_note`, the literal-pattern note and all
  result keys stay exactly as today.
- In `_search_content` the per-file block becomes `file_lines = read_lines(rel_path)` inside
  the existing `try` (`UnicodeDecodeError` → silent skip first, then `(ValueError, OSError)`
  → `skipped_files`).
- `search_files` builds the working-tree reader:

```python
def _read_local_lines(project_dir: Path, rel_path: str) -> list[str]:
    abs_path, _ = normalize_path(rel_path, project_dir)
    with open(abs_path, encoding="utf-8") as f:
        return f.readlines()

return search_paths(list_accessible_files(".", project_dir).files,
                    functools.partial(_read_local_lines, project_dir), glob, pattern, ...)
```

## DATA

Same result dicts as today (`mode`, `details`/`files`, `total_matches`/`total_files`,
`truncated`, `matched_files`, `skipped_files`, `note`, `glob_note`).

## Tests (write first)

With an in-memory dict `{path: lines}` as the reader:
- Order of `files` is kept in both file-search and content-search results (e.g.
  `["b/x.py", "a.py"]` stays in that order).
- A reader raising `OSError` or `ValueError` for one path → that path in `skipped_files`,
  others still searched; a reader raising `UnicodeDecodeError` → silently skipped.
- `glob="{a,b}.py"` with no match → `glob_note`; unparseable glob → `ValueError`; an invalid
  regex → literal search with `note`; `context_lines`, `max_results`, `max_result_lines`
  truncation behave as in `tests/file_tools/test_search.py`.
- On win32, `glob="**/CLAUDE.md"` matches `"Claude.md"` (case-insensitive, same as today).
- Existing `tests/file_tools/test_search.py` passes unchanged.
