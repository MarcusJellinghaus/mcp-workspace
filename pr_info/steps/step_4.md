# Step 4 — Cross-tool invariant test

Tests only, no source changes. This is what makes "every emitted path is forward-slash
separated" verifiable instead of a list that drifts, and it is what pins `edit_file`'s
compliance, which today is accidental.

## WHERE

| File | Role |
|---|---|
| `tests/test_path_separator_invariant.py` | **new** — the whole step |

Sits in the `tests/` root alongside the other cross-cutting suites
(`test_tool_descriptions.py`, `test_startup_performance.py`). No new folder or module.

## WHAT

```python
def _strings(value: Any) -> list[str]:
    """Flatten a tool return value to every string it carries."""

@pytest.fixture
def invariant_project(tmp_path: Path) -> Path:
    """Temp project with a nested file, a nested file to move, and a git repo."""

@pytest.fixture
def reference_project(invariant_project: Path) -> Iterator[str]:
    """Register invariant_project as a reference project; yield its name."""

@pytest.mark.parametrize("tool_name, call", [...])
def test_emitted_paths_use_forward_slashes(tool_name, call, invariant_project) -> None:
```

## HOW

- **One parametrized test**, not eight. Each param is a `(name, callable)` pair; the
  callable runs one tool against the temp project and returns its raw result. Adding a tool
  to the guarded set is one line.
- `_strings` walks `str`, `list`, `tuple` and `dict` (values **and** keys are irrelevant —
  walk values only) and yields every `str` it finds, so a tool returning a `Dict[str, Any]`
  is covered without the test knowing its shape.
- The reference fixture follows the existing pattern in
  `tests/test_reference_search_mcp_tools.py`: set
  `mcp_workspace.server_reference_tools._reference_projects` to
  `{name: ReferenceProject(name=..., path=...)}` and patch
  `server_reference_tools.ensure_available` with an `AsyncMock` returning `None`. Restore
  the module global on teardown.
- The two reference tools are `async`; mark those params with `pytest.mark.asyncio` or wrap
  the callables with `asyncio.run` so the single parametrized test stays sync. Prefer the
  wrapper — it keeps one test function.
- `move_file` is covered at the **util** layer (`file_operations.move_file`, whose returned
  dict carries `source` and `destination`), not at the MCP tool layer, whose `bool` return
  carries no path.
- `edit_file` is covered for its **diff headers**, which are the paths it emits.

## ALGORITHM

```
build temp project containing a nested file (a/b/c.txt) and a nested edit/move target
for each (tool_name, call) in the parametrized set:
    result = call(project)
    for s in _strings(result):
        assert "\\" not in s, f"{tool_name} emitted a native separator: {s!r}"
```

## DATA

The guarded set, named explicitly:

| Tool | Layer | What it emits |
|---|---|---|
| `list_directory` | MCP tool | `List[str]` of entries |
| `search_files` | MCP tool | `Dict[str, Any]` — `files`, `matches`, `skipped_files` |
| `list_reference_directory` | reference tool | `List[str]` |
| `search_reference_files` | reference tool | `Dict[str, Any]` |
| `delete_directory` | util | `list[str]` of deleted paths |
| `move_file` | util | `Dict[str, Any]` with `source`, `destination` |
| `edit_file` | MCP tool | diff headers in the result |
| `check_file_size` | MCP tool | report text |

Excluded, deliberately: `git`, `github_pr_view` and `check_branch_status`. Their paths
originate outside this codebase already forward-slashed — the "already compliant" row — so
there is nothing this change can regress, and including them would mean mocking the GitHub
API for no added guard.

## Tests

This step *is* the test. Two properties to get right:

1. It must **fail on the pre-fix code**. Verify by stashing step 1 locally, or at minimum by
   asserting that the same helper flags a deliberately backslashed sample string.
2. It must not duplicate per-tool assertions. This file is the single home for *separator*
   assertions across the guarded set. The separator-coverage criteria for
   `list_reference_directory` and `search_reference_files` are satisfied here, not by
   separate tests. Per-tool tests in steps 1–3 assert only *correctness* claims this test
   cannot express: exact string values, nested paths, and each path appearing exactly once.

## Checks

`run_format_code`, then `run_pylint_check`, `run_pytest_check` with `["-n", "auto"]`,
`run_mypy_check`. One commit.

---

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_4.md`, then implement step 4.
> Steps 1–3 must already be committed.
>
> Create `tests/test_path_separator_invariant.py`. Source code is not modified in this step;
> if any tool in the guarded set fails the invariant, that is a bug in steps 1–3 to fix
> there, not here.
>
> Write it as **one parametrized test** over the eight `(tool_name, callable)` pairs in the
> **DATA** table, plus a `_strings` helper that flattens any return value to the strings it
> carries. The assertion is that no emitted string contains a backslash.
>
> For the two reference tools, follow the fixture pattern already used in
> `tests/test_reference_search_mcp_tools.py`: set
> `server_reference_tools._reference_projects` and patch `ensure_available` with an
> `AsyncMock`. Cover `move_file` at the util layer, not the MCP tool layer — the tool
> returns `bool` and carries no path.
>
> Exclude `git`, `github_pr_view` and `check_branch_status`; their paths arrive from the
> GitHub API already forward-slashed.
>
> Use the MCP tools per `CLAUDE.md`. Run `run_format_code`, then `run_pylint_check`,
> `run_pytest_check` with `extra_args: ["-n", "auto"]`, and `run_mypy_check`. All must pass.
> Commit once.
