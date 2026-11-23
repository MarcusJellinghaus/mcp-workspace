# Step 12 — Tool docstrings, server instructions, description tests

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_12.md`.
> Write the tests first, then the implementation. Use the MCP tools from `.claude/CLAUDE.md`.
> Run pylint, pytest (`extra_args: ["-n", "auto"]`) and mypy; all must pass. Run
> `run_format_code`, then make exactly one commit for this step.

## WHERE

- `src/mcp_workspace/toolset/reference.py` — docstrings and Field descriptions of
  `read_reference_file`, `search_reference_files`, `list_reference_directory`
- `src/mcp_workspace/toolset/git.py` — `reference_name` Field description
- `src/mcp_workspace/server.py` — `_INSTRUCTIONS`
- `tests/test_tool_descriptions.py`, `tests/test_server_instructions.py`

## WHAT — required content ("Docstrings must say" in #340)

All three read tools:
- Content comes from the reference's `origin/<default>` (`origin/HEAD`, else `origin/main`,
  else `origin/master`), fetched automatically, at most one fetch interval old.
- Only tracked files exist there: tracked files matching `.gitignore` are visible; untracked
  or gitignored local files are not. A folder that is not a git repo is read as-is.
- Other refs: `git(command="show", args=["<ref>:<path>"], reference_name=…)` — output defaults
  to 100 lines, pass `max_lines` for more.
- "When was X added upstream": `git(command="log", args=["-S<text>", "origin/main"], reference_name=…)`.
- A note line / entry appears only when the fetch failed or the repo has no usable origin
  default branch.
- Known limitations (one short sentence each): after an upstream default-branch rename,
  reads follow the old branch until `git remote set-head origin --auto`; with
  `core.autocrlf=true` content has LF where the working tree has CRLF; Git LFS files show
  pointer text; partial clones download missing blobs on read.

Per tool:
- `list_reference_directory` Returns: paths can be passed back to `read_reference_file`;
  the **last entry may be a note** instead of a path (and, for a local folder, the first
  line may be a `WARNING:` as today).
- `search_reference_files` Returns: lists the `freshness` key (present only when a note
  applies). Glob description: replace the `git ls-files` advice with
  `git(command="ls_tree", args=["-r", "--name-only", "origin/main"], reference_name=…)`
  (the ref named in the tool's notes and errors), mentioning `max_lines` or a pathspec
  (output defaults to 100 lines).
- `git` `reference_name`: "…runs git against that project instead of the workspace, after
  the same automatic fetch of origin as the reference read tools; a failed fetch adds a
  trailing note and never fails the call."
- `_INSTRUCTIONS`: one sentence that reference files are read from the upstream default
  branch, auto-fetched — without naming tools other than those
  `tests/test_server_instructions.py` already allows.

## HOW

Keep `search_files`' glob description unchanged (its `git ls-files` advice stays correct
for the workspace). Schema snapshots in `tests/toolset/tool_schemas/` strip descriptions and
no parameters change, so they need no update; if they fail, regenerate only after checking
the diff is description-free.

## Tests (write first)

- `tests/test_tool_descriptions.py`: split `GLOB_DOC_PHRASES` into a shared list
  (`gitignore`, `brace expansion is not supported`, `any depth`, `case-insensitive`,
  `glob_note`) plus per-tool phrases: `search_files` → `git ls-files`;
  `search_reference_files` → `ls_tree`, `--name-only`, `origin/main`, `max_lines`.
- New description tests (lower-cased substring checks) for each read tool: `origin/`,
  `fetched automatically` (or the chosen wording), `tracked`, `git(command="show"`,
  `max_lines`, `-s<text>`; `list_reference_directory` → `last entry may be a note`;
  `search_reference_files` → `freshness`; `git` tool `reference_name` field → `fetch`.
- `tests/test_server_instructions.py`: instructions mention the upstream default branch.
