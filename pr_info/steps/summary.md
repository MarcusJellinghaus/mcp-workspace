# Summary — Issue #252

Advertise the reference-project capability through the server-level MCP `instructions`
field, and stop maintaining the same tool list in five places.

## Problem

An agent only learns that reference projects are searchable, git-readable local
checkouts of sibling repos once something already prompts it to look. Under deferred
tool loading a client holds only tool *names*; descriptions require an explicit
lookup. So the `get_reference_projects` docstring cannot prevent the failure that
produced this issue — asking the user whether sibling repos had a given MCP server
configured, when `search_reference_files` would have answered it.

Server-level `instructions` are surfaced unconditionally, before any tool call, while
tools are still deferred. `src/mcp_workspace/server.py:47` builds
`FastMCP("File System Service")` with no `instructions`, so this server contributes
nothing to that block.

Separately, the twelve reachable tool names are spelled out in five places (docstring,
`usage` string, two tests, `README.md:383`) and a different eight-name list in three
more (`README.md:35`, `README.md:455`, `.claude/CLAUDE.md:61`, plus a "these eight
tools alone" count at `README.md:460`). #270 and #278 each had to touch several;
missing one re-opens this issue.

## Architectural / design changes

**1. A new, unconditional advertising channel.** The server gains a static
`instructions` string — the first server-level metadata this project has set. It is a
different delivery channel from tool descriptions: always in context, never gated on a
tool lookup. It becomes the primary home for the reference-project framing; the
docstring keeps a one-line pointer only as insurance against clients that drop the
field.

**2. Description by category replaces enumeration.** The twelve names collapse to
"the reference file tools, `git()`, and the GitHub read tools; issues can also be
created, edited and commented on" — scoped to the read tools plus issue writes because
`github_pr_create` takes no `reference_name`. This trades away literal-string
discoverability (an agent grepping descriptions for `github_label_list` won't find it
in the instructions block) for a list that cannot drift. The per-tool reference tables
stay the place where every tool is named: the `.claude/CLAUDE.md` tool mapping table
already lists all of them, and `README.md:223-229` gains the seven rows it is missing.
Four are from the prose enumeration — `github_label_list`, `github_issue_create`,
`github_issue_edit`, `github_issue_comment` — and three are not: `search_reference_files`
and `git` appear in `README.md` only inside the quoted `usage` string at line 383, and
`github_pr_create` only in the bullet at line 460. All seven otherwise appear in
`README.md` only in the passages steps 2 and 3 remove.

**3. No new runtime state or code path.** The instructions text is a literal argument
at construction. `mcp` is built at import time, before `run_server()` learns the
configuration, so the text names no projects and no filesystem paths. Assigning later
would work — `create_initialization_options` reads `self.instructions` at client
connect — but requires touching the private `_mcp_server` attribute and would disclose
which repos are configured. Rejected on both counts.

**4. `usage` drops its interpolated count.** The value becomes a plain string rather
than an f-string, `count` already carries the number, and the two test expectations
become byte-identical. The empty case keeps `"No reference projects available"`
unchanged — it usefully explains a `count: 0` that would otherwise read as a
malfunction.

## Constraints carried from the issue

- **No filesystem path may reach the model.** `get_reference_projects` returns `name`
  and `url` only, never `path` (`server_reference_tools.py:65-68`). Preserve that, and
  keep paths out of the instructions text.
- **Keep the instructions short.** Every session pays for this block, including
  sessions that never touch a reference project. Target ~60-70 words.
- **Do not rename the concept.** "reference project" is load-bearing across the
  `--reference-project` CLI flag, the `reference_name` parameter on twelve tools, and
  four tool names. Out of scope.
- **Ruff DOC201 requires the `Returns:` block.** A docstring reduced to a summary and
  a pointer, with no `Returns:` section, fails. Free-form prose *after* `Returns:`
  lints clean, so the one-line pointer goes there.
- **`git()` and `get_reference_projects()` may be named** in the instructions text —
  the issue's Approach specifies exactly that. What is banned is restating the roster
  of twelve.

## Testing note

Step 1 adds one content test in `tests/test_server.py`, read through the public
`FastMCP.instructions` property (never `mcp._mcp_server`). Non-emptiness alone would be
close to tautological, so the test asserts the rules the text has to satisfy: it
mentions reference projects, contains no `github_*` or reference-file tool name, and
contains no filesystem path. That automates three of the issue's verification bullets —
a non-empty `instructions` argument, no individual tool names, no path. The fourth,
that a client actually surfaces the block, still needs an MCP server restart, which no
unit test reaches. Steps 2 and 3 are covered by the two existing expectations in
`tests/test_reference_projects_mcp_tools.py`, updated test-first.

**Verifying by hand needs an MCP server restart.** The description an agent sees comes
from the running process. During analysis of this issue the live server still
advertised the pre-#278 eight-tool docstring while the file on disk was current — a
stale process, not a code discrepancy.

## Files created or modified

No new folders or modules. No new files outside `pr_info/`.

| File | Step | Change |
|---|---|---|
| `src/mcp_workspace/server.py` | 1 | Line 47: pass `instructions=` to `FastMCP(...)` |
| `tests/test_server.py` | 1 | New instructions-content test |
| `src/mcp_workspace/server_reference_tools.py` | 2 | Lines 37-50 docstring; lines 78-84 `usage` value |
| `tests/test_reference_projects_mcp_tools.py` | 2 | Lines 58-64 and 92-98: both `usage` expectations |
| `README.md` | 2 | Line 383: quoted `usage` example |
| `README.md` | 3 | Lines 35, 455, 460: prose enumerations and the count |
| `README.md` | 3 | Lines 223-229: seven rows added to the per-tool table |
| `.claude/CLAUDE.md` | 3 | Line 61: prose enumeration |

Unchanged on purpose: the existing rows of `README.md:223-229`, the `.claude/CLAUDE.md`
tool mapping table, `README.md:374` (the `projects` field description), the `count: 0`
branch, `tests/LLM_Test.md` (asserts `usage` is a `str`, not its value), and
`docs/ARCHITECTURE.md` (no layer or dependency changes).

## Steps

1. [step_1.md](./step_1.md) — server-level `instructions`
2. [step_2.md](./step_2.md) — shrink the docstring and `usage`, update tests and the README example
3. [step_3.md](./step_3.md) — convert the eight-name prose enumerations to categories

## Verification (from the issue)

- `FastMCP(...)` is constructed with a non-empty `instructions` argument.
- Neither the instructions text, the docstring, nor `usage` enumerates individual tool
  names.
- `README.md` quotes the current `usage` value.
- No filesystem path appears in the instructions text or any `get_reference_projects`
  return value.
- Restarting the MCP server surfaces the instructions block in the client's
  server-instructions section.
- `run_pylint_check`, `run_pytest_check`, `run_mypy_check` and ruff `D`/`DOC` pass.
- No prose passage in `README.md` or `.claude/CLAUDE.md` enumerates the GitHub tools
  that accept `reference_name`, and no count of them survives.
