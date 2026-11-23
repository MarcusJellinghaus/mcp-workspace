# Step 4 — Raises clauses in tool descriptions (gaps 1, 2)

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_4.md`.
> Write the tests first, then the docstrings. Run pylint, pytest (`-n auto`) and mypy until all
> pass, run `run_format_code`, and make exactly one commit.

## Goal

Each tool that refuses gitignored or read-only paths says so in its description, in one short
clause. Descriptions only; no behaviour change.

## WHERE

- `src/mcp_workspace/toolset/read.py` — `read_file`
- `src/mcp_workspace/toolset/reference.py` — `read_reference_file`
- `src/mcp_workspace/toolset/write.py` — `save_file`, `append_file`, `edit_file`
- `src/mcp_workspace/toolset/delete.py` — `delete_this_file`, `delete_directory`
- `src/mcp_workspace/toolset/move.py` — `move_file`
- `tests/test_tool_descriptions.py`

## WHAT — docstring text (Raises → `ValueError`)

- **`read_file`:** extend the existing clause to: `If file_path is not a non-empty string, or is
  gitignored and not exposed by the project's .mcp-file-access.`
- **`read_reference_file`:** add a new section
  `Raises:\n    ValueError: If file_path is gitignored and not exposed by that project's
  .mcp-file-access.` No noqa is needed; DOC502 is already per-file ignored for
  `toolset/reference.py` in `pyproject.toml`.
- **`save_file`, `append_file`, `edit_file`, `delete_this_file`:** append to the existing clause:
  `…, or file_path is gitignored and not exposed read-write by .mcp-file-access, or read-only by
  it ("No write access to '<path>' (…)").`
- **`move_file`:** in the `ValueError` entry, add the same refusal for the source and destination:
  `if the source or destination is gitignored and not exposed read-write by .mcp-file-access, or
  the source or destination path of any moved file is read-only by it ("No write access to
  '<path>' (…)")`. Keep the "would make a file hidden by .gitignore accessible" clause.
- **`delete_directory`:** replace `the path is excluded by .gitignore` with `the path is gitignored and
  not exposed read-write by .mcp-file-access`. Add `("No write access to '<path>' (…)")` after
  its read-only clause.

## HOW

The docstrings become the tool descriptions through `tool_spec`. Keep each addition to one clause.

## ALGORITHM / DATA

None.

## Tests (write first) — `tests/test_tool_descriptions.py`

Add two parametrized tests, using `tool_specs(tmp_path)` and `spec.description.lower()`:

```python
READ_TOOLS = ["read_file", "read_reference_file"]
WRITE_TOOLS = ["save_file", "append_file", "edit_file", "delete_this_file",
               "move_file", "delete_directory"]
# read tools: ".mcp-file-access" and "not exposed by" in description
# write tools: "not exposed read-write by .mcp-file-access" and "no write access" in description
```

## Commit

`docs(toolset): mention .mcp-file-access in file tool Raises clauses (#404)`
