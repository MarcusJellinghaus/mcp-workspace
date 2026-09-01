# Step 1 — Server-level MCP `instructions`

One commit. Read [summary.md](./summary.md) first.

## WHERE

`src/mcp_workspace/server.py`, line 47 only.

```python
# Create a FastMCP server instance
mcp = FastMCP("File System Service")
```

## WHAT

`FastMCP.__init__` takes `instructions: str | None` as its second parameter (verified
against the installed `mcp` package):

```python
def __init__(self, name: str | None = None, instructions: str | None = None, ...)
```

Pass the text as a keyword argument. Do **not** introduce a module-level constant: the
string is used once, and an implicitly concatenated literal inside the call avoids both
a name and the stray indentation of a triple-quoted string in a call.

```python
mcp = FastMCP(
    "File System Service",
    instructions=(
        "Reference projects are full local checkouts of sibling repositories, "
        "configured when this server starts. Their files are readable and "
        "searchable read-only, their history is available through git(), and "
        "their GitHub issues and pull requests are reachable through the GitHub "
        "tools — issues there are writable. Answer questions about another repo "
        "from its reference project instead of asking the user. Call "
        "get_reference_projects() for the configured names, then pass one as "
        "reference_name."
    ),
)
register_reference_tools(mcp)
```

## HOW

No imports change; `FastMCP` is already imported at `server.py:11`. `register_reference_tools(mcp)`
on the next line is untouched. Nothing else in the module reads or writes the value.

## DATA

The text must satisfy, and each is checkable by reading it:

- names no reference project and no filesystem path (it is built at import time, before
  `run_server()` learns the configuration — it *cannot* name projects even if it wanted to);
- describes the reachable tools by category, not by listing the twelve names.
  `git()` and `get_reference_projects()` are the two deliberate exceptions;
- states what a reference project *is* (a full local checkout of a sibling repo) and
  when to reach for one (instead of asking the user about another repo);
- notes that issues are writable, since read-only is the default assumption;
- stays around 60-70 words. Every session pays for this block.

## Tests

One test, in its own module `tests/test_server_instructions.py` — `tests/test_server.py`
is close to the 750-line file-size limit and this is a content assertion, not a
file-operations API test. `FastMCP` exposes `instructions` as a public
read-only property (`self._mcp_server.instructions`), so read `mcp.instructions` —
never `mcp._mcp_server`. Assert the *content* rules the DATA section states, not mere
non-emptiness:

```python
from mcp_workspace.server import mcp


def test_server_instructions_describe_reference_projects() -> None:
    """Server instructions advertise reference projects without naming tools or paths."""
    text = mcp.instructions
    assert text is not None
    assert "reference project" in text.lower()
    # Only git() and get_reference_projects() may be named; no tool roster
    assert "github_" not in text
    assert "read_reference_file" not in text
    assert "search_reference_files" not in text
    assert "list_reference_directory" not in text
    # No filesystem path may reach the model
    assert "\\" not in text and "/" not in text
```

This automates three of the issue's verification bullets: a non-empty `instructions`
argument, no individual tool names in the text, and no filesystem path in it. What it
cannot cover is the client actually surfacing the block — that still needs the manual
restart below.

## Checks

`run_format_code`, then `run_pylint_check`, `run_pytest_check` with
`extra_args: ["-n", "auto"]`, `run_mypy_check`, `run_ruff_check`. The existing suite
must stay green — in particular `tests/test_startup_performance.py`, which asserts that
importing `mcp_workspace.server` does not eagerly import `github`/`git`. This change
adds no import.

## Manual verification

Restart the MCP server, then confirm the text appears in the client's
server-instructions section. A stale server process shows the previous build; that is
the trap noted in the summary, not a code problem.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`.
>
> Implement step 1 test-first: add the instructions-content test from the step as a new
> `tests/test_server_instructions.py`, confirm it fails, then add the static `instructions=`
> argument to the `FastMCP(...)` constructor at `src/mcp_workspace/server.py:47`,
> using the text and the inline implicit-concatenation style given in the step. No
> module-level constant, no new imports in `server.py`, and read `mcp.instructions`
> (the public property) rather than `mcp._mcp_server`.
>
> Use the `mcp__mcp-workspace__*` tools for all file access. Then run
> `run_format_code`, `run_pylint_check`, `run_pytest_check` with
> `extra_args: ["-n", "auto"]`, `run_mypy_check` and `run_ruff_check`, and commit
> once with all checks passing.
