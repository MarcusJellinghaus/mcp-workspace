# Step 5 — Documentation

Docs only, no source logic and no tests. States the invariant where a later reader will
actually meet it.

## WHERE

| File | Role |
|---|---|
| `docs/ARCHITECTURE.md` | the invariant and its boundary |
| `src/mcp_workspace/file_tools/directory_utils.py` | `_discover_files` docstring |
| `src/mcp_workspace/server.py` | `list_directory` and `search_files` tool docstrings |
| `src/mcp_workspace/server_reference_tools.py` | `list_reference_directory` and `search_reference_files` tool docstrings |

Explicitly **not** `README.md`: its tool table is one line per tool and would drift.

## WHAT

1. **`docs/ARCHITECTURE.md`** — a new numbered subsection under **Architectural
   Principles**, following the style of the existing "4. Fast Startup via Lazy Imports" and
   "5. Truststore Activation": a short heading, the rule, the boundary, and why it is
   load-bearing. It must state **both** halves:

   - Every project-relative path the server emits is forward-slash separated, in structured
     return values and prose error messages alike.
   - **Absolute paths stay native.** `edit_file`'s `File not found: {abs_path}` and
     `path_utils._outside_error` keep OS separators — they are not fed back into tools, and
     `C:/Users/...` reads worse than it helps.

   Name the two enforcement points (`_discover_files`, `normalize_path`) so a later reader
   knows where to add a third rather than reaching for a per-site `replace`. Note that CI is
   `ubuntu-latest` only, so the guard is `tests/test_path_separator_invariant.py`, not CI.

2. **`_discover_files`' docstring** — one added sentence in `Returns:`: paths are
   project-relative and forward-slash separated on every platform. It is the enforcement
   point for all four listing/search tools.

3. **Four `@mcp.tool()` docstrings** — one sentence each in `Returns:`, stating that paths
   are forward-slash separated on every platform and can be passed straight back to
   `read_file` / `read_reference_file`.

## HOW

- The tool docstrings are the descriptions callers actually see. The wiki records the glob
  gotcha as invisible to callers precisely because "gitignore semantics" lived only in a
  helper docstring — do not repeat that by documenting this only in `ARCHITECTURE.md` or
  only on `_discover_files`.
- Keep each docstring addition to one sentence. These docstrings are already long and are
  shipped to every caller on every connection.
- `tests/test_tool_descriptions.py` exists and asserts on tool descriptions — check whether
  it constrains length or content before editing, and update it if it does.

## ALGORITHM

None — this step changes no logic.

## DATA

No return values change. Docstring text only.

## Tests

No new tests. `tests/test_tool_descriptions.py` may need updating if it pins description
content; the full suite must stay green.

## Checks

`run_format_code`, then `run_pylint_check`, `run_pytest_check` with `["-n", "auto"]`,
`run_mypy_check`. One commit.

---

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_5.md`, then implement step 5.
> Steps 1–4 must already be committed.
>
> Documentation only — change no logic.
>
> Add a numbered subsection to **Architectural Principles** in `docs/ARCHITECTURE.md`
> stating the forward-slash invariant **and its boundary**: project-relative paths are
> forward-slash separated everywhere, absolute paths stay native. Match the style of the
> existing sections 4 and 5. Name the two enforcement points and note that the guard is
> `tests/test_path_separator_invariant.py` rather than CI, which is `ubuntu-latest` only.
>
> Then add one sentence to the `Returns:` block of `_discover_files` and of the four
> `@mcp.tool()` docstrings: `list_directory`, `search_files`, `list_reference_directory`,
> `search_reference_files`. One sentence each — these descriptions ship to every caller.
>
> Do not touch `README.md`; its per-tool table would drift.
>
> Check `tests/test_tool_descriptions.py` first in case it pins description content.
>
> Use the MCP tools per `CLAUDE.md`. Run `run_format_code`, then `run_pylint_check`,
> `run_pytest_check` with `extra_args: ["-n", "auto"]`, and `run_mypy_check`. All must pass.
> Commit once.
