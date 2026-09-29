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
def _paths(value: Any, keys: tuple[str, ...]) -> list[str]:
    """Collect the path-carrying strings from a tool return value.

    For list/str results, every string. For dict results, only the values under
    `keys` (recursively), so match text and other free-form strings are skipped.
    """

@pytest.fixture
def invariant_project(tmp_path: Path) -> Path:
    """Temp project with a nested file, a nested file to move, a nested
    over-the-limit file for check_file_size, and a git repo. Calls
    server.set_project_dir(tmp_path) and restores the previous value on
    teardown — list_directory, search_files, edit_file and check_file_size all
    read the server module global. All fixture file contents are ASCII and
    backslash-free."""

@pytest.fixture
def reference_project(invariant_project: Path) -> Iterator[str]:
    """Register invariant_project as a reference project; yield its name."""

@pytest.mark.parametrize("tool_name, call, path_keys", [...])
def test_emitted_paths_use_forward_slashes(
    tool_name, call, path_keys, invariant_project, reference_project
) -> None:
    # Every callable takes the same two arguments; the six non-reference
    # tools ignore the second.
    result = call(invariant_project, reference_project)
```

## HOW

- **One parametrized test**, not eight. Each param is a `(name, callable, path_keys)`
  triple; the callable runs one tool against the temp project and returns its raw result,
  and `path_keys` names the result keys that carry paths. Adding a tool to the guarded set
  is one line.
- **Every callable takes `(project, reference_name)`**, so one signature serves all eight
  params: the two reference tools pass `reference_name` through, the other six ignore it.
  The test function therefore requests **both** fixtures, `invariant_project` and
  `reference_project`; the latter depends on the former, so the temp project is registered
  as a reference project for every param, which is harmless for the six that do not use it.
- `_paths` walks `str`, `list`, `tuple` and `dict`. For a `dict` it descends only into the
  keys named in `path_keys`, so free-form strings — `search_files`' matched line text
  above all — are never asserted over. A `list`/`str` result carries nothing but paths and
  is walked whole.
- **The assertion must never be able to fail on file content.** Three results embed file
  text: `search_files`' matches, `edit_file`'s diff body, and `check_file_size`'s report.
  Two defences, both required. First, `path_keys` excludes the content-bearing keys.
  Second, for the two tools whose result is a bare `str`, the call arguments are pinned so
  content cannot reach the assertion:
  - `edit_file` — assert only the `---`/`+++` diff header lines (the paths it emits);
    filter the result to lines starting with `---` or `+++` before asserting.
  - `check_file_size` — assert only the violation lines (`  - <path>: N lines`) and stale
    allowlist lines; filter to lines starting with `  - ` before asserting.
  - `search_files` — call it in **file-search** mode (`glob` only, no `pattern`), so the
    result carries `files` and `skipped_files` and no match text at all.
  Belt and braces, the fixture's file contents are ASCII and contain no backslash, so a
  stray content string cannot produce a false failure either.
- The reference fixture follows the existing pattern in
  `tests/test_reference_search_mcp_tools.py`: set
  `mcp_workspace.server_reference_tools._reference_projects` to
  `{name: ReferenceProject(name=..., path=...)}` and patch
  `server_reference_tools.ensure_available` with an `AsyncMock` returning `None`. Restore
  the module global on teardown.
- **Three of the guarded tools are `async`** — `edit_file` (`server.py:712`) as well as the
  two reference tools. Wrap each of those callables with `asyncio.run` so the single
  parametrized test stays sync (preferred over `pytest.mark.asyncio`, which would split the
  test). Missing the wrapper does not fail: the callable returns an un-awaited coroutine,
  `_paths` collects nothing from it, and the parameter passes vacuously — which for
  `edit_file` silently drops the only check on `_create_diff`'s `replace`
  (`file_tools/edit_file.py:150`), the accidental compliance this test exists to pin.
- `move_file` is covered at the **util** layer (`file_operations.move_file`, whose returned
  dict carries `source` and `destination`), not at the MCP tool layer, whose `bool` return
  carries no path.
- `edit_file` is covered for its **diff headers**, which are the paths it emits.

## ALGORITHM

```
build temp project containing a nested file (a/b/c.txt) and a nested edit/move target,
  plus a nested file over check_file_size's threshold; all contents ASCII, no backslash
set_project_dir(project)                      # the MCP tools read the module global
register project as a reference project       # reference_project fixture, yields its name
for each (tool_name, call, path_keys) in the parametrized set:
    result = call(project, reference_name)    # async tools wrapped in asyncio.run
    for s in _paths(result, path_keys):       # path-carrying fields/lines only
        assert "\\" not in s, f"{tool_name} emitted a native separator: {s!r}"
restore the previous project dir
```

## DATA

The guarded set, named explicitly:

| Tool | Layer | What it emits | Asserted over |
|---|---|---|---|
| `list_directory` | MCP tool | `List[str]` of entries | the whole list |
| `search_files` | MCP tool | `Dict[str, Any]` — `files`, `matches`, `skipped_files` | `files`, `skipped_files`; called glob-only so `matches` is absent |
| `list_reference_directory` | reference tool | `List[str]` | the whole list |
| `search_reference_files` | reference tool | `Dict[str, Any]` | `files`, `skipped_files`; called glob-only |
| `delete_directory` | util | `list[str]` of deleted paths | the whole list |
| `move_file` | util | `Dict[str, Any]` with `source`, `destination` | `source`, `destination` |
| `edit_file` | MCP tool (`async`) | `str` — diff headers plus diff body, **only after `asyncio.run`**; the raw call yields a coroutine | the `---`/`+++` header lines only |
| `check_file_size` | MCP tool | `str` — report text | the `  - ` violation/stale lines only |

The `Asserted over` column is what `path_keys` (dict results) or the line filter (`str`
results) selects. Everything excluded is file content or prose, which carries no path and
could otherwise fail on data rather than on a separator bug.

`check_file_size` only emits paths for violations (or stale allowlist entries), so the call
must produce one: give the fixture a nested file above the threshold, or call it with a
threshold low enough (`max_lines=0`) that the nested file violates it. Without that the
parameter asserts over a report containing no paths at all.

Excluded, deliberately: `git`, `github_pr_view` and `check_branch_status`. Their paths
originate outside this codebase already forward-slashed — the "already compliant" row — so
there is nothing this change can regress, and including them would mean mocking the GitHub
API for no added guard.

## Tests

This step *is* the test. Two properties to get right:

1. The assertion must be able to fail. Pin that automatically: assert `_paths` returns a
   deliberately backslashed sample string, from both a `list` result and a `dict` result
   under a named key, so the narrowing added here cannot silence the guard.
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
> Write it as **one parametrized test** over the eight `(tool_name, callable, path_keys)`
> triples in the **DATA** table, plus a `_paths` helper that collects the path-carrying
> strings from a return value. The assertion is that no emitted path contains a backslash.
>
> Give every callable the signature `(project, reference_name)` and have the test request
> both the `invariant_project` and `reference_project` fixtures, so the two reference-tool
> params get the name they need and the other six ignore it.
>
> Wrap the three `async` tools — `edit_file` and the two reference tools — in `asyncio.run`.
> Without the wrapper the callable returns an un-awaited coroutine, `_paths` finds nothing
> in it, and the parameter passes vacuously.
>
> Assert only over the `Asserted over` column of the **DATA** table — never over file
> content. `search_files` and `search_reference_files` are called glob-only so no match text
> is returned; `edit_file` is narrowed to its `---`/`+++` diff header lines and
> `check_file_size` to its `  - ` violation lines. Keep every fixture file's content ASCII
> and backslash-free as a second line of defence.
>
> The `invariant_project` fixture must call `server.set_project_dir(tmp_path)` and restore
> the previous value on teardown — `list_directory`, `search_files`, `edit_file` and
> `check_file_size` all read that module global.
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
